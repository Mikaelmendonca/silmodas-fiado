from datetime import timedelta

import pytest

pytestmark = pytest.mark.api


def payload(clock, **over):
    base = {
        "customer": "Dona Maria",
        "description": "arroz e feijão",
        "amount_cents": 4_590,
        "due_date": (clock.current + timedelta(days=7)).isoformat(),
        "phone": "(11) 91234-5678",
    }
    return {**base, **over}


def create(client, clock, **over):
    res = client.post("/debts", json=payload(clock, **over))
    assert res.status_code == 201, res.text
    return res.json()


class TestCreate:
    def test_contract(self, client, clock):
        body = create(client, clock)
        assert body["id"] == 1
        assert body["status"] == "pending"
        assert body["remaining_cents"] == body["amount_cents"] == 4_590
        assert body["phone"] == "5511912345678"
        assert body["whatsapp_url"].startswith("https://wa.me/5511912345678?text=")

    def test_without_phone_has_no_whatsapp_link(self, client, clock):
        body = create(client, clock, phone=None)
        assert body["whatsapp_url"] is None

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("customer", ""),
            ("customer", "   "),
            ("amount_cents", 0),
            ("amount_cents", -5),
            ("due_date", "2026-03-14"),
            ("phone", "12345"),
        ],
    )
    def test_business_validation_returns_422(self, client, clock, field, value):
        res = client.post("/debts", json=payload(clock, **{field: value}))
        assert res.status_code == 422
        assert client.get("/debts").json() == []  # nada foi gravado

    @pytest.mark.parametrize(
        "bad",
        [
            {"amount_cents": "doze"},
            {"amount_cents": 12.5},
            {"due_date": "amanhã"},
            {"due_date": "2026-13-45"},
            {"customer": "x" * 121},
        ],
    )
    def test_schema_validation_returns_422(self, client, clock, bad):
        assert client.post("/debts", json=payload(clock, **bad)).status_code == 422

    def test_missing_required_fields(self, client):
        assert client.post("/debts", json={}).status_code == 422

    def test_hostile_strings_are_stored_verbatim_as_data(self, client, clock):
        evil = "<script>alert(1)</script>'; DROP TABLE debts;--"
        body = create(client, clock, customer=evil, description=evil)
        assert client.get(f"/debts/{body['id']}").json()["customer"] == evil
        assert client.get("/debts").status_code == 200  # tabela continua de pé

    def test_unicode_customer(self, client, clock):
        assert create(client, clock, customer="José da Conceição 🧾")["customer"].startswith("José")


class TestReadAndDelete:
    def test_get_404(self, client):
        res = client.get("/debts/42")
        assert res.status_code == 404 and "não encontrado" in res.json()["detail"]

    def test_get_non_integer_id(self, client):
        assert client.get("/debts/abc").status_code == 422

    def test_list_filter_by_status(self, client, clock):
        create(client, clock, customer="Hoje", due_date=clock.current.isoformat())
        create(client, clock, customer="Futuro")
        res = client.get("/debts", params={"status": "due_today"}).json()
        assert [d["customer"] for d in res] == ["Hoje"]

    def test_list_invalid_status_filter(self, client):
        assert client.get("/debts", params={"status": "inventado"}).status_code == 422

    def test_delete(self, client, clock):
        d = create(client, clock)
        assert client.delete(f"/debts/{d['id']}").status_code == 204
        assert client.get(f"/debts/{d['id']}").status_code == 404

    def test_delete_404(self, client):
        assert client.delete("/debts/1").status_code == 404


