import pytest

from fiado import __main__ as cli

pytestmark = pytest.mark.unit


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("FIADO_DB", str(tmp_path / "t.db"))
    monkeypatch.delenv("FIADO_NTFY_TOPIC", raising=False)
    monkeypatch.chdir(tmp_path)  # evita ler um .env real do projeto


def test_seed_then_alerts(env, capsys):
    assert cli.main(["seed"]) == 0
    assert cli.main(["alerts"]) == 0
    out = capsys.readouterr().out
    assert "Dados de exemplo criados" in out
    assert "4 alerta(s) enviado(s), 0 falha(s)" in out  # hoje, amanhã, em 3 dias, atrasado
    cli.main(["alerts"])
    assert "0 alerta(s) enviado(s)" in capsys.readouterr().out


def test_test_command_without_topic_only_logs(env, capsys):
    assert cli.main(["test"]) == 0
    assert "Sem FIADO_NTFY_TOPIC" in capsys.readouterr().out


def test_test_command_reports_failure(env, monkeypatch, capsys):
    from fiado.notifier import NotifierError

    class Broken:
        def send(self, alert):
            raise NotifierError("sem rede")

    monkeypatch.setattr(cli, "build_notifier", lambda settings: Broken())
    assert cli.main(["test"]) == 1
    assert "Falhou: sem rede" in capsys.readouterr().out


def test_test_command_with_topic(env, monkeypatch, capsys):
    monkeypatch.setenv("FIADO_NTFY_TOPIC", "abc")
    monkeypatch.setattr(
        cli, "build_notifier", lambda settings: type("N", (), {"send": lambda s, a: None})()
    )
    assert cli.main(["test"]) == 0
    assert "Enviado!" in capsys.readouterr().out


def test_alerts_command_returns_error_code_when_delivery_fails(env, monkeypatch):
    from fiado.notifier import NotifierError

    class Broken:
        def send(self, alert):
            raise NotifierError("x")

    cli.main(["seed"])
    monkeypatch.setattr(cli, "build_notifier", lambda settings: Broken())
    assert cli.main(["alerts"]) == 1


@pytest.mark.parametrize("topic", [None, "silmodas-abc"])
def test_serve_prints_banner_and_starts_uvicorn(env, monkeypatch, capsys, topic):
    if topic:
        monkeypatch.setenv("FIADO_NTFY_TOPIC", topic)
    started = {}
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **kw: started.update(kw))
    assert cli.main(["serve", "--port", "9999"]) == 0
    assert started["port"] == 9999 and started["host"] == "127.0.0.1" and started["factory"]
    assert ("ligados" if topic else "DESLIGADOS") in capsys.readouterr().out
