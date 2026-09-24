"""Agendador diário sem dependências externas. Relógio e sleep são injetáveis para teste."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, time, timedelta, tzinfo

log = logging.getLogger(__name__)


def next_run(now: datetime, at: time) -> datetime:
    """Próxima ocorrência de `at` estritamente depois de `now`."""
    candidate = now.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    return candidate if candidate > now else candidate + timedelta(days=1)


async def run_daily(
    job: Callable[[], Awaitable[None]],
    at: time,
    tz: tzinfo,
    *,
    now: Callable[[tzinfo], datetime] = datetime.now,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Roda `job` todo dia às `at`. Se o app subir depois do horário, roda logo ao iniciar
    (recuperação: o PC pode ter estado desligado às 8h). O job é idempotente, então
    rodar de novo no mesmo dia não duplica notificações.
    """
    if now(tz).time() >= at:
        await _safely(job)
    while True:
        current = now(tz)
        await sleep((next_run(current, at) - current).total_seconds())
        await _safely(job)


async def _safely(job: Callable[[], Awaitable[None]]) -> None:
    try:
        await job()
    except Exception:  # um erro de hoje não pode matar o agendador de amanhã
        log.exception("Falha ao executar o job diário de alertas")
