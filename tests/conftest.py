from datetime import date

import pytest
from fastapi.testclient import TestClient

from fiado.alerts import Alert
from fiado.api import create_app
from fiado.notifier import NotifierError
from fiado.repository import SqliteDebtRepository
from fiado.service import DebtService
from fiado.settings import Settings

HOJE = date(2026, 3, 15)


class FakeClock:
    """Relógio controlável: testes de prazo nunca dependem da data real."""

    def __init__(self, today: date = HOJE) -> None:
        self.current = today

    def __call__(self) -> date:
        return self.current


class FakeNotifier:
    """Guarda o que seria enviado; `fail=True` simula o celular/servidor fora do ar."""

    def __init__(self, *, fail: bool = False) -> None:
        self.sent: list[Alert] = []
        self.fail = fail

    def send(self, alert: Alert) -> None:
        if self.fail:
            raise NotifierError("fora do ar")
        self.sent.append(alert)


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def service(clock: FakeClock):
    svc = DebtService(SqliteDebtRepository(":memory:"), clock)
    yield svc
    svc.close()


@pytest.fixture
def client(clock: FakeClock, notifier: FakeNotifier):
    app = create_app(
        db_path=":memory:",
        today=clock,
        settings=Settings(ntfy_topic="teste"),
        notifier=notifier,
        schedule_alerts=False,
    )
    with TestClient(app) as c:
        yield c
