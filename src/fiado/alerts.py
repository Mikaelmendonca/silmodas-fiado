"""Regra de quando avisar e o que dizer. Puro: sem rede, sem banco, sem relógio."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from fiado.domain import Debt, Status, format_brl


class AlertKind(StrEnum):
    UPCOMING = "upcoming"  # faltam poucos dias
    DUE_TODAY = "due_today"  # o prazo acaba hoje
    OVERDUE = "overdue"  # já passou do prazo
    TEST = "test"  # botão "testar no celular"


@dataclass(frozen=True)
class Alert:
    kind: AlertKind
    title: str
    message: str
    priority: int  # escala do ntfy: 1 (mínima) a 5 (urgente)
    tags: tuple[str, ...] = ()


TEST_ALERT = Alert(
    kind=AlertKind.TEST,
    title="Silmodas",
    message="Teste: as notificações estão chegando no celular!",
    priority=3,
    tags=("white_check_mark",),
)


def alert_for(debt: Debt, today: date, warn_days: Collection[int]) -> Alert | None:
    """Alerta que este fiado merece hoje, ou None se não há nada a avisar.

    - Vencido: avisa todo dia até quitar.
    - Vence hoje: avisa.
    - Faltando N dias: avisa só se N estiver em `warn_days` (padrão: 3 e 1).
    """
    status = debt.status(today)
    if status is Status.PAID:
        return None

    who = debt.customer
    owed = f"Está devendo {format_brl(debt.remaining_cents)}."

    if status is Status.OVERDUE:
        days = debt.days_overdue(today)
        unit = "dia" if days == 1 else "dias"
        return Alert(
            kind=AlertKind.OVERDUE,
            title=f"Atrasado: {who}",
            message=f"Prazo de {who} venceu há {days} {unit} ({_short(debt.due_date)}). {owed}",
            priority=5,
            tags=("rotating_light",),
        )

    if status is Status.DUE_TODAY:
        return Alert(
            kind=AlertKind.DUE_TODAY,
            title=f"Vence hoje: {who}",
            message=f"Prazo de {who} finaliza hoje. {owed}",
            priority=4,
            tags=("alarm_clock",),
        )

    days_left = (debt.due_date - today).days
    if days_left not in warn_days:
        return None
    when = "amanhã" if days_left == 1 else f"em {days_left} dias ({_short(debt.due_date)})"
    return Alert(
        kind=AlertKind.UPCOMING,
        title=f"Vence {'amanhã' if days_left == 1 else f'em {days_left} dias'}: {who}",
        message=f"Prazo de {who} finaliza {when}. {owed}",
        priority=3,
        tags=("calendar",),
    )


def _short(d: date) -> str:
    return d.strftime("%d/%m")
