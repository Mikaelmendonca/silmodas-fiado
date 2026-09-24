from datetime import timedelta

import pytest

from fiado.domain import DebtNotFound, PaymentExceedsBalance, Status, ValidationError
from fiado.notifier import NotifierError

pytestmark = pytest.mark.unit


def add(service, clock, customer="Ana", amount=10_000, days=0, **kw):
    return service.create(
        customer=customer,
        description="",
        amount_cents=amount,
        due_date=clock.current + timedelta(days=days),
        **kw,
    )


def test_create_assigns_id_and_persists(service, clock):
    created = add(service, clock)
    assert created.id is not None
    assert service.get(created.id).customer == "Ana"


def test_create_propagates_validation_error(service, clock):
    with pytest.raises(ValidationError):
        add(service, clock, customer=" ")


def test_get_missing_raises(service):
    with pytest.raises(DebtNotFound):
        service.get(999)


def test_pay_persists(service, clock):
    d = add(service, clock, amount=10_000)
    service.pay(d.id, 3_000)
    assert service.get(d.id).remaining_cents == 7_000


def test_pay_overpayment_does_not_change_balance(service, clock):
    d = add(service, clock, amount=10_000)
    with pytest.raises(PaymentExceedsBalance):
        service.pay(d.id, 10_001)
    assert service.get(d.id).paid_cents == 0


def test_delete(service, clock):
    d = add(service, clock)
    service.delete(d.id)
    with pytest.raises(DebtNotFound):
        service.get(d.id)


def test_delete_missing_raises(service):
    with pytest.raises(DebtNotFound):
        service.delete(1)


def test_list_filters_by_status(service, clock):
    add(service, clock, "Hoje", days=0)
    add(service, clock, "Futuro", days=10)
    assert [d.customer for d in service.list_debts(Status.DUE_TODAY)] == ["Hoje"]
    assert len(service.list_debts()) == 2


def test_reminders_empty_when_nothing_due(service, clock):
    add(service, clock, days=1)
    assert service.reminders() == []


def test_reminders_include_due_today_and_overdue_most_late_first(service, clock):
    add(service, clock, "Vence hoje", days=0)
    add(service, clock, "Futuro", days=5)
    add(service, clock, "Vence em 2 dias", days=2)
    clock.current += timedelta(days=5)  # passam 5 dias
    names = [d.customer for d in service.reminders()]
    # "Vence hoje" (5d de atraso), "Vence em 2 dias" (3d), "Futuro" (vence hoje)
    assert names == ["Vence hoje", "Vence em 2 dias", "Futuro"]


def test_reminders_exclude_paid(service, clock):
    d = add(service, clock, amount=5_000, days=0)
    service.pay(d.id, 5_000)
    assert service.reminders() == []


def test_reminder_appears_exactly_on_due_date(service, clock):
    add(service, clock, days=3)
    for _ in range(2):
        clock.current += timedelta(days=1)
        assert service.reminders() == []
    clock.current += timedelta(days=1)
    assert len(service.reminders()) == 1


def test_summary(service, clock):
    a = add(service, clock, "Atrasado", amount=10_000, days=0)
    add(service, clock, "Hoje", amount=2_000, days=1)
    add(service, clock, "Futuro", amount=500, days=30)
    service.pay(a.id, 2_500)
    clock.current += timedelta(days=1)
    s = service.summary()
    assert s.total_open_cents == 7_500 + 2_000 + 500
    assert s.total_overdue_cents == 7_500
    assert (s.overdue_count, s.due_today_count) == (1, 1)


def test_summary_empty(service):
    s = service.summary()
    assert (s.total_open_cents, s.overdue_count, s.due_today_count) == (0, 0, 0)


# --- prazo em dias -----------------------------------------------------------------------------


def test_create_with_term_days_computes_due_date(service, clock):
    d = service.create(customer="Bruno", description="", amount_cents=30_000, term_days=30)
    assert d.due_date == clock.current + timedelta(days=30)
    assert d.term_days == 30


