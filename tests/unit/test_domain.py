from datetime import date, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fiado.domain import (
    Debt,
    PaymentExceedsBalance,
    Status,
    ValidationError,
    format_brl,
    new_debt,
    normalize_phone,
    reminder_message,
    whatsapp_link,
)

pytestmark = pytest.mark.unit
HOJE = date(2026, 3, 15)


def make_debt(due: date = HOJE, amount: int = 10_000, paid: int = 0, phone=None) -> Debt:
    return Debt(
        customer="Dona Maria",
        description="compras",
        amount_cents=amount,
        due_date=due,
        created_at=HOJE - timedelta(days=10),
        paid_cents=paid,
        phone=phone,
    )


class TestStatus:
    """Análise de valor-limite em torno da data de vencimento."""

    @pytest.mark.parametrize(
        ("delta_days", "expected"),
        [
            (+30, Status.PENDING),
            (+1, Status.PENDING),  # amanhã: ainda no prazo
            (0, Status.DUE_TODAY),  # hoje: cobrar
            (-1, Status.OVERDUE),  # ontem: atrasado
            (-90, Status.OVERDUE),
        ],
    )
    def test_status_by_due_date(self, delta_days, expected):
        assert make_debt(due=HOJE + timedelta(days=delta_days)).status(HOJE) is expected

    def test_paid_debt_is_paid_even_if_past_due(self):
        debt = make_debt(due=HOJE - timedelta(days=30), paid=10_000)
        assert debt.status(HOJE) is Status.PAID

    def test_partial_payment_keeps_overdue(self):
        debt = make_debt(due=HOJE - timedelta(days=1), paid=9_999)
        assert debt.status(HOJE) is Status.OVERDUE

    def test_status_changes_as_time_passes(self):
        debt = make_debt(due=HOJE + timedelta(days=1))
        assert debt.status(HOJE) is Status.PENDING
        assert debt.status(HOJE + timedelta(days=1)) is Status.DUE_TODAY
        assert debt.status(HOJE + timedelta(days=2)) is Status.OVERDUE

    def test_year_boundary(self):
        debt = make_debt(due=date(2025, 12, 31))
        assert debt.status(date(2026, 1, 1)) is Status.OVERDUE
        assert debt.days_overdue(date(2026, 1, 1)) == 1


class TestDaysOverdue:
    def test_zero_when_not_due(self):
        assert make_debt(due=HOJE + timedelta(days=5)).days_overdue(HOJE) == 0

    def test_zero_when_due_today(self):
        assert make_debt(due=HOJE).days_overdue(HOJE) == 0

    def test_counts_days(self):
        assert make_debt(due=HOJE - timedelta(days=7)).days_overdue(HOJE) == 7

    def test_zero_when_paid(self):
        assert make_debt(due=HOJE - timedelta(days=7), paid=10_000).days_overdue(HOJE) == 0


class TestPayment:
    def test_partial_payment(self):
        debt = make_debt(amount=10_000).with_payment(2_500)
        assert (debt.paid_cents, debt.remaining_cents) == (2_500, 7_500)

    def test_exact_payment_settles(self):
        assert make_debt(amount=10_000).with_payment(10_000).status(HOJE) is Status.PAID

    def test_two_payments_accumulate(self):
        debt = make_debt(amount=10_000).with_payment(4_000).with_payment(6_000)
        assert debt.remaining_cents == 0

    def test_original_is_immutable(self):
        original = make_debt()
        original.with_payment(100)
        assert original.paid_cents == 0

    @pytest.mark.parametrize("bad", [0, -1, -10_000])
    def test_rejects_non_positive(self, bad):
        with pytest.raises(ValidationError):
            make_debt().with_payment(bad)

    def test_rejects_one_cent_over_balance(self):
        with pytest.raises(PaymentExceedsBalance):
            make_debt(amount=10_000).with_payment(10_001)

    def test_rejects_payment_on_settled_debt(self):
        with pytest.raises(PaymentExceedsBalance):
            make_debt(amount=10_000, paid=10_000).with_payment(1)


class TestNewDebt:
    def kwargs(self, **over):
        base = dict(
            customer="João",
            description="fiado",
            amount_cents=1_000,
            due_date=HOJE + timedelta(days=7),
            today=HOJE,
        )
        return {**base, **over}

    def test_valid(self):
        debt = new_debt(**self.kwargs())
        assert debt.customer == "João" and debt.created_at == HOJE and debt.paid_cents == 0

    def test_trims_whitespace(self):
        assert (
            new_debt(**self.kwargs(customer="  João  ", description="  arroz ")).customer == "João"
        )

    @pytest.mark.parametrize("name", ["", "   ", "\t\n"])
    def test_rejects_blank_customer(self, name):
        with pytest.raises(ValidationError, match="cliente"):
            new_debt(**self.kwargs(customer=name))

    @pytest.mark.parametrize("amount", [0, -1, -500])
    def test_rejects_non_positive_amount(self, amount):
        with pytest.raises(ValidationError, match="valor"):
            new_debt(**self.kwargs(amount_cents=amount))

    def test_accepts_one_cent(self):
        assert new_debt(**self.kwargs(amount_cents=1)).amount_cents == 1

    def test_accepts_due_today(self):
        assert new_debt(**self.kwargs(due_date=HOJE)).due_date == HOJE

    def test_rejects_yesterday(self):
        with pytest.raises(ValidationError, match="passado"):
            new_debt(**self.kwargs(due_date=HOJE - timedelta(days=1)))

    @pytest.mark.parametrize("phone", [None, "", "   "])
    def test_empty_phone_becomes_none(self, phone):
        assert new_debt(**self.kwargs(phone=phone)).phone is None

    def test_phone_is_normalized(self):
        assert new_debt(**self.kwargs(phone="(11) 91234-5678")).phone == "5511912345678"


