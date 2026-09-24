import json

import httpx
import pytest

from fiado.alerts import Alert, AlertKind
from fiado.notifier import LogNotifier, NotifierError, NtfyNotifier, build_notifier
from fiado.settings import Settings

pytestmark = pytest.mark.unit

ALERT = Alert(
    kind=AlertKind.DUE_TODAY,
    title="Vence hoje: José",
    message="Prazo de José finaliza hoje. Está devendo R$ 300,00.",
    priority=4,
    tags=("alarm_clock",),
)


def ntfy(handler, server="https://ntfy.sh/"):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return NtfyNotifier("silmodas-secreto", server, client)


def test_posts_json_to_server_root_preserving_accents():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={})

    ntfy(handler).send(ALERT)

    assert seen["url"] == "https://ntfy.sh"
    assert seen["body"] == {
        "topic": "silmodas-secreto",
        "title": "Vence hoje: José",
        "message": "Prazo de José finaliza hoje. Está devendo R$ 300,00.",
        "priority": 4,
        "tags": ["alarm_clock"],
    }


def test_server_error_becomes_notifier_error():
    with pytest.raises(NotifierError):
        ntfy(lambda request: httpx.Response(503)).send(ALERT)


def test_network_error_becomes_notifier_error():
    def handler(request):
        raise httpx.ConnectError("sem internet")

    with pytest.raises(NotifierError, match="sem internet"):
        ntfy(handler).send(ALERT)


def test_build_notifier_picks_implementation_from_settings():
    assert isinstance(build_notifier(Settings()), LogNotifier)
    assert isinstance(build_notifier(Settings(ntfy_topic="abc")), NtfyNotifier)


def test_log_notifier_logs(caplog):
    with caplog.at_level("INFO"):
        LogNotifier().send(ALERT)
    assert "Prazo de José finaliza hoje" in caplog.text
