"""Quando avisar e o que dizer. Valores-limite: 0, 1, 2, 3, 4 dias e passado."""

from datetime import date, timedelta

import pytest

from fiado.alerts import TEST_ALERT, AlertKind, alert_for
from fiado.domain import Debt

pytestmark = pytest.mark.unit

HOJE = date(2026, 3, 15)


def debt(days_from_today: int, *, name="Bruno", amount=30_000, paid=0) -> Debt:
    return Debt(
        customer=name,
        description="",
        amount_cents=amount,
        paid_cents=paid,
        due_date=HOJE + timedelta(days=days_from_today),
        created_at=HOJE - timedelta(days=30),
        id=1,
    )


def test_due_today_message_is_the_one_the_owner_asked_for():
    alert = alert_for(debt(0), HOJE, (3, 1))
    assert alert.kind is AlertKind.DUE_TODAY
    assert alert.message == "Prazo de Bruno finaliza hoje. Está devendo R$ 300,00."
    assert alert.priority == 4


def test_overdue_says_how_long_and_how_much():
    alert = alert_for(debt(-2), HOJE, (3, 1))
    assert alert.kind is AlertKind.OVERDUE
    assert alert.message == "Prazo de Bruno venceu há 2 dias (13/03). Está devendo R$ 300,00."
    assert alert.priority == 5


def test_overdue_singular():
    assert "há 1 dia (" in alert_for(debt(-1), HOJE, (3, 1)).message


def test_tomorrow():
    alert = alert_for(debt(1), HOJE, (3, 1))
    assert alert.kind is AlertKind.UPCOMING
    assert alert.message == "Prazo de Bruno finaliza amanhã. Está devendo R$ 300,00."
    assert alert.title == "Vence amanhã: Bruno"


def test_three_days_ahead():
    alert = alert_for(debt(3), HOJE, (3, 1))
    assert alert.message == "Prazo de Bruno finaliza em 3 dias (18/03). Está devendo R$ 300,00."
    assert alert.title == "Vence em 3 dias: Bruno"


@pytest.mark.parametrize("days", [2, 4, 10, 365])
def test_days_outside_warn_list_stay_quiet(days):
    assert alert_for(debt(days), HOJE, (3, 1)) is None


def test_warn_days_are_configurable():
    assert alert_for(debt(2), HOJE, (2,)) is not None
    assert alert_for(debt(3), HOJE, ()) is None


def test_paid_debt_never_alerts_even_when_past_due():
    assert alert_for(debt(-5, paid=30_000), HOJE, (3, 1)) is None
    assert alert_for(debt(0, paid=30_000), HOJE, (3, 1)) is None


def test_message_shows_remaining_balance_not_original_amount():
    alert = alert_for(debt(0, amount=30_000, paid=10_050), HOJE, (3, 1))
    assert "R$ 199,50" in alert.message


def test_test_alert_has_its_own_kind():
    assert TEST_ALERT.kind is AlertKind.TEST