class TestPayments:
    def test_partial_then_full(self, client, clock):
        d = create(client, clock, amount_cents=10_000)
        r1 = client.post(f"/debts/{d['id']}/payments", json={"amount_cents": 4_000}).json()
        assert (r1["paid_cents"], r1["remaining_cents"], r1["status"]) == (4_000, 6_000, "pending")
        r2 = client.post(f"/debts/{d['id']}/payments", json={"amount_cents": 6_000}).json()
        assert (r2["remaining_cents"], r2["status"]) == (0, "paid")

    def test_overpayment_is_409_and_balance_untouched(self, client, clock):
        d = create(client, clock, amount_cents=10_000)
        res = client.post(f"/debts/{d['id']}/payments", json={"amount_cents": 10_001})
        assert res.status_code == 409
        assert client.get(f"/debts/{d['id']}").json()["paid_cents"] == 0

    @pytest.mark.parametrize("amount", [0, -1])
    def test_non_positive_is_422(self, client, clock, amount):
        d = create(client, clock)
        res = client.post(f"/debts/{d['id']}/payments", json={"amount_cents": amount})
        assert res.status_code == 422

    def test_payment_on_missing_debt(self, client):
        assert client.post("/debts/9/payments", json={"amount_cents": 1}).status_code == 404

    def test_double_submit_cannot_overpay(self, client, clock):
        """Clique duplo no botão: o segundo pagamento integral deve ser barrado."""
        d = create(client, clock, amount_cents=5_000)
        url = f"/debts/{d['id']}/payments"
        assert client.post(url, json={"amount_cents": 5_000}).status_code == 200
        assert client.post(url, json={"amount_cents": 5_000}).status_code == 409


class TestRemindersEndToEnd:
    def test_the_core_user_story(self, client, clock):
        """Dona anota fiado -> passa o prazo -> sistema lembra de cobrar -> cliente paga -> some."""
        d = create(
            client,
            clock,
            customer="Seu Zé",
            due_date=(clock.current + timedelta(days=2)).isoformat(),
        )
        assert client.get("/reminders").json() == []  # dia 0: nada a cobrar

        clock.current += timedelta(days=2)  # dia do vencimento
        [due] = client.get("/reminders").json()
        assert (due["customer"], due["status"], due["days_overdue"]) == ("Seu Zé", "due_today", 0)

        clock.current += timedelta(days=3)  # 3 dias depois
        [late] = client.get("/reminders").json()
        assert (late["status"], late["days_overdue"]) == ("overdue", 3)
        assert "3%20dias" in late["whatsapp_url"]

        client.post(f"/debts/{d['id']}/payments", json={"amount_cents": late["remaining_cents"]})
        assert client.get("/reminders").json() == []

    def test_most_overdue_first(self, client, clock):
        create(
            client, clock, customer="B", due_date=(clock.current + timedelta(days=1)).isoformat()
        )
        create(
            client, clock, customer="A", due_date=(clock.current + timedelta(days=3)).isoformat()
        )
        clock.current += timedelta(days=5)
        assert [r["customer"] for r in client.get("/reminders").json()] == ["B", "A"]


class TestSummary:
    def test_summary(self, client, clock):
        create(client, clock, amount_cents=1_000, due_date=clock.current.isoformat())
        create(client, clock, amount_cents=2_000)
        clock.current += timedelta(days=1)
        assert client.get("/summary").json() == {
            "total_open_cents": 3_000,
            "total_overdue_cents": 1_000,
            "due_today_count": 0,
            "overdue_count": 1,
        }


class TestMisc:
    def test_health(self, client):
        assert client.get("/health").json() == {"status": "ok"}

    def test_index_page_served(self, client):
        res = client.get("/")
        assert res.status_code == 200 and "Silmodas" in res.text

    def test_openapi_documents_endpoints(self, client):
        paths = client.get("/openapi.json").json()["paths"]
        assert {"/debts", "/debts/{debt_id}", "/debts/{debt_id}/payments", "/reminders"} <= set(
            paths
        )


