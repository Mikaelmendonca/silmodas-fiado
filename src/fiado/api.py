"""API HTTP (FastAPI). Rode com: python -m fiado   (ou uvicorn fiado.api:create_app --factory)"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from fiado.alerts import TEST_ALERT
from fiado.domain import (
    Debt,
    DebtNotFound,
    PaymentExceedsBalance,
    Status,
    ValidationError,
    whatsapp_link,
)
from fiado.notifier import Notifier, NotifierError, build_notifier
from fiado.repository import SqliteDebtRepository
from fiado.scheduling import run_daily
from fiado.service import DebtService
from fiado.settings import Settings

STATIC_DIR = Path(__file__).parent / "static"
# SQLite guarda inteiros de até 64 bits: um id maior nunca existe (antes causava erro 500).
DebtId = Annotated[int, PathParam(ge=1, le=2**63 - 1)]
log = logging.getLogger(__name__)


class DebtIn(BaseModel):
    customer: str = Field(max_length=120)
    description: str = Field(default="", max_length=300)
    amount_cents: int = Field(description="Valor em centavos (R$ 12,50 = 1250)")
    due_date: date | None = Field(default=None, description="Vencimento (tem prioridade)")
    term_days: int | None = Field(default=None, description="Prazo em dias a partir de hoje")
    phone: str | None = Field(default=None, max_length=30)


class PaymentIn(BaseModel):
    amount_cents: int


class DebtOut(BaseModel):
    id: int
    customer: str
    phone: str | None
    description: str
    amount_cents: int
    paid_cents: int
    remaining_cents: int
    due_date: date
    term_days: int
    created_at: date
    status: Status
    days_overdue: int
    whatsapp_url: str | None


def _out(debt: Debt, today: date) -> DebtOut:
    assert debt.id is not None
    return DebtOut(
        id=debt.id,
        customer=debt.customer,
        phone=debt.phone,
        description=debt.description,
        amount_cents=debt.amount_cents,
        paid_cents=debt.paid_cents,
        remaining_cents=debt.remaining_cents,
        due_date=debt.due_date,
        term_days=debt.term_days,
        created_at=debt.created_at,
        status=debt.status(today),
        days_overdue=debt.days_overdue(today),
        whatsapp_url=whatsapp_link(debt, today),
    )


def create_app(
    db_path: str | None = None,
    today: Callable[[], date] | None = None,
    *,
    settings: Settings | None = None,
    notifier: Notifier | None = None,
    schedule_alerts: bool = True,
) -> FastAPI:
    settings = settings or Settings.from_env()
    notifier = notifier or build_notifier(settings)
    service = DebtService(
        SqliteDebtRepository(db_path or settings.db_path), today or settings.today
    )

    async def alert_job() -> None:
        report = await asyncio.to_thread(service.send_alerts, notifier, settings.warn_days)
        log.info("Alertas do dia: %d enviados, %d falharam", report.sent, report.failed)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = None
        if schedule_alerts:
            tz = ZoneInfo(settings.timezone)
            task = asyncio.create_task(run_daily(alert_job, settings.alert_time, tz))
        yield
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        service.close()

    app = FastAPI(
        title="Silmodas · Fiado",
        description="Controle de fiado com alertas de vencimento no celular.",
        lifespan=lifespan,
    )

    @app.exception_handler(ValidationError)
    async def _validation(_: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(PaymentExceedsBalance)
    async def _overpay(_: Request, exc: PaymentExceedsBalance) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(DebtNotFound)
    async def _not_found(_: Request, exc: DebtNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/debts", response_model=DebtOut, status_code=201)
    def create_debt(body: DebtIn) -> DebtOut:
        debt = service.create(**body.model_dump())
        return _out(debt, service.today())

    @app.get("/debts", response_model=list[DebtOut])
    def list_debts(status: Status | None = None) -> list[DebtOut]:
        t = service.today()
        return [_out(d, t) for d in service.list_debts(status)]

    @app.get("/debts/{debt_id}", response_model=DebtOut)
    def get_debt(debt_id: DebtId) -> DebtOut:
        return _out(service.get(debt_id), service.today())

    @app.post("/debts/{debt_id}/payments", response_model=DebtOut)
    def pay_debt(debt_id: DebtId, body: PaymentIn) -> DebtOut:
        return _out(service.pay(debt_id, body.amount_cents), service.today())

    @app.delete("/debts/{debt_id}", status_code=204)
    def delete_debt(debt_id: DebtId) -> None:
        service.delete(debt_id)

    @app.get("/reminders", response_model=list[DebtOut])
    def reminders() -> list[DebtOut]:
        t = service.today()
        return [_out(d, t) for d in service.reminders()]

    @app.get("/alerts/status")
    def alerts_status() -> dict[str, object]:
        return {
            "push_enabled": settings.push_enabled,
            "alert_time": settings.alert_time.strftime("%H:%M"),
            "warn_days": list(settings.warn_days),
        }

    @app.post("/alerts/run")
    def run_alerts() -> dict[str, int]:
        report = service.send_alerts(notifier, settings.warn_days)
        return {"sent": report.sent, "failed": report.failed}

    @app.post("/alerts/test")
    def test_alert() -> dict[str, bool]:
        try:
            notifier.send(TEST_ALERT)
        except NotifierError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"push_enabled": settings.push_enabled}

    @app.get("/summary")
    def summary() -> dict[str, int]:
        s = service.summary()
        return {
            "total_open_cents": s.total_open_cents,
            "total_overdue_cents": s.total_overdue_cents,
            "due_today_count": s.due_today_count,
            "overdue_count": s.overdue_count,
        }

    return app
