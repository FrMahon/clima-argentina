import time
from datetime import date

import pytest

from clima import warehouse
from clima.extract import Chunk, City, write_raw

BA = City("buenos_aires", "Buenos Aires", -34.6, -58.38)


def api_payload(days, means):
    return {
        "latitude": -34.5,
        "longitude": -58.5,
        "elevation": 37.0,
        "daily": {
            "time": days,
            "temperature_2m_mean": means,
            "temperature_2m_max": [None if m is None else m + 5 for m in means],
            "temperature_2m_min": [None if m is None else m - 5 for m in means],
            "precipitation_sum": [0.0 for _ in means],
        },
    }


@pytest.fixture
def con(tmp_path):
    c = warehouse.connect(tmp_path / "test.duckdb")
    yield c
    c.close()


def rows(con):
    return con.execute(
        "select date::varchar, temperature_2m_mean from raw.open_meteo_daily order by date"
    ).fetchall()


def test_carga_archivo_crudo(con, tmp_path):
    chunk = Chunk(BA, date(2020, 1, 1), date(2020, 1, 3))
    write_raw(chunk, api_payload(["2020-01-01", "2020-01-02", "2020-01-03"], [20.0, 21.0, 22.0]), tmp_path)

    loaded = warehouse.load_raw_files(con, tmp_path)

    assert loaded == 3
    assert rows(con) == [("2020-01-01", 20.0), ("2020-01-02", 21.0), ("2020-01-03", 22.0)]
    grid = con.execute("select distinct grid_latitude, grid_elevation_m, model from raw.open_meteo_daily").fetchall()
    assert grid == [(-34.5, 37.0, "era5")]


def test_recarga_es_idempotente(con, tmp_path):
    chunk = Chunk(BA, date(2020, 1, 1), date(2020, 1, 2))
    write_raw(chunk, api_payload(["2020-01-01", "2020-01-02"], [20.0, 21.0]), tmp_path)

    warehouse.load_raw_files(con, tmp_path)
    assert warehouse.load_raw_files(con, tmp_path) == 0  # el archivo ya figura en el log
    assert len(rows(con)) == 2


def test_archivo_mas_nuevo_pisa_dias_solapados(con, tmp_path):
    old = Chunk(BA, date(2020, 1, 1), date(2020, 1, 2))
    write_raw(old, api_payload(["2020-01-01", "2020-01-02"], [20.0, 21.0]), tmp_path)
    warehouse.load_raw_files(con, tmp_path)

    time.sleep(1.1)  # el timestamp de extracción va en el nombre del archivo
    new = Chunk(BA, date(2020, 1, 2), date(2020, 1, 3))
    write_raw(new, api_payload(["2020-01-02", "2020-01-03"], [25.0, 26.0]), tmp_path)
    warehouse.load_raw_files(con, tmp_path)

    assert rows(con) == [("2020-01-01", 20.0), ("2020-01-02", 25.0), ("2020-01-03", 26.0)]


def test_descarta_dias_sin_datos(con, tmp_path):
    chunk = Chunk(BA, date(2020, 1, 1), date(2020, 1, 2))
    write_raw(chunk, api_payload(["2020-01-01", "2020-01-02"], [20.0, None]), tmp_path)

    warehouse.load_raw_files(con, tmp_path)
    assert rows(con) == [("2020-01-01", 20.0)]


def test_watermarks_por_ciudad(con, tmp_path):
    assert warehouse.get_watermarks(con) == {}
    chunk = Chunk(BA, date(2020, 1, 1), date(2020, 1, 2))
    write_raw(chunk, api_payload(["2020-01-01", "2020-01-02"], [20.0, 21.0]), tmp_path)
    warehouse.load_raw_files(con, tmp_path)

    assert warehouse.get_watermarks(con) == {"buenos_aires": date(2020, 1, 2)}