class TestTermDays:
    def test_create_with_term_days_only(self, client, clock):
        res = client.post(
            "/debts", json={"customer": "Bruno", "amount_cents": 30000, "term_days": 30}
        )
        assert res.status_code == 201
        body = res.json()
        assert body["due_date"] == "2026-04-14" and body["term_days"] == 30

    def test_missing_both_is_422(self, client):
        res = client.post("/debts", json={"customer": "Bruno", "amount_cents": 30000})
        assert res.status_code == 422


class TestAlertsEndpoints:
    def test_status_reports_configuration(self, client):
        assert client.get("/alerts/status").json() == {
            "push_enabled": True,
            "alert_time": "08:00",
            "warn_days": [3, 1],
        }

    def test_run_sends_alert_for_debt_due_today(self, client, notifier):
        client.post("/debts", json={"customer": "Bruno", "amount_cents": 30000, "term_days": 0})
        assert client.post("/alerts/run").json() == {"sent": 1, "failed": 0}
        assert notifier.sent[0].message == "Prazo de Bruno finaliza hoje. Está devendo R$ 300,00."
        assert client.post("/alerts/run").json() == {"sent": 0, "failed": 0}  # sem duplicar

    def test_test_endpoint_sends_test_notification(self, client, notifier):
        assert client.post("/alerts/test").json() == {"push_enabled": True}
        assert notifier.sent[0].kind == "test"

    def test_test_endpoint_reports_502_when_delivery_fails(self, client, notifier):
        notifier.fail = True
        res = client.post("/alerts/test")
        assert res.status_code == 502 and "fora do ar" in res.json()["detail"]


def test_scheduler_starts_and_stops_cleanly_with_the_app(clock, notifier):
    from fastapi.testclient import TestClient

    from fiado.api import create_app
    from fiado.settings import Settings

    app = create_app(
        db_path=":memory:", today=clock, settings=Settings(), notifier=notifier
    )  # schedule_alerts=True (padrão)
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200


class TestRegressionsFoundByBoundaryProbing:
    """Bugs reais achados por teste de borda: todos devolviam 500 ou aceitavam absurdos."""

    @pytest.mark.parametrize("cents", [2**63, 10**30])
    def test_amount_beyond_sqlite_integer_is_422_not_500(self, client, cents):
        res = client.post("/debts", json={"customer": "A", "amount_cents": cents, "term_days": 1})
        assert res.status_code == 422 and "valor máximo" in res.json()["detail"]

    def test_amount_limit_is_inclusive(self, client):
        ok = client.post("/debts", json={"customer": "A", "amount_cents": 10**9, "term_days": 1})
        too_much = client.post(
            "/debts", json={"customer": "A", "amount_cents": 10**9 + 1, "term_days": 1}
        )
        assert (ok.status_code, too_much.status_code) == (201, 422)

    @pytest.mark.parametrize("method", ["get", "delete"])
    def test_absurd_debt_id_is_422_not_500(self, client, method):
        res = getattr(client, method)("/debts/99999999999999999999999")
        assert res.status_code == 422

    def test_absurd_debt_id_on_payment_is_422(self, client):
        res = client.post("/debts/2147483648999999999999/payments", json={"amount_cents": 1})
        assert res.status_code == 422

    @pytest.mark.parametrize("bad_id", [0, -1])
    def test_non_positive_ids_are_422(self, client, bad_id):
        assert client.get(f"/debts/{bad_id}").status_code == 422

    def test_due_date_too_far_is_rejected_like_term_days(self, client):
        res = client.post(
            "/debts", json={"customer": "A", "amount_cents": 100, "due_date": "9999-12-31"}
        )
        assert res.status_code == 422 and "3650 dias" in res.json()["detail"]

    def test_due_date_at_the_limit_is_accepted(self, client):
        res = client.post("/debts", json={"customer": "A", "amount_cents": 100, "term_days": 3650})
        assert res.status_code == 201
        same = client.post(
            "/debts",
            json={"customer": "A", "amount_cents": 100, "due_date": res.json()["due_date"]},
        )
        assert same.status_code == 201
