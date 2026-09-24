"""Backup diário do banco: um arquivo por dia, guardando os últimos 30."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fiado.repository import SqliteDebtRepository


def make_backup(repo: SqliteDebtRepository, folder: Path, today: date, keep: int = 30) -> Path:
    """Salva `fiado-AAAA-MM-DD.db` em `folder` (rodar duas vezes no dia só sobrescreve)."""
    if keep < 1:
        raise ValueError("keep precisa ser >= 1")
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"fiado-{today.isoformat()}.db"
    partial = dest.with_suffix(".tmp")
    repo.backup_to(str(partial))
    partial.replace(dest)  # troca atômica: nunca sobra um backup pela metade
    for old in sorted(folder.glob("fiado-*.db"))[:-keep]:
        old.unlink()
    return dest
