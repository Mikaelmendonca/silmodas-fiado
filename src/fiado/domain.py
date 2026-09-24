"""Regras de negócio do fiado. Sem I/O: tudo aqui é puro e fácil de testar."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from enum import StrEnum
from urllib.parse import quote


class FiadoError(Exception):
    """Base para erros de regra de negócio."""


class ValidationError(FiadoError):
    """Dado de entrada inválido."""


class PaymentExceedsBalance(FiadoError):
    """Pagamento maior que o valor que ainda falta pagar."""


class DebtNotFound(FiadoError):
    """Fiado inexistente."""


class Status(StrEnum):
    PENDING = "pending"  # ainda dentro do prazo
    DUE_TODAY = "due_today"  # vence hoje: cobrar hoje
    OVERDUE = "overdue"  # passou do prazo
    PAID = "paid"  # quitado


@dataclass(frozen=True)
class Debt:
    customer: str
    description: str
    amount_cents: int
    due_date: date
    created_at: date
    phone: str | None = None
    paid_cents: int = 0
    id: int | None = None

    @property
    def remaining_cents(self) -> int:
        return self.amount_cents - self.paid_cents

    @property
    def term_days(self) -> int:
        """Prazo combinado, em dias, entre a compra e o vencimento."""
        return (self.due_date - self.created_at).days

    def status(self, today: date) -> Status:
        if self.remaining_cents == 0:
            return Status.PAID
        if self.due_date < today:
            return Status.OVERDUE
        if self.due_date == today:
            return Status.DUE_TODAY
        return Status.PENDING

    def days_overdue(self, today: date) -> int:
        """Dias de atraso; 0 se ainda não venceu ou se já foi pago."""
        if self.status(today) is not Status.OVERDUE:
            return 0
        return (today - self.due_date).days

    def with_payment(self, amount_cents: int) -> Debt:
        if amount_cents <= 0:
            raise ValidationError("O valor do pagamento deve ser maior que zero.")
        if amount_cents > self.remaining_cents:
            raise PaymentExceedsBalance(
                f"Pagamento de {amount_cents} centavos excede o saldo de "
                f"{self.remaining_cents} centavos."
            )
        return replace(self, paid_cents=self.paid_cents + amount_cents)


MAX_TERM_DAYS = 3650
MAX_AMOUNT_CENTS = 1_000_000_000  # R$ 10 milhões: acima disso é erro de digitação


def resolve_due_date(*, due_date: date | None, term_days: int | None, today: date) -> date:
    """Vencimento explícito tem prioridade; senão, hoje + prazo em dias."""
    if due_date is not None:
        return due_date
    if term_days is None:
        raise ValidationError("Informe o vencimento ou o prazo em dias.")
    if not 0 <= term_days <= MAX_TERM_DAYS:
        raise ValidationError(f"O prazo deve estar entre 0 e {MAX_TERM_DAYS} dias.")
    return today + timedelta(days=term_days)


def new_debt(
    *,
    customer: str,
    description: str,
    amount_cents: int,
    due_date: date,
    today: date,
    phone: str | None = None,
) -> Debt:
    """Cria um fiado validando as regras de entrada."""
    customer = customer.strip()
    if not customer:
        raise ValidationError("O nome do cliente é obrigatório.")
    if amount_cents <= 0:
        raise ValidationError("O valor deve ser maior que zero.")
    if amount_cents > MAX_AMOUNT_CENTS:
        raise ValidationError(f"O valor máximo é {format_brl(MAX_AMOUNT_CENTS)}.")
    if due_date < today:
        raise ValidationError("A data de vencimento não pode estar no passado.")
    if due_date > today + timedelta(days=MAX_TERM_DAYS):
        raise ValidationError(
            f"O vencimento não pode passar de {MAX_TERM_DAYS} dias a partir de hoje."
        )
    if phone is not None and phone.strip():
        phone = normalize_phone(phone)
    else:
        phone = None
    return Debt(
        customer=customer,
        description=description.strip(),
        amount_cents=amount_cents,
        due_date=due_date,
        created_at=today,
        phone=phone,
    )


def normalize_phone(raw: str) -> str:
    """Devolve só dígitos com DDI 55. Aceita '(11) 91234-5678', '+55 11 91234-5678' etc.

    Regras: DDD de 2 dígitos (11-99); celular tem 9 dígitos e começa com 9; fixo tem 8 e
    começa com 2-5. Números internacionais (+1, +351...) são recusados.
    """
    raw = raw.strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if raw.startswith("+") and not digits.startswith("55"):
        raise ValidationError(_PHONE_ERROR)
    if len(digits) in (12, 13) and digits.startswith("55"):
        digits = digits[2:]
    if not _is_valid_national(digits):
        raise ValidationError(_PHONE_ERROR)
    return "55" + digits


_PHONE_ERROR = "Telefone inválido. Use DDD + número, ex.: (11) 91234-5678."


def _is_valid_national(digits: str) -> bool:
    if len(digits) not in (10, 11) or digits[0] == "0" or digits[1] == "0":
        return False
    subscriber = digits[2:]
    if len(subscriber) == 9:
        return subscriber[0] == "9"
    return subscriber[0] in "2345"


def format_brl(cents: int) -> str:
    reais, centavos = divmod(cents, 100)
    return f"R$ {reais:,}".replace(",", ".") + f",{centavos:02d}"


def reminder_message(debt: Debt, today: date) -> str:
    """Texto educado de cobrança, pronto para mandar no WhatsApp."""
    saldo = format_brl(debt.remaining_cents)
    vencimento = debt.due_date.strftime("%d/%m/%Y")
    status = debt.status(today)
    if status is Status.OVERDUE:
        dias = debt.days_overdue(today)
        plural = "dia" if dias == 1 else "dias"
        return (
            f"Olá, {debt.customer}! Tudo bem? Passando para lembrar do valor de {saldo} "
            f"que venceu em {vencimento} (há {dias} {plural}). "
            "Podemos combinar o pagamento? Obrigada!"
        )
    return (
        f"Olá, {debt.customer}! Tudo bem? Lembrando que o valor de {saldo} "
        f"vence em {vencimento}. Obrigada!"
    )


def whatsapp_link(debt: Debt, today: date) -> str | None:
    if debt.phone is None:
        return None
    return f"https://wa.me/{debt.phone}?text={quote(reminder_message(debt, today))}"
