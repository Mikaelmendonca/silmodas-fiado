import sqlite3
from datetime import date, timedelta

import pytest

from fiado.backup import make_backup
from fiado.repository import SqliteDebtRepository
from fiado.service import DebtService

pytestmark = pytest.mark.unit

HOJE = date(2026, 3, 15)


@pytest.fixture
def repo_com_dados():
    repo = SqliteDebtRepository(":memory:")
    DebtService(repo, lambda: HOJE).create(
        customer="Bruno", description="", amount_cents=30_000, term_days=5
    )
    yield repo
    repo.close()


def test_backup_is_a_real_readable_copy_of_the_data(repo_com_dados, tmp_path):
    saved = make_backup(repo_com_dados, tmp_path / "backups", HOJE)

    assert saved.name == "fiado-2026-03-15.db"
    copia = SqliteDebtRepository(str(saved))
    assert [d.customer for d in copia.list_all()] == ["Bruno"]
    copia.close()


def test_backup_creates_the_folder_and_leaves_no_partial_files(repo_com_dados, tmp_path):
    make_backup(repo_com_dados, tmp_path / "a" / "b", HOJE)
    assert [f.name for f in (tmp_path / "a" / "b").iterdir()] == ["fiado-2026-03-15.db"]


def test_running_twice_the_same_day_overwrites_instead_of_piling_up(repo_com_dados, tmp_path):
    make_backup(repo_com_dados, tmp_path, HOJE)
    DebtService(repo_com_dados, lambda: HOJE).create(
        customer="Maria", description="", amount_cents=100, term_days=1
    )
    saved = make_backup(repo_com_dados, tmp_path, HOJE)

    assert len(list(tmp_path.glob("fiado-*.db"))) == 1
    assert sqlite3.connect(saved).execute("SELECT COUNT(*) FROM debts").fetchone()[0] == 2


def test_keeps_only_the_most_recent_backups(repo_com_dados, tmp_path):
    for i in range(5):
        make_backup(repo_com_dados, tmp_path, HOJE + timedelta(days=i), keep=3)

    assert sorted(f.name for f in tmp_path.glob("fiado-*.db")) == [
        "fiado-2026-03-17.db",
        "fiado-2026-03-18.db",
        "fiado-2026-03-19.db",
    ]


def test_never_deletes_files_that_are_not_backups(repo_com_dados, tmp_path):
    (tmp_path / "minhas-anotacoes.txt").write_text("importante")
    make_backup(repo_com_dados, tmp_path, HOJE, keep=1)
    assert (tmp_path / "minhas-anotacoes.txt").exists()


def test_keep_must_be_positive(repo_com_dados, tmp_path):
    with pytest.raises(ValueError):
        make_backup(repo_com_dados, tmp_path, HOJE, keep=0)
