"""Persistência em SQLite. Use ':memory:' nos testes."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import replace
from datetime import date

from fiado.domain import Debt

_SCHEMA = """
CREATE TABLE IF NOT EXISTS debts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    customer     TEXT    NOT NULL,
    phone        TEXT,
    description  TEXT    NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    paid_cents   INTEGER NOT NULL DEFAULT 0 CHECK (paid_cents >= 0),
    due_date     TEXT    NOT NULL,
    created_at   TEXT    NOT NULL,
    CHECK (paid_cents <= amount_cents)
);

-- Um alerta de cada tipo por dia por fiado: reiniciar o app não duplica notificações.
CREATE TABLE IF NOT EXISTS alerts_sent (
    debt_id INTEGER NOT NULL REFERENCES debts(id) ON DELETE CASCADE,
    kind    TEXT    NOT NULL,
    sent_on TEXT    NOT NULL,
    PRIMARY KEY (debt_id, kind, sent_on)
);
"""


class SqliteDebtRepository:
    def __init__(self, path: str = ":memory:") -> None:
        # check_same_thread=False: o FastAPI atende requisições em threads diferentes.
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def add(self, debt: Debt) -> Debt:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO debts (customer, phone, description, amount_cents, "
                "paid_cents, due_date, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    debt.customer,
                    debt.phone,
                    debt.description,
                    debt.amount_cents,
                    debt.paid_cents,
                    debt.due_date.isoformat(),
                    debt.created_at.isoformat(),
                ),
            )
        return replace(debt, id=cur.lastrowid)

    def get(self, debt_id: int) -> Debt | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM debts WHERE id = ?", (debt_id,)).fetchone()
        return _to_debt(row) if row else None

    def list_all(self) -> list[Debt]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM debts ORDER BY due_date, id").fetchall()
        return [_to_debt(r) for r in rows]

    def update_paid(self, debt_id: int, paid_cents: int) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE debts SET paid_cents = ? WHERE id = ?", (paid_cents, debt_id)
            )

    def alert_was_sent(self, debt_id: int, kind: str, day: date) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM alerts_sent WHERE debt_id = ? AND kind = ? AND sent_on = ?",
                (debt_id, kind, day.isoformat()),
            ).fetchone()
        return row is not None

    def mark_alert_sent(self, debt_id: int, kind: str, day: date) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO alerts_sent (debt_id, kind, sent_on) VALUES (?, ?, ?)",
                (debt_id, kind, day.isoformat()),
            )

    def delete(self, debt_id: int) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM debts WHERE id = ?", (debt_id,))
        return cur.rowcount > 0


def _to_debt(row: sqlite3.Row) -> Debt:
    return Debt(
        id=row["id"],
        customer=row["customer"],
        phone=row["phone"],
        description=row["description"],
        amount_cents=row["amount_cents"],
        paid_cents=row["paid_cents"],
        due_date=date.fromisoformat(row["due_date"]),
        created_at=date.fromisoformat(row["created_at"]),
    )
