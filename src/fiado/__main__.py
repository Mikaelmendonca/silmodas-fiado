"""Linha de comando: python -m fiado [serve|alerts|test|seed]."""

from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta

import uvicorn

from fiado.alerts import TEST_ALERT
from fiado.domain import Debt
from fiado.notifier import NotifierError, build_notifier
from fiado.repository import SqliteDebtRepository
from fiado.service import DebtService
from fiado.settings import Settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fiado", description="Silmodas · controle de fiado")
    parser.add_argument(
        "command",
        nargs="?",
        default="serve",
        choices=["serve", "alerts", "test", "seed"],
        help="serve: painel + alertas diários (padrão) | alerts: envia os alertas de hoje e sai "
        "(bom para cron) | test: manda uma notificação de teste | seed: cria dados de exemplo",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="padrão: só este computador. Use 0.0.0.0 para abrir o painel no celular (mesmo Wi-Fi)",
    )
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env()

    if args.command == "serve":
        _print_banner(settings)
        uvicorn.run("fiado.api:create_app", factory=True, host=args.host, port=args.port)
        return 0

    notifier = build_notifier(settings)
    if args.command == "test":
        try:
            notifier.send(TEST_ALERT)
        except NotifierError as exc:
            print(f"Falhou: {exc}")
            return 1
        print("Enviado!" if settings.push_enabled else "Sem FIADO_NTFY_TOPIC: só registrei no log.")
        return 0

    repo = SqliteDebtRepository(settings.db_path)
    service = DebtService(repo, settings.today)
    try:
        if args.command == "seed":
            _seed(repo, settings.today())
            print("Dados de exemplo criados.")
            return 0
        report = service.send_alerts(notifier, settings.warn_days)
        print(f"{report.sent} alerta(s) enviado(s), {report.failed} falha(s).")
        return 1 if report.failed else 0
    finally:
        service.close()


def _print_banner(settings: Settings) -> None:
    if settings.push_enabled:
        print(f"Alertas no celular: ligados (tópico ntfy, todo dia às {settings.alert_time:%H:%M})")
    else:
        print("Alertas no celular: DESLIGADOS. Defina FIADO_NTFY_TOPIC (veja o README).")


def _seed(repo: SqliteDebtRepository, today: date) -> None:
    """Exemplos espalhados pelos estados possíveis, para o painel não ficar vazio."""
    examples = [
        ("Bruno", "2 camisetas", 30000, 0, 30),
        ("Maria", "Vestido de festa", 15000, 1, 20),
        ("Joana", "Calça e blusa", 22050, 3, 15),
        ("Carla", "Bolsa", 48000, -2, 30),
        ("Ana", "Sandália", 9000, 12, 10),
    ]
    for customer, description, cents, days_from_today, term in examples:
        due = today + timedelta(days=days_from_today)
        # Direto no repositório: o serviço (corretamente) recusa vencimento no passado.
        repo.add(
            Debt(
                customer=customer,
                description=description,
                amount_cents=cents,
                due_date=due,
                created_at=due - timedelta(days=term),
            )
        )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
