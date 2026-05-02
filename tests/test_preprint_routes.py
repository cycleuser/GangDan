"""Tests for preprint_routes module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gangdan.core.config import DATA_DIR


@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    import os

    os.environ["QT_QPA_PLATFORM"] = "offscreen"

    temp_dir = Path(tempfile.mkdtemp())
    os.environ["GANGDAN_DATA_DIR"] = str(temp_dir)

    from gangdan.app import app

    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestPreprintSearchAPI:
    """Test preprint search API endpoints."""

    def test_search_missing_query(self, client) -> None:
        resp = client.post("/api/preprint/search", json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    @patch("gangdan.core.preprint_fetcher.PreprintFetcher")
    def test_search_success(self, mock_fetcher_cls, client) -> None:
        from gangdan.core.preprint_fetcher import PreprintMetadata

        mock_fetcher = MagicMock()
        mock_fetcher_cls.return_value = mock_fetcher
        mock_fetcher.search.return_value = [
            PreprintMetadata(
                preprint_id="2301.12345",
                title="Test Paper",
                abstract="Test abstract",
                has_html=True,
                has_tex=True,
                source_platform="arxiv",
            )
        ]

        resp = client.post("/api/preprint/search", json={
            "query": "machine learning",
            "platforms": ["arxiv"],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["total"] == 1
        assert data["html_available"] == 1


class TestPreprintSchedulerAPI:
    """Test scheduler API endpoints."""

    def test_scheduler_status(self, client) -> None:
        resp = client.get("/api/preprint/scheduler/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "status" in data

    def test_scheduler_start(self, client) -> None:
        resp = client.post("/api/preprint/scheduler/start")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_scheduler_stop(self, client) -> None:
        resp = client.post("/api/preprint/scheduler/stop")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_set_interval(self, client) -> None:
        resp = client.post("/api/preprint/scheduler/interval", json={"hours": 12})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["interval_hours"] == 12


class TestPreprintSubscriptionsAPI:
    """Test subscriptions API endpoints."""

    def test_list_subscriptions_empty(self, client) -> None:
        resp = client.get("/api/preprint/subscriptions")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "subscriptions" in data

    def test_add_subscription(self, client) -> None:
        resp = client.post("/api/preprint/subscriptions", json={
            "name": "AI Research",
            "keywords": ["machine learning", "deep learning"],
            "platforms": ["arxiv"],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["subscription"]["name"] == "AI Research"

    def test_add_subscription_missing_fields(self, client) -> None:
        resp = client.post("/api/preprint/subscriptions", json={})
        assert resp.status_code == 400

    def test_remove_subscription(self, client) -> None:
        client.post("/api/preprint/subscriptions", json={
            "name": "ToRemove",
            "keywords": ["test"],
        })
        resp = client.delete("/api/preprint/subscriptions/ToRemove")
        assert resp.status_code == 200

    def test_remove_nonexistent_subscription(self, client) -> None:
        resp = client.delete("/api/preprint/subscriptions/Nonexistent")
        assert resp.status_code == 404


class TestPreprintKBAPI:
    """Test KB API endpoints."""

    def test_kb_stats(self, client) -> None:
        resp = client.get("/api/preprint/kb/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "stats" in data

    def test_kb_recent(self, client) -> None:
        resp = client.get("/api/preprint/kb/recent")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_kb_search_missing_query(self, client) -> None:
        resp = client.post("/api/preprint/kb/search", json={})
        assert resp.status_code == 400

    def test_kb_index_missing_fields(self, client) -> None:
        resp = client.post("/api/preprint/kb/index", json={})
        assert resp.status_code == 400


class TestPreprintFetchRecentAPI:
    """Test fetch recent API endpoint."""

    @patch("gangdan.core.preprint_fetcher.PreprintFetcher")
    def test_fetch_recent(self, mock_fetcher_cls, client) -> None:
        mock_fetcher = MagicMock()
        mock_fetcher_cls.return_value = mock_fetcher
        mock_fetcher.fetch_recent.return_value = []

        resp = client.get("/api/preprint/recent?days=7")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
