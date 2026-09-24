"""Infra dos testes ponta a ponta: um servidor real por teste + navegador Playwright.

Cada teste sobe a aplicação de verdade (uvicorn numa thread) com banco em memória e um
celular falso, então os testes são independentes e ainda provam o caminho completo:
navegador -> HTML/JS -> API -> banco -> notificação.
"""

import socket
import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn

from fiado.api import create_app
from fiado.settings import Settings
from tests.e2e.helpers import TZ


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "/tests/e2e/" in str(item.path).replace("\\", "/"):
            item.add_marker(pytest.mark.e2e)


@pytest.fixture
def live_server(notifier) -> Iterator[str]:
    app = create_app(
        db_path=":memory:",
        settings=Settings(ntfy_topic="e2e", timezone=TZ),
        notifier=notifier,
        schedule_alerts=False,
    )
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("O servidor de teste não subiu em 10s")
        time.sleep(0.02)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict) -> dict:
    # Mesmo fuso e idioma do servidor: "hoje" e "R$ 300,00" saem iguais no navegador.
    return {**browser_context_args, "timezone_id": TZ, "locale": "pt-BR"}
