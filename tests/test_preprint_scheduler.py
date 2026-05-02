"""Tests for preprint_scheduler module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gangdan.core.preprint_scheduler import (
    FetchJob,
    PreprintScheduler,
    SchedulerStatus,
    Subscription,
)


class TestSubscription:
    """Test Subscription dataclass."""

    def test_defaults(self) -> None:
        sub = Subscription()
        assert sub.name == ""
        assert sub.keywords == []
        assert sub.platforms == ["arxiv"]
        assert sub.enabled is True

    def test_to_dict(self) -> None:
        sub = Subscription(name="Test", keywords=["AI", "ML"])
        d = sub.to_dict()
        assert d["name"] == "Test"
        assert d["keywords"] == ["AI", "ML"]

    def test_from_dict(self) -> None:
        data = {
            "name": "Test",
            "keywords": ["AI"],
            "platforms": ["arxiv", "biorxiv"],
            "max_results": 5,
        }
        sub = Subscription.from_dict(data)
        assert sub.name == "Test"
        assert sub.keywords == ["AI"]
        assert sub.platforms == ["arxiv", "biorxiv"]
        assert sub.max_results == 5


class TestSchedulerStatus:
    """Test SchedulerStatus dataclass."""

    def test_defaults(self) -> None:
        status = SchedulerStatus()
        assert status.running is False
        assert status.interval_hours == 24
        assert status.total_runs == 0

    def test_to_dict(self) -> None:
        status = SchedulerStatus(running=True, total_runs=5)
        d = status.to_dict()
        assert d["running"] is True
        assert d["total_runs"] == 5


class TestFetchJob:
    """Test FetchJob dataclass."""

    def test_defaults(self) -> None:
        job = FetchJob()
        assert job.status == "pending"
        assert job.preprints_found == 0

    def test_to_dict(self) -> None:
        job = FetchJob(job_id="abc123", status="completed", preprints_found=10)
        d = job.to_dict()
        assert d["job_id"] == "abc123"
        assert d["status"] == "completed"
        assert d["preprints_found"] == 10


class TestPreprintScheduler:
    """Test PreprintScheduler."""

    def _make_scheduler(self) -> PreprintScheduler:
        """Create a scheduler with a temp state file."""
        tmpdir = Path(tempfile.mkdtemp())
        state_file = tmpdir / "preprint_state.json"
        return PreprintScheduler(state_file=state_file)

    def test_init_empty(self) -> None:
        scheduler = self._make_scheduler()
        assert len(scheduler.subscriptions) == 0
        assert scheduler.status.running is False

    def test_add_subscription(self) -> None:
        scheduler = self._make_scheduler()
        sub = scheduler.add_subscription("AI Research", ["machine learning", "deep learning"])
        assert sub.name == "AI Research"
        assert len(scheduler.subscriptions) == 1

    def test_remove_subscription(self) -> None:
        scheduler = self._make_scheduler()
        scheduler.add_subscription("Test", ["test"])
        assert scheduler.remove_subscription("Test") is True
        assert len(scheduler.subscriptions) == 0

    def test_remove_nonexistent(self) -> None:
        scheduler = self._make_scheduler()
        assert scheduler.remove_subscription("Nonexistent") is False

    def test_get_subscription(self) -> None:
        scheduler = self._make_scheduler()
        scheduler.add_subscription("Test", ["test"])
        sub = scheduler.get_subscription("Test")
        assert sub is not None
        assert sub.name == "Test"

    def test_get_nonexistent_subscription(self) -> None:
        scheduler = self._make_scheduler()
        assert scheduler.get_subscription("Nonexistent") is None

    def test_set_interval(self) -> None:
        scheduler = self._make_scheduler()
        scheduler.set_interval(12)
        assert scheduler.status.interval_hours == 12

    def test_start_stop(self) -> None:
        scheduler = self._make_scheduler()
        assert scheduler.start() is True
        assert scheduler.status.running is True
        assert scheduler.stop() is True
        assert scheduler.status.running is False

    def test_start_already_running(self) -> None:
        scheduler = self._make_scheduler()
        scheduler.start()
        assert scheduler.start() is False
        scheduler.stop()

    def test_stop_not_running(self) -> None:
        scheduler = self._make_scheduler()
        assert scheduler.stop() is False

    def test_get_status(self) -> None:
        scheduler = self._make_scheduler()
        scheduler.add_subscription("Test", ["test"])
        status = scheduler.get_status()
        assert "subscriptions" in status
        assert "recent_jobs" in status
        assert len(status["subscriptions"]) == 1

    def test_get_jobs_empty(self) -> None:
        scheduler = self._make_scheduler()
        jobs = scheduler.get_jobs()
        assert jobs == []

    def test_state_persistence(self) -> None:
        scheduler = self._make_scheduler()
        scheduler.add_subscription("Test", ["keyword"])
        scheduler.set_interval(6)

        state_file = scheduler.state_file
        assert state_file.exists()

        data = json.loads(state_file.read_text())
        assert len(data["subscriptions"]) == 1
        assert data["status"]["interval_hours"] == 6

    def test_state_load(self) -> None:
        tmpdir = Path(tempfile.mkdtemp())
        state_file = tmpdir / "preprint_state.json"
        state_data = {
            "subscriptions": [
                {"name": "Loaded", "keywords": ["test"], "platforms": ["arxiv"], "categories": [], "max_results": 10, "enabled": True, "last_fetched": "", "total_fetched": 0}
            ],
            "status": {"running": False, "interval_hours": 12, "total_runs": 3},
            "jobs": [],
            "cache": {},
        }
        state_file.write_text(json.dumps(state_data))

        scheduler = PreprintScheduler(state_file=state_file)
        assert len(scheduler.subscriptions) == 1
        assert scheduler.subscriptions[0].name == "Loaded"
        assert scheduler.status.interval_hours == 12

    def test_run_once(self) -> None:
        scheduler = self._make_scheduler()
        scheduler.add_subscription("Test", ["test keyword"])

        with patch("gangdan.core.preprint_fetcher.PreprintFetcher") as mock_fetcher_cls:
            mock_fetcher = MagicMock()
            mock_fetcher_cls.return_value = mock_fetcher
            mock_fetcher.search.return_value = []

            result = scheduler.run_once()

        assert result["subscriptions_processed"] == 1
        assert result["total_preprints"] == 0

    def test_progress_callback(self) -> None:
        scheduler = self._make_scheduler()
        callback = MagicMock()
        scheduler.set_progress_callback(callback)

        scheduler._report_progress("Test", 5, 10)
        callback.assert_called_once_with("Test", 5, 10)

    def test_get_cached_preprints_empty(self) -> None:
        scheduler = self._make_scheduler()
        assert scheduler.get_cached_preprints() == []

    def test_get_cached_preprint_not_found(self) -> None:
        scheduler = self._make_scheduler()
        assert scheduler.get_cached_preprint("nonexistent") is None

    def test_clear_cache(self) -> None:
        scheduler = self._make_scheduler()
        scheduler._fetch_cache["test"] = {"data": "value"}
        scheduler.clear_cache()
        assert scheduler.get_cached_preprints() == []