def test_term_zero_means_due_today(service, clock):
    d = service.create(customer="Bruno", description="", amount_cents=100, term_days=0)
    assert d.due_date == clock.current and d.status(clock.current) is Status.DUE_TODAY


def test_explicit_due_date_wins_over_term(service, clock):
    d = service.create(
        customer="Bruno",
        description="",
        amount_cents=100,
        due_date=clock.current + timedelta(days=5),
        term_days=99,
    )
    assert d.term_days == 5


@pytest.mark.parametrize("term", [-1, 3651, 10**9])
def test_term_out_of_range_is_rejected(service, term):
    with pytest.raises(ValidationError):
        service.create(customer="Bruno", description="", amount_cents=100, term_days=term)


def test_neither_due_date_nor_term_is_rejected(service):
    with pytest.raises(ValidationError, match="vencimento ou o prazo"):
        service.create(customer="Bruno", description="", amount_cents=100)


# --- alertas -----------------------------------------------------------------------------------


class TestSendAlerts:
    def test_sends_only_what_is_due_and_reports_count(self, service, clock, notifier):
        add(service, clock, "Hoje", days=0)
        add(service, clock, "Amanha", days=1)
        add(service, clock, "Longe", days=20)
        report = service.send_alerts(notifier, (3, 1))
        assert (report.sent, report.failed) == (2, 0)
        assert {a.title for a in notifier.sent} == {"Vence hoje: Hoje", "Vence amanhã: Amanha"}

    def test_running_twice_the_same_day_does_not_duplicate(self, service, clock, notifier):
        add(service, clock, "Bruno", days=0)
        service.send_alerts(notifier, (3, 1))
        again = service.send_alerts(notifier, (3, 1))
        assert again.sent == 0 and len(notifier.sent) == 1

    def test_next_day_alerts_again(self, service, clock, notifier):
        add(service, clock, "Bruno", days=0)
        service.send_alerts(notifier, (3, 1))
        clock.current += timedelta(days=1)  # agora está atrasado
        service.send_alerts(notifier, (3, 1))
        assert [a.kind for a in notifier.sent] == ["due_today", "overdue"]

    def test_countdown_alerts_fire_on_the_right_days(self, service, clock, notifier):
        add(service, clock, "Bruno", days=4)
        for _ in range(5):
            service.send_alerts(notifier, (3, 1))
            clock.current += timedelta(days=1)
        assert [a.kind for a in notifier.sent] == ["upcoming", "upcoming", "due_today"]

    def test_failed_delivery_is_retried_next_run(self, service, clock, notifier):
        add(service, clock, "Bruno", days=0)
        notifier.fail = True
        report = service.send_alerts(notifier, (3, 1))
        assert (report.sent, report.failed) == (0, 1)
        notifier.fail = False
        assert service.send_alerts(notifier, (3, 1)).sent == 1

    def test_one_failure_does_not_block_the_others(self, service, clock, notifier):
        add(service, clock, "A", days=0)
        add(service, clock, "B", days=0)
        original = notifier.send
        calls = []

        def flaky(alert):
            calls.append(alert)
            if len(calls) == 1:
                raise NotifierError("x")
            original(alert)

        notifier.send = flaky
        report = service.send_alerts(notifier, (3, 1))
        assert (report.sent, report.failed) == (1, 1)

    def test_paid_debt_is_not_alerted(self, service, clock, notifier):
        d = add(service, clock, "Bruno", days=0, amount=5_000)
        service.pay(d.id, 5_000)
        assert service.send_alerts(notifier, (3, 1)).sent == 0

    def test_deleting_a_debt_removes_its_alert_history(self, service, clock, notifier):
        d = add(service, clock, "Bruno", days=0)
        service.send_alerts(notifier, (3, 1))
        service.delete(d.id)  # não pode falhar por causa da chave estrangeira
        assert service.list_debts() == []
