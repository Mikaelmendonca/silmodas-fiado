"""Casos de uso. O relógio é injetado para os testes controlarem "hoje"."""

from __future__ import annotations

import logging
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import date

from fiado.alerts import alert_for
from fiado.domain import Debt, DebtNotFound, Status, new_debt, resolve_due_date
from fiado.notifier import Notifier, NotifierError
from fiado.repository import SqliteDebtRepository

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Summary:
    total_open_cents: int
    total_overdue_cents: int
    due_today_count: int
    overdue_count: int


@dataclass(frozen=True)
class AlertReport:
    sent: int
    failed: int


class DebtService:
    def __init__(self, repo: SqliteDebtRepository, today: Callable[[], date] = date.today) -> None:
        self._repo = repo
        self._today = today

    def close(self) -> None:
        self._repo.close()

    def today(self) -> date:
        return self._today()

    def create(
        self,
        *,
        customer: str,
        description: str,
        amount_cents: int,
        due_date: date | None = None,
        term_days: int | None = None,
        phone: str | None = None,
    ) -> Debt:
        today = self._today()
        debt = new_debt(
            customer=customer,
            description=description,
            amount_cents=amount_cents,
            due_date=resolve_due_date(due_date=due_date, term_days=term_days, today=today),
            today=today,
            phone=phone,
        )
        return self._repo.add(debt)

    def get(self, debt_id: int) -> Debt:
        debt = self._repo.get(debt_id)
        if debt is None:
            raise DebtNotFound(f"Fiado {debt_id} não encontrado.")
        return debt

    def list_debts(self, status: Status | None = None) -> list[Debt]:
        today = self._today()
        debts = self._repo.list_all()
        if status is not None:
            debts = [d for d in debts if d.status(today) is status]
        return debts

    def pay(self, debt_id: int, amount_cents: int) -> Debt:
        updated = self.get(debt_id).with_payment(amount_cents)
        self._repo.update_paid(debt_id, updated.paid_cents)
        return updated

    def delete(self, debt_id: int) -> None:
        if not self._repo.delete(debt_id):
            raise DebtNotFound(f"Fiado {debt_id} não encontrado.")

    def reminders(self) -> list[Debt]:
        """O que cobrar hoje: vencidos (mais atrasados primeiro) e depois os que vencem hoje."""
        today = self._today()
        due = [
            d
            for d in self._repo.list_all()
            if d.status(today) in (Status.OVERDUE, Status.DUE_TODAY)
        ]
        return sorted(due, key=lambda d: (d.due_date, d.id))

    def summary(self) -> Summary:
        today = self._today()
        debts = self._repo.list_all()
        open_debts = [d for d in debts if d.status(today) is not Status.PAID]
        overdue = [d for d in open_debts if d.status(today) is Status.OVERDUE]
        return Summary(
            total_open_cents=sum(d.remaining_cents for d in open_debts),
            total_overdue_cents=sum(d.remaining_cents for d in overdue),
            due_today_count=sum(1 for d in open_debts if d.status(today) is Status.DUE_TODAY),
            overdue_count=len(overdue),
        )

    def send_alerts(self, notifier: Notifier, warn_days: Collection[int] = (3, 1)) -> AlertReport:
        """Manda os alertas de hoje que ainda não foram enviados. Idempotente por dia.

        Se uma entrega falha, o alerta não é marcado como enviado: a próxima execução tenta de novo.
        """
        today = self._today()
        sent = failed = 0
        for debt in self._repo.list_all():
            alert = alert_for(debt, today, warn_days)
            if alert is None or debt.id is None:
                continue
            if self._repo.alert_was_sent(debt.id, alert.kind, today):
                continue
            try:
                notifier.send(alert)
            except NotifierError:
                log.exception("Não consegui enviar o alerta de %s", debt.customer)
                failed += 1
                continue
            self._repo.mark_alert_sent(debt.id, alert.kind, today)
            sent += 1
        return AlertReport(sent=sent, failed=failed)
