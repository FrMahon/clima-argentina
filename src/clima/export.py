"""Exporta los marts a un JSON compacto y arma el sitio estático del dashboard (site/)."""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from . import config

log = logging.getLogger(__name__)


def _rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, (_clean(v) for v in row))) for row in cur.fetchall()]


def _clean(value):
    if isinstance(value, float):
        return round(value, 2)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _columnar(rows: list[dict], key: str, fields: list[str]) -> dict[str, dict[str, list]]:
    """[{key, year, a, b}, …] → {key: {year: [...], a: [...], b: [...]}}: mucho más liviano."""
    out: dict[str, dict[str, list]] = {}
    for r in rows:
        series = out.setdefault(r[key], {f: [] for f in fields})
        for f in fields:
            series[f].append(r[f])
    return out


def build_dataset(con: duckdb.DuckDBPyConnection) -> dict:
    cities = _rows(con, """
        select city_id as id, city_name as name, province, region, is_capital, latitude, longitude,
               grid_elevation_m, first_date, last_date, north_to_south_rank as rank
        from marts.dim_city order by north_to_south_rank
    """)
    warming = _rows(con, "select * from marts.mart_city_warming order by north_to_south_rank")
    regions = _rows(con, """
        select area, year, anomaly_c as anomaly, anomaly_10y_rolling_c as rolling
        from marts.mart_region_annual order by area, year
    """)
    indicator_rows = _rows(con, """
        select indicator, city_id, year, baseline_value as baseline, change,
               change_10y_rolling as rolling
        from marts.mart_city_indicator_annual order by indicator, city_id, year
    """)
    # {indicador: {ciudad: {baseline, year: [...], change: [...], rolling: [...]}}}
    indicators: dict[str, dict] = {}
    for r in indicator_rows:
        series = indicators.setdefault(r["indicator"], {}).setdefault(
            r["city_id"], {"baseline": r["baseline"], "year": [], "change": [], "rolling": []}
        )
        for f in ("year", "change", "rolling"):
            series[f].append(r[f])
    first = warming[0]
    return {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data_through": max(c["last_date"] for c in cities if c["last_date"]),
            "first_year": first["first_year"],
            "last_year": first["last_year"],
            "baseline": [1961, 1990],
            "recent": [first["recent_start_year"], first["recent_end_year"]],
            "source": "Open-Meteo Historical Weather API — reanálisis ERA5 (ECMWF/Copernicus)",
        },
        "cities": cities,
        "warming": warming,
        "regions": _columnar(regions, "area", ["year", "anomaly", "rolling"]),
        "indicators": indicators,
    }


def run(db_path: Path = config.DB_PATH, site_dir: Path = config.SITE_DIR) -> Path:
    # Sin read_only a propósito: en `clima run`, dbt corre en este mismo proceso y deja abierta su
    # conexión de lectura-escritura; DuckDB no admite otra con distinta configuración al mismo archivo.
    with duckdb.connect(str(db_path)) as con:
        dataset = build_dataset(con)
    site_dir.mkdir(parents=True, exist_ok=True)
    for item in config.DASHBOARD_DIR.iterdir():
        if item.is_file():
            shutil.copy2(item, site_dir / item.name)
    out = site_dir / "data.json"
    out.write_text(json.dumps(dataset, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log.info("Export: %s (%.0f KB)", out, out.stat().st_size / 1024)
    return out
