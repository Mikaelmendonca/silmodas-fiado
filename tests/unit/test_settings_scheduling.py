import asyncio
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from fiado.scheduling import next_run, run_daily
from fiado.settings import Settings

pytestmark = pytest.mark.unit

TZ = ZoneInfo("America/Sao_Paulo")


class TestSettings:
    def test_defaults(self):
        s = Settings.from_env({})
        assert s.db_path == "fiado.db"
        assert s.alert_time == time(8, 0)
        assert s.warn_days == (3, 1)
        assert not s.push_enabled

    def test_reads_everything(self):
        s = Settings.from_env(
            {
                "FIADO_DB": "x.db",
                "FIADO_NTFY_TOPIC": "  silmodas-abc  ",
                "FIADO_NTFY_SERVER": "https://ntfy.exemplo.com/",
                "FIADO_ALERT_TIME": "07:30",
                "FIADO_WARN_DAYS": "1, 5,3,3",
                "FIADO_TZ": "UTC",
            }
        )
        assert s.db_path == "x.db"
        assert s.ntfy_topic == "silmodas-abc" and s.push_enabled
        assert s.ntfy_server == "https://ntfy.exemplo.com"
        assert s.alert_time == time(7, 30)
        assert s.warn_days == (5, 3, 1)
        assert s.timezone == "UTC"

    def test_password_and_backup_folder(self):
        s = Settings.from_env({"FIADO_PASSWORD": "  segredo1 ", "FIADO_BACKUP_DIR": "/tmp/b"})
        assert s.password == "segredo1" and s.backup_dir == "/tmp/b"
        assert Settings.from_env({}).password is None
        assert Settings.from_env({"FIADO_PASSWORD": "  "}).password is None

    def test_password_never_shows_up_in_repr_or_logs(self):
        assert "segredo1" not in repr(Settings(password="segredo1"))

    def test_blank_topic_means_disabled(self):
        assert Settings.from_env({"FIADO_NTFY_TOPIC": "   "}).ntfy_topic is None

    def test_empty_warn_days_allowed(self):
        assert Settings.from_env({"FIADO_WARN_DAYS": ""}).warn_days == ()

    @pytest.mark.parametrize(
        ("var", "value"),
        [
            ("FIADO_ALERT_TIME", "8h"),
            ("FIADO_ALERT_TIME", "25:00"),
            ("FIADO_WARN_DAYS", "tres"),
            ("FIADO_WARN_DAYS", "0"),
            ("FIADO_WARN_DAYS", "-1"),
            ("FIADO_TZ", "Marte/Olympus"),
        ],
    )
    def test_invalid_values_fail_loudly(self, var, value):
        with pytest.raises(ValueError, match=var):
            Settings.from_env({var: value})

    def test_today_uses_store_timezone(self):
        assert isinstance(Settings(timezone="UTC").today(), date)


class TestNextRun:
    def test_later_today(self):
        now = datetime(2026, 3, 15, 6, 0, tzinfo=TZ)
        assert next_run(now, time(8, 0)) == datetime(2026, 3, 15, 8, 0, tzinfo=TZ)

    def test_already_past_goes_to_tomorrow(self):
        now = datetime(2026, 3, 15, 9, 0, tzinfo=TZ)
        assert next_run(now, time(8, 0)) == datetime(2026, 3, 16, 8, 0, tzinfo=TZ)

    def test_exactly_on_time_goes_to_tomorrow(self):
        now = datetime(2026, 3, 15, 8, 0, tzinfo=TZ)
        assert next_run(now, time(8, 0)) == datetime(2026, 3, 16, 8, 0, tzinfo=TZ)

    def test_month_and_year_rollover(self):
        now = datetime(2026, 12, 31, 23, 0, tzinfo=TZ)
        assert next_run(now, time(8, 0)) == datetime(2027, 1, 1, 8, 0, tzinfo=TZ)


class TestRunDaily:
    def _run(self, start: datetime, job, *, cycles: int):
        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)
            if len(sleeps) == cycles:
                raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            asyncio.run(run_daily(job, time(8, 0), TZ, now=lambda _tz: start, sleep=fake_sleep))
        return sleeps

    def test_before_alert_time_waits_first_without_catch_up(self):
        calls = []

        async def job():
            calls.append(1)

        sleeps = self._run(datetime(2026, 3, 15, 6, 0, tzinfo=TZ), job, cycles=1)
        assert sleeps == [2 * 3600]
        assert calls == []

    def test_started_after_alert_time_runs_immediately_then_waits(self):
        calls = []

        async def job():
            calls.append(1)

        sleeps = self._run(datetime(2026, 3, 15, 9, 0, tzinfo=TZ), job, cycles=2)
        assert calls == [1, 1]  # catch-up + execução do dia seguinte
        assert sleeps == [23 * 3600, 23 * 3600]

    def test_failing_job_does_not_kill_the_scheduler(self):
        calls = []

        async def job():
            calls.append(1)
            raise RuntimeError("boom")

        self._run(datetime(2026, 3, 15, 9, 0, tzinfo=TZ), job, cycles=3)
        assert len(calls) == 3