class TestNormalizePhone:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("(11) 91234-5678", "5511912345678"),
            ("11912345678", "5511912345678"),
            ("+55 11 91234-5678", "5511912345678"),
            ("5511912345678", "5511912345678"),
            ("(11) 3234-5678", "551132345678"),  # fixo
            ("(55) 91234-5678", "5555912345678"),  # DDD 55 (RS) não é confundido com DDI
        ],
    )
    def test_valid_formats(self, raw, expected):
        assert normalize_phone(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "abc",
            "123",
            "0",
            "1191234567890123",
            "+1 415 555 0100",  # EUA: 11 dígitos parecem DDD+celular, mas é internacional
            "+351 912 345 678",  # Portugal
            "(01) 91234-5678",  # DDD começa com 0
            "(11) 81234-5678",  # celular de 9 dígitos precisa começar com 9
            "(11) 1234-5678",  # fixo de 8 dígitos precisa começar com 2-5
        ],
    )
    def test_invalid(self, raw):
        with pytest.raises(ValidationError):
            normalize_phone(raw)


class TestFormatBrl:
    @pytest.mark.parametrize(
        ("cents", "expected"),
        [
            (0, "R$ 0,00"),
            (1, "R$ 0,01"),
            (99, "R$ 0,99"),
            (1250, "R$ 12,50"),
            (100_000, "R$ 1.000,00"),
            (123_456_789, "R$ 1.234.567,89"),
        ],
    )
    def test_format(self, cents, expected):
        assert format_brl(cents) == expected


class TestReminderMessage:
    def test_overdue_mentions_days_and_amount(self):
        msg = reminder_message(make_debt(due=HOJE - timedelta(days=3), amount=5_000), HOJE)
        assert "Dona Maria" in msg and "R$ 50,00" in msg and "3 dias" in msg and "12/03/2026" in msg

    def test_singular_day(self):
        assert "1 dia)" in reminder_message(make_debt(due=HOJE - timedelta(days=1)), HOJE)

    def test_due_today_is_friendly_not_accusing(self):
        msg = reminder_message(make_debt(due=HOJE), HOJE)
        assert "vence em 15/03/2026" in msg and "atraso" not in msg and "venceu" not in msg

    def test_message_uses_remaining_not_total(self):
        msg = reminder_message(make_debt(amount=10_000, paid=4_000), HOJE)
        assert "R$ 60,00" in msg and "R$ 100,00" not in msg


class TestWhatsappLink:
    def test_none_without_phone(self):
        assert whatsapp_link(make_debt(), HOJE) is None

    def test_link_is_url_encoded(self):
        link = whatsapp_link(make_debt(phone="5511912345678"), HOJE)
        assert link.startswith("https://wa.me/5511912345678?text=")
        assert " " not in link and "\n" not in link


# --- Testes baseados em propriedades: invariantes valem para QUALQUER entrada ---

amounts = st.integers(min_value=1, max_value=10**9)
dates = st.dates(min_value=date(2020, 1, 1), max_value=date(2035, 12, 31))


@given(amount=amounts, data=st.data())
def test_property_paid_plus_remaining_equals_amount(amount, data):
    pay = data.draw(st.integers(min_value=1, max_value=amount))
    debt = make_debt(amount=amount).with_payment(pay)
    assert debt.paid_cents + debt.remaining_cents == debt.amount_cents
    assert 0 <= debt.remaining_cents <= debt.amount_cents


@given(amount=amounts, extra=st.integers(min_value=1, max_value=10**6))
def test_property_overpayment_always_rejected(amount, extra):
    with pytest.raises(PaymentExceedsBalance):
        make_debt(amount=amount).with_payment(amount + extra)


@given(due=dates, today=dates, amount=amounts)
def test_property_status_is_consistent_with_dates(due, today, amount):
    debt = make_debt(due=due, amount=amount)
    status = debt.status(today)
    assert status is not Status.PAID
    assert (status is Status.OVERDUE) == (due < today)
    assert (status is Status.DUE_TODAY) == (due == today)
    assert (debt.days_overdue(today) > 0) == (status is Status.OVERDUE)


@given(cents=st.integers(min_value=0, max_value=10**12))
def test_property_format_brl_roundtrip(cents):
    text = format_brl(cents)
    digits = text.removeprefix("R$ ").replace(".", "").replace(",", "")
    assert int(digits) == cents
