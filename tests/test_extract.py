from datetime import date

import pytest

from clima.extract import (
    Chunk,
    City,
    OpenMeteoClient,
    RateLimitExceeded,
    history_complete,
    plan_chunks,
    plan_extraction,
    write_raw,
)

BA = City("buenos_aires", "Buenos Aires", -34.6, -58.38)
USH = City("ushuaia", "Ushuaia", -54.8, -68.3)


# --- Planificación ------------------------------------------------------------

def test_plan_chunks_alinea_por_decada():
    chunks = plan_chunks(BA, date(1940, 1, 1), date(1965, 6, 30), years=10)
    assert [(c.start, c.end) for c in chunks] == [
        (date(1940, 1, 1), date(1949, 12, 31)),
        (date(1950, 1, 1), date(1959, 12, 31)),
        (date(1960, 1, 1), date(1965, 6, 30)),
    ]


def test_plan_chunks_arranca_a_mitad_de_decada():
    chunks = plan_chunks(BA, date(2026, 8, 1), date(2026, 10, 31))
    assert [(c.start, c.end) for c in chunks] == [(date(2026, 8, 1), date(2026, 10, 31))]


def test_plan_chunks_vacio_si_start_mayor_que_end():
    assert plan_chunks(BA, date(2026, 11, 1), date(2026, 10, 31)) == []


def test_plan_extraction_backfill_completo_sin_watermark(tmp_path):
    chunks = plan_extraction([BA], watermarks={}, today=date(2026, 11, 7), raw_dir=tmp_path)
    assert chunks[0].start == date(1940, 1, 1)
    assert chunks[-1].end == date(2026, 10, 31)  # hoy - 7 días
    assert len(chunks) == 9  # 1940s … 2020s


def test_plan_extraction_incremental_usa_ventana_de_refresco(tmp_path):
    chunks = plan_extraction(
        [BA], watermarks={"buenos_aires": date(2026, 10, 24)}, today=date(2026, 11, 7), raw_dir=tmp_path
    )
    assert [(c.start, c.end) for c in chunks] == [(date(2026, 7, 26), date(2026, 10, 31))]


def test_plan_extraction_saltea_decadas_cerradas_ya_descargadas(tmp_path):
    done = Chunk(BA, date(1940, 1, 1), date(1949, 12, 31))
    write_raw(done, {"daily": {}}, raw_dir=tmp_path)

    chunks = plan_extraction([BA, USH], watermarks={}, today=date(2026, 11, 7), raw_dir=tmp_path)

    ba_starts = [c.start for c in chunks if c.city == BA]
    assert date(1940, 1, 1) not in ba_starts
    assert len(ba_starts) == 8
    assert len([c for c in chunks if c.city == USH]) == 9  # la otra ciudad no se ve afectada


def test_plan_extraction_redescarga_chunk_abierto_aunque_exista(tmp_path):
    open_chunk = Chunk(BA, date(2020, 1, 1), date(2026, 10, 31))
    write_raw(open_chunk, {"daily": {}}, raw_dir=tmp_path)

    chunks = plan_extraction([BA], watermarks={}, today=date(2026, 11, 7), raw_dir=tmp_path)
    assert chunks[-1].start == date(2020, 1, 1)


# --- ¿Se puede publicar aunque la API haya cortado? -------------------------------

def test_history_complete_con_todas_las_ciudades_al_dia():
    wm = {"buenos_aires": date(2026, 10, 31), "ushuaia": date(2026, 10, 20)}
    assert history_complete([BA, USH], wm, today=date(2026, 11, 7))


def test_history_incompleto_si_falta_una_ciudad():
    assert not history_complete([BA, USH], {"buenos_aires": date(2026, 10, 31)}, today=date(2026, 11, 7))


def test_history_incompleto_si_una_ciudad_quedo_a_mitad_del_backfill():
    wm = {"buenos_aires": date(2026, 10, 31), "ushuaia": date(1989, 12, 31)}
    assert not history_complete([BA, USH], wm, today=date(2026, 11, 7))


# --- Cliente HTTP -----------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(params)
        return self.responses.pop(0)


CHUNK = Chunk(BA, date(2020, 1, 1), date(2020, 1, 31))


def make_client(responses):
    sleeps = []
    session = FakeSession(responses)
    client = OpenMeteoClient(session=session, sleep=sleeps.append, max_retries=3)
    return client, session, sleeps


def test_fetch_envia_parametros_esperados():
    client, session, _ = make_client([FakeResponse(200, {"daily": {"time": []}})])
    client.fetch(CHUNK)
    params = session.calls[0]
    assert params["start_date"] == "2020-01-01"
    assert params["end_date"] == "2020-01-31"
    assert params["models"] == "era5"
    assert "temperature_2m_mean" in params["daily"]


def test_fetch_reintenta_errores_5xx():
    client, session, sleeps = make_client(
        [FakeResponse(503, {}), FakeResponse(200, {"daily": {"time": ["2020-01-01"]}})]
    )
    assert client.fetch(CHUNK) == {"daily": {"time": ["2020-01-01"]}}
    assert len(session.calls) == 2
    assert len(sleeps) == 1


def test_fetch_espera_un_minuto_con_limite_por_minuto():
    client, _, sleeps = make_client(
        [
            FakeResponse(429, {"error": True, "reason": "Minutely API request limit exceeded."}),
            FakeResponse(200, {"daily": {}}),
        ]
    )
    client.fetch(CHUNK)
    assert sleeps == [60]


def test_fetch_corta_con_limite_diario():
    client, _, _ = make_client(
        [FakeResponse(429, {"error": True, "reason": "Daily API request limit exceeded."})]
    )
    with pytest.raises(RateLimitExceeded):
        client.fetch(CHUNK)


def test_fetch_no_reintenta_error_400():
    client, session, _ = make_client([FakeResponse(400, {"error": True, "reason": "Parameter bad"})])
    with pytest.raises(RuntimeError, match="Parameter bad"):
        client.fetch(CHUNK)
    assert len(session.calls) == 1


def test_fetch_falla_tras_agotar_reintentos():
    client, session, _ = make_client([FakeResponse(500, {})] * 3)
    with pytest.raises(RuntimeError):
        client.fetch(CHUNK)
    assert len(session.calls) == 3
