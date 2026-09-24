"""Envio de notificações. NtfyNotifier manda push pro celular; LogNotifier só registra."""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

from fiado.alerts import Alert
from fiado.settings import Settings

log = logging.getLogger(__name__)


class NotifierError(Exception):
    """Não foi possível entregar a notificação."""


class Notifier(Protocol):
    def send(self, alert: Alert) -> None: ...


class LogNotifier:
    """Usado quando não há tópico configurado: útil para desenvolver sem celular."""

    def send(self, alert: Alert) -> None:
        log.info("[alerta] %s — %s", alert.title, alert.message)


class NtfyNotifier:
    """Push via https://ntfy.sh (grátis, sem conta): instale o app ntfy e assine o tópico."""

    def __init__(
        self, topic: str, server: str = "https://ntfy.sh", client: httpx.Client | None = None
    ) -> None:
        self._topic = topic
        self._server = server.rstrip("/")
        self._client = client or httpx.Client(timeout=10)

    def send(self, alert: Alert) -> None:
        # Publicação em JSON (e não em headers) para acentos e emojis chegarem certos.
        payload = {
            "topic": self._topic,
            "title": alert.title,
            "message": alert.message,
            "priority": alert.priority,
            "tags": list(alert.tags),
        }
        try:
            response = self._client.post(self._server, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise NotifierError(f"Falha ao enviar para o ntfy: {exc}") from exc


def build_notifier(settings: Settings) -> Notifier:
    if settings.ntfy_topic is None:
        return LogNotifier()
    return NtfyNotifier(settings.ntfy_topic, settings.ntfy_server)
