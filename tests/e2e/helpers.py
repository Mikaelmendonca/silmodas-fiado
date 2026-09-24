"""Datas no mesmo fuso do servidor e do navegador dos testes E2E."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = "America/Sao_Paulo"


def hoje() -> date:
    return datetime.now(ZoneInfo(TZ)).date()


def em(dias: int) -> date:
    return hoje() + timedelta(days=dias)
