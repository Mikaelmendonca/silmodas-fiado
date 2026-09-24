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


def test_backup_command_saves_a_copy(env, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("FIADO_BACKUP_DIR", str(tmp_path / "copias"))
    cli.main(["seed"])
    assert cli.main(["backup"]) == 0
    saved = list((tmp_path / "copias").glob("fiado-*.db"))
    assert len(saved) == 1 and "Backup salvo em" in capsys.readouterr().out


def test_serve_refuses_to_open_to_the_network_without_password(env, monkeypatch, capsys):
    monkeypatch.delenv("FIADO_PASSWORD", raising=False)
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **kw: pytest.fail("não deveria subir"))
    assert cli.main(["serve", "--host", "0.0.0.0"]) == 2
    assert "FIADO_PASSWORD" in capsys.readouterr().out


def test_serve_on_the_network_with_password_shows_the_phone_address(env, monkeypatch, capsys):
    monkeypatch.setenv("FIADO_PASSWORD", "segredo1")
    monkeypatch.setattr(cli, "_lan_ip", lambda: "192.168.0.15")
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **kw: None)
    assert cli.main(["serve", "--host", "0.0.0.0", "--port", "8123"]) == 0
    out = capsys.readouterr().out
    assert "http://192.168.0.15:8123" in out and "segredo1" not in out


def test_serve_only_on_this_computer_needs_no_password(env, monkeypatch, capsys):
    monkeypatch.delenv("FIADO_PASSWORD", raising=False)
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **kw: None)
    assert cli.main(["serve"]) == 0
    assert "192." not in capsys.readouterr().out  # não anuncia endereço de rede


def test_lan_ip_returns_an_address_or_none_and_never_raises(monkeypatch):
    assert cli._lan_ip() is None or cli._lan_ip().count(".") == 3

    class Broken:
        def __enter__(self):
            raise OSError("sem rede")

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(cli.socket, "socket", lambda *a, **kw: Broken())
    assert cli._lan_ip() is None
