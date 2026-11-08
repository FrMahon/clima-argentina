"""Carga: archivos JSON crudos → tabla raw.open_meteo_daily en DuckDB.

- Upsert por (city_id, date): si un día llega en dos archivos, gana el más reciente.
- raw.load_log registra qué archivos ya se cargaron, así recargar es idempotente.
- El "desarmado" del JSON (listas paralelas → una fila por día) se hace en SQL con UNNEST.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import duckdb

from . import config

log = logging.getLogger(__name__)

DDL = """
create schema if not exists raw;

create table if not exists raw.open_meteo_daily (
    city_id              varchar   not null,
    date                 date      not null,
    temperature_2m_mean  double,
    temperature_2m_max   double,
    temperature_2m_min   double,
    precipitation_sum    double,
    grid_latitude        double,
    grid_longitude       double,
    grid_elevation_m     double,
    model                varchar,
    source_file          varchar   not null,
    extracted_at         timestamp not null,
    loaded_at            timestamp not null,
    primary key (city_id, date)
);

create table if not exists raw.load_log (
    source_file  varchar   primary key,
    rows_loaded  integer   not null,
    loaded_at    timestamp not null
);
"""

# Las listas de "daily" vienen en paralelo (time[i] ↔ temperature_2m_mean[i] …):
# varios UNNEST en el mismo SELECT las recorren juntas, como un zip.
LOAD_SQL = """
insert or replace into raw.open_meteo_daily
select
    city_id, date,
    temperature_2m_mean, temperature_2m_max, temperature_2m_min, precipitation_sum,
    grid_latitude, grid_longitude, grid_elevation_m, model,
    source_file, extracted_at, now()::timestamp as loaded_at
from (
    select
        j.city_id,
        j.model,
        cast(j.extracted_at as timestamptz)::timestamp            as extracted_at,
        cast(j.response.latitude  as double)                       as grid_latitude,
        cast(j.response.longitude as double)                       as grid_longitude,
        cast(j.response.elevation as double)                       as grid_elevation_m,
        $source_file                                               as source_file,
        cast(unnest(j.response.daily.time) as date)                as date,
        cast(unnest(j.response.daily.temperature_2m_mean) as double) as temperature_2m_mean,
        cast(unnest(j.response.daily.temperature_2m_max)  as double) as temperature_2m_max,
        cast(unnest(j.response.daily.temperature_2m_min)  as double) as temperature_2m_min,
        cast(unnest(j.response.daily.precipitation_sum)   as double) as precipitation_sum
    from read_json({path}, maximum_object_size = 67108864) as j
)
-- Días que la API devuelve vacíos (todavía sin publicar): no deben pisar datos buenos.
where coalesce(temperature_2m_mean, temperature_2m_max, temperature_2m_min) is not null
"""


def connect(db_path: Path = config.DB_PATH) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute(DDL)
    return con


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _extracted_at_key(path: Path) -> str:
    # <ciudad>__<inicio>__<fin>__<YYYYmmddTHHMMSS>.json → ordenar por momento de extracción
    return path.stem.rsplit("__", 1)[-1]


def load_raw_files(con: duckdb.DuckDBPyConnection, raw_dir: Path = config.RAW_DIR) -> int:
    """Carga los archivos que todavía no están en raw.load_log. Devuelve filas cargadas."""
    loaded = {r[0] for r in con.execute("select source_file from raw.load_log").fetchall()}
    pending = sorted(
        (p for p in raw_dir.glob("*/*.json") if p.relative_to(raw_dir).as_posix() not in loaded),
        key=_extracted_at_key,
    )
    total = 0
    for path in pending:
        source_file = path.relative_to(raw_dir).as_posix()
        sql = LOAD_SQL.format(path=_sql_literal(path.as_posix()))
        con.execute("begin transaction")
        try:
            n = con.execute(sql, {"source_file": source_file}).fetchone()[0]
            con.execute(
                "insert into raw.load_log values (?, ?, now()::timestamp)", [source_file, n]
            )
            con.execute("commit")
        except Exception:
            con.execute("rollback")
            raise
        total += n
        log.debug("Cargado %s (%d filas)", source_file, n)
    log.info("Carga: %d archivos nuevos, %d filas", len(pending), total)
    return total


def get_watermarks(con: duckdb.DuckDBPyConnection) -> dict[str, date]:
    """Último día cargado por ciudad."""
    return dict(
        con.execute("select city_id, max(date) from raw.open_meteo_daily group by city_id").fetchall()
    )
