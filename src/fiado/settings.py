"""Configuração via variáveis de ambiente (ou arquivo .env). Tudo tem padrão sensato."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    db_path: str = "fiado.db"
    ntfy_topic: str | None = None  # sem tópico = alertas só no log, nada vai pro celular
    ntfy_server: str = "https://ntfy.sh"
    alert_time: time = time(8, 0)  # hora do envio diário
    warn_days: tuple[int, ...] = (3, 1)  # avisa quando faltam 3 e 1 dias, além de "hoje"
    timezone: str = "America/Sao_Paulo"

    @property
    def push_enabled(self) -> bool:
        return self.ntfy_topic is not None

    def today(self) -> date:
        """'Hoje' no fuso da loja, mesmo que o servidor rode em UTC."""
        return datetime.now(ZoneInfo(self.timezone)).date()

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        if env is None:
            load_dotenv()
            env = os.environ
        defaults = cls()
        return cls(
            db_path=env.get("FIADO_DB") or defaults.db_path,
            ntfy_topic=(env.get("FIADO_NTFY_TOPIC") or "").strip() or None,
            ntfy_server=(env.get("FIADO_NTFY_SERVER") or defaults.ntfy_server).rstrip("/"),
            alert_time=_parse_time(env.get("FIADO_ALERT_TIME") or "08:00"),
            warn_days=_parse_days(env.get("FIADO_WARN_DAYS", "3,1")),
            timezone=_parse_timezone(env.get("FIADO_TZ") or defaults.timezone),
        )


def _parse_time(text: str) -> time:
    try:
        return time.fromisoformat(text.strip())
    except ValueError:
        raise ValueError(f"FIADO_ALERT_TIME inválido: {text!r}. Use HH:MM, ex.: 08:00.") from None


def _parse_days(text: str) -> tuple[int, ...]:
    try:
        days = {int(part) for part in text.split(",") if part.strip()}
    except ValueError:
        raise ValueError(f"FIADO_WARN_DAYS inválido: {text!r}. Use ex.: 3,1.") from None
    if any(d < 1 for d in days):
        raise ValueError("FIADO_WARN_DAYS só aceita dias >= 1 (o dia do vencimento já é avisado).")
    return tuple(sorted(days, reverse=True))


def _parse_timezone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (KeyError, ValueError, OSError):
        raise ValueError(f"FIADO_TZ inválido: {name!r}. Ex.: America/Sao_Paulo.") from None
    return name
