import pytest

from clima import cli, extract


@pytest.fixture
def calls(monkeypatch):
    log = []
    monkeypatch.delenv("CLIMA_SKIP_EXTRACT", raising=False)
    monkeypatch.setattr(cli, "cmd_load", lambda: log.append("load") or 0)
    monkeypatch.setattr(cli, "cmd_transform", lambda: log.append("transform") or 0)
    monkeypatch.setattr(cli, "cmd_export", lambda: log.append("export") or 0)
    monkeypatch.setattr(cli.warehouse, "connect", lambda: _Con())
    monkeypatch.setattr(cli.warehouse, "get_watermarks", lambda con: {})
    monkeypatch.setattr(extract, "read_cities", lambda *a: [])
    return log


class _Con:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_run_completo_si_la_api_responde(calls, monkeypatch):
    monkeypatch.setattr(cli, "cmd_extract", lambda: 0)
    assert cli.cmd_run() == 0
    assert calls == ["load", "transform", "export"]


def test_run_corta_sin_publicar_si_la_api_corta_y_el_historico_esta_incompleto(calls, monkeypatch):
    monkeypatch.setattr(cli, "cmd_extract", lambda: cli.EXIT_RATE_LIMIT)
    monkeypatch.setattr(extract, "history_complete", lambda *a: False)
    assert cli.cmd_run() == cli.EXIT_RATE_LIMIT
    assert calls == ["load"]


def test_run_publica_si_la_api_corta_pero_el_historico_esta_completo(calls, monkeypatch):
    monkeypatch.setattr(cli, "cmd_extract", lambda: cli.EXIT_RATE_LIMIT)
    monkeypatch.setattr(extract, "history_complete", lambda *a: True)
    assert cli.cmd_run() == 0
    assert calls == ["load", "transform", "export"]


def test_run_no_llama_a_la_api_con_skip_extract(calls, monkeypatch):
    monkeypatch.setenv("CLIMA_SKIP_EXTRACT", "1")
    monkeypatch.setattr(cli, "cmd_extract", lambda: pytest.fail("no debe extraer"))
    assert cli.cmd_run() == 0
    assert calls == ["load", "transform", "export"]
