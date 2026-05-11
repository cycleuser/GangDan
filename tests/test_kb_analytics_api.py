"""Tests for KB analytics API routes."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def app_with_analytics(temp_data_dir):
    """Create Flask app with analytics configured."""
    from gangdan.core.config import CONFIG
    CONFIG.embedding_model = "nomic-embed-text"
    CONFIG.chat_model = "llama3.2"

    from gangdan.app import app
    app.config["TESTING"] = True

    with app.test_client() as client:
        yield client


@pytest.fixture
def kb_setup(app_with_analytics):
    """Create a test KB via API."""
    client = app_with_analytics
    resp = client.post("/api/kb/create", json={
        "display_name": "Test Analytics",
        "description": "Test KB for analytics",
    })
    data = resp.get_json()
    assert data["success"] is True
    return data["kb"]["internal_name"]


class TestTopicClustersAPI:
    """Test topic clusters API endpoint."""

    def test_topic_clusters_no_kb(self, app_with_analytics):
        resp = app_with_analytics.post("/api/kb/nonexistent/analytics/topics", json={})
        assert resp.status_code == 404

    def test_topic_clusters_basic(self, app_with_analytics, kb_setup):
        internal_name = kb_setup

        with patch("gangdan.kb_routes.get_analytics") as mock_get:
            mock_analytics = MagicMock()
            mock_analytics.get_topic_clusters.return_value = [
                MagicMock(
                    cluster_id=0,
                    name="topic_0",
                    doc_ids=["doc1", "doc2"],
                    representative_doc="doc1",
                    size=2,
                    keywords=["test"],
                    to_dict=lambda: {
                        "cluster_id": 0,
                        "name": "topic_0",
                        "doc_ids": ["doc1", "doc2"],
                        "representative_doc": "doc1",
                        "size": 2,
                        "keywords": ["test"],
                    },
                ),
            ]
            mock_get.return_value = mock_analytics

            resp = app_with_analytics.post(
                f"/api/kb/{internal_name}/analytics/topics",
                json={"n_clusters": 2},
            )

            assert resp.status_code == 200
            data = resp.get_json()
            assert "clusters" in data
            assert data["total_clusters"] == 1


class TestPointCloudAPI:
    """Test point cloud API endpoint."""

    def test_point_cloud_no_kb(self, app_with_analytics):
        resp = app_with_analytics.post("/api/kb/nonexistent/analytics/point-cloud", json={})
        assert resp.status_code == 404

    def test_point_cloud_basic(self, app_with_analytics, kb_setup):
        internal_name = kb_setup

        with patch("gangdan.kb_routes.get_analytics") as mock_get:
            mock_analytics = MagicMock()
            mock_cloud = MagicMock()
            mock_cloud.to_dict.return_value = {
                "points": [{"doc_id": "doc1", "x": 0.1, "y": 0.2, "z": 0, "label": "Doc 1", "cluster": 0}],
                "dimensions": 2,
                "method": "pca",
            }
            mock_analytics.get_point_cloud.return_value = mock_cloud
            mock_analytics._get_embeddings_for_kb.return_value = (["doc1"], ["Doc 1"], [[0.1, 0.2]])
            mock_get.return_value = mock_analytics

            resp = app_with_analytics.post(
                f"/api/kb/{internal_name}/analytics/point-cloud",
                json={"dimensions": 2, "method": "pca", "include_clusters": True},
            )

            assert resp.status_code == 200
            data = resp.get_json()
            assert "point_cloud" in data
            assert data["point_cloud"]["dimensions"] == 2


class TestOpinionClustersAPI:
    """Test opinion clusters API endpoint."""

    def test_opinion_clusters_no_kb(self, app_with_analytics):
        resp = app_with_analytics.post("/api/kb/nonexistent/analytics/opinions", json={})
        assert resp.status_code == 404

    def test_opinion_clusters_basic(self, app_with_analytics, kb_setup):
        internal_name = kb_setup

        with patch("gangdan.kb_routes.get_analytics") as mock_get:
            mock_analytics = MagicMock()
            mock_analytics.get_opinion_clusters.return_value = [
                MagicMock(
                    opinion_id=1,
                    stance="Supports X",
                    doc_ids=["doc1"],
                    confidence=0.8,
                    summary="Supports",
                    to_dict=lambda: {
                        "opinion_id": 1,
                        "stance": "Supports X",
                        "doc_ids": ["doc1"],
                        "confidence": 0.8,
                        "summary": "Supports",
                    },
                ),
            ]
            mock_get.return_value = mock_analytics

            resp = app_with_analytics.post(
                f"/api/kb/{internal_name}/analytics/opinions",
                json={"topic": "AI safety", "max_clusters": 3, "use_llm": True},
            )

            assert resp.status_code == 200
            data = resp.get_json()
            assert "opinion_clusters" in data
            assert data["total_clusters"] == 1


class TestCitedResponseAPI:
    """Test cited response API endpoint."""

    def test_cite_no_kb(self, app_with_analytics):
        resp = app_with_analytics.post("/api/kb/nonexistent/analytics/cite", json={})
        assert resp.status_code == 404

    def test_cite_missing_query(self, app_with_analytics, kb_setup):
        internal_name = kb_setup
        resp = app_with_analytics.post(
            f"/api/kb/{internal_name}/analytics/cite",
            json={"required_doc_ids": ["doc1"]},
        )
        assert resp.status_code == 400

    def test_cite_missing_doc_ids(self, app_with_analytics, kb_setup):
        internal_name = kb_setup
        resp = app_with_analytics.post(
            f"/api/kb/{internal_name}/analytics/cite",
            json={"query": "Test question"},
        )
        assert resp.status_code == 400

    def test_cite_basic(self, app_with_analytics, kb_setup):
        internal_name = kb_setup

        with patch("gangdan.kb_routes.get_analytics") as mock_get:
            mock_analytics = MagicMock()
            mock_analytics.generate_cited_response.return_value = {
                "response": "Test answer [1]",
                "citations": [{"doc_id": "doc1", "title": "Test Doc"}],
                "missing_citations": [],
            }
            mock_get.return_value = mock_analytics

            resp = app_with_analytics.post(
                f"/api/kb/{internal_name}/analytics/cite",
                json={
                    "query": "Test question",
                    "required_doc_ids": ["doc1"],
                },
            )

            assert resp.status_code == 200
            data = resp.get_json()
            assert "response" in data
            assert "citations" in data


class TestDocumentContentAPI:
    """Test document content API endpoint."""

    def test_doc_content_no_kb(self, app_with_analytics):
        resp = app_with_analytics.get("/api/kb/nonexistent/documents/doc1/content")
        assert resp.status_code == 404

    def test_doc_content_basic(self, app_with_analytics, kb_setup):
        internal_name = kb_setup

        with patch("gangdan.kb_routes.get_analytics") as mock_get:
            mock_analytics = MagicMock()
            mock_analytics.get_document_content.return_value = {
                "doc_id": "doc1",
                "title": "Test Doc",
                "content": "Test content",
                "source_type": "paper",
                "source_id": "",
                "authors": [],
                "published_date": "",
                "url": "",
                "tags": [],
            }
            mock_get.return_value = mock_analytics

            resp = app_with_analytics.get(
                f"/api/kb/{internal_name}/documents/doc1/content",
                query_string={"max_length": 5000},
            )

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["doc_id"] == "doc1"

    def test_doc_content_not_found(self, app_with_analytics, kb_setup):
        internal_name = kb_setup

        with patch("gangdan.kb_routes.get_analytics") as mock_get:
            mock_analytics = MagicMock()
            mock_analytics.get_document_content.return_value = None
            mock_get.return_value = mock_analytics

            resp = app_with_analytics.get(
                f"/api/kb/{internal_name}/documents/nonexistent/content",
            )

        assert resp.status_code == 404


class TestDimensionInfoAPI:
    """Test dimension info API endpoint."""

    def test_dimension_info_no_kb(self, app_with_analytics):
        resp = app_with_analytics.get("/api/kb/nonexistent/dimension-info")
        assert resp.status_code == 404

    def test_dimension_info_basic(self, app_with_analytics, kb_setup):
        internal_name = kb_setup

        with patch("gangdan.kb_routes.get_kb_manager") as mock_get:
            mock_manager = MagicMock()
            mock_manager.get_kb.return_value = MagicMock(display_name="Test Analytics")
            mock_manager.get_collection_embedding_info.return_value = {
                "embedding_model": "nomic-embed-text",
                "dimension": 768,
                "doc_count": 10,
                "current_model": "nomic-embed-text",
                "compatible": True,
            }
            mock_get.return_value = mock_manager

            resp = app_with_analytics.get(
                f"/api/kb/{internal_name}/dimension-info",
            )

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["kb_name"] == internal_name
            assert data["embedding_model"] == "nomic-embed-text"
            assert data["dimension"] == 768
            assert data["compatible"] is True

    def test_dimension_info_incompatible(self, app_with_analytics, kb_setup):
        internal_name = kb_setup

        with patch("gangdan.kb_routes.get_kb_manager") as mock_get:
            mock_manager = MagicMock()
            mock_manager.get_kb.return_value = MagicMock(display_name="Test Analytics")
            mock_manager.get_collection_embedding_info.return_value = {
                "embedding_model": "old-model",
                "dimension": 512,
                "doc_count": 5,
                "current_model": "nomic-embed-text",
                "compatible": False,
            }
            mock_get.return_value = mock_manager

            resp = app_with_analytics.get(
                f"/api/kb/{internal_name}/dimension-info",
            )

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["compatible"] is False


class TestDimensionMatrixAPI:
    """Test dimension matrix API endpoint."""

    def test_dimension_matrix_basic(self, app_with_analytics):
        with patch("gangdan.kb_routes.get_kb_manager") as mock_get, \
             patch("gangdan.core.config.load_user_kbs") as mock_load, \
             patch("gangdan.core.doc_manager.DOC_SOURCES", {}):
            mock_manager = MagicMock()
            mock_manager.get_collection_embedding_info.return_value = {
                "embedding_model": "nomic-embed-text",
                "dimension": 768,
                "doc_count": 10,
                "current_model": "nomic-embed-text",
                "compatible": True,
            }
            mock_get.return_value = mock_manager
            mock_load.return_value = {"test_kb": {"display_name": "Test KB"}}

            resp = app_with_analytics.get("/api/kb/dimension-matrix")

            assert resp.status_code == 200
            data = resp.get_json()
            assert "knowledge_bases" in data
            assert "current_model" in data
            assert "total" in data
            assert "compatible_count" in data


class TestReindexAPI:
    """Test reindex API endpoint."""

    def test_reindex_no_kb(self, app_with_analytics):
        resp = app_with_analytics.post("/api/kb/nonexistent/reindex", json={})
        assert resp.status_code == 404

    def test_reindex_success(self, app_with_analytics, kb_setup):
        internal_name = kb_setup

        with patch("gangdan.kb_routes.get_kb_manager") as mock_get:
            mock_manager = MagicMock()
            mock_manager.get_kb.return_value = MagicMock(display_name="Test Analytics")
            mock_manager.reindex_kb.return_value = {
                "success": True,
                "re_embeded": 10,
                "model": "nomic-embed-text",
            }
            mock_get.return_value = mock_manager

            resp = app_with_analytics.post(
                f"/api/kb/{internal_name}/reindex",
                json={"model": "nomic-embed-text"},
            )

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True

    def test_reindex_failure(self, app_with_analytics, kb_setup):
        internal_name = kb_setup

        with patch("gangdan.kb_routes.get_kb_manager") as mock_get:
            mock_manager = MagicMock()
            mock_manager.get_kb.return_value = MagicMock(display_name="Test Analytics")
            mock_manager.reindex_kb.return_value = {
                "success": False,
                "error": "Embedding model not available",
            }
            mock_get.return_value = mock_manager

            resp = app_with_analytics.post(
                f"/api/kb/{internal_name}/reindex",
                json={},
            )

            assert resp.status_code == 500
            data = resp.get_json()
            assert data["success"] is False

    def test_reindex_default_model(self, app_with_analytics, kb_setup):
        internal_name = kb_setup

        with patch("gangdan.kb_routes.get_kb_manager") as mock_get:
            mock_manager = MagicMock()
            mock_manager.get_kb.return_value = MagicMock(display_name="Test Analytics")
            mock_manager.reindex_kb.return_value = {
                "success": True,
                "re_embeded": 5,
                "model": "nomic-embed-text",
            }
            mock_get.return_value = mock_manager

            resp = app_with_analytics.post(
                f"/api/kb/{internal_name}/reindex",
                json={},
            )

            assert resp.status_code == 200
            mock_manager.reindex_kb.assert_called_once_with(internal_name, new_model=None)


class TestReviewAPI:
    """Test review generation API endpoint."""

    def test_review_no_kb(self, app_with_analytics):
        resp = app_with_analytics.post("/api/kb/nonexistent/analytics/review", json={})
        assert resp.status_code == 404

    def test_review_missing_doc_ids(self, app_with_analytics, kb_setup):
        internal_name = kb_setup
        resp = app_with_analytics.post(
            f"/api/kb/{internal_name}/analytics/review",
            json={"topic": "AI Safety"},
        )
        assert resp.status_code == 400

    def test_review_basic(self, app_with_analytics, kb_setup):
        internal_name = kb_setup

        with patch("gangdan.kb_routes.get_analytics") as mock_get:
            mock_analytics = MagicMock()
            mock_analytics.generate_review.return_value = {
                "review": "This is a literature review on AI safety.",
                "citations": [{"doc_id": "doc1", "title": "AI Safety Paper"}],
                "missing_citations": [],
                "doc_count": 1,
            }
            mock_get.return_value = mock_analytics

            resp = app_with_analytics.post(
                f"/api/kb/{internal_name}/analytics/review",
                json={
                    "doc_ids": ["doc1"],
                    "topic": "AI Safety",
                    "style": "academic",
                    "language": "en",
                },
            )

            assert resp.status_code == 200
            data = resp.get_json()
            assert "review" in data
            assert "citations" in data
            assert data["doc_count"] == 1

    def test_review_with_doc_ids_filter(self, app_with_analytics, kb_setup):
        internal_name = kb_setup

        with patch("gangdan.kb_routes.get_analytics") as mock_get:
            mock_analytics = MagicMock()
            mock_analytics.generate_review.return_value = {
                "review": "Review based on selected docs.",
                "citations": [],
                "missing_citations": ["doc3"],
                "doc_count": 2,
            }
            mock_get.return_value = mock_analytics

            resp = app_with_analytics.post(
                f"/api/kb/{internal_name}/analytics/review",
                json={
                    "doc_ids": ["doc1", "doc2", "doc3"],
                    "topic": "Test Topic",
                    "style": "technical",
                },
            )

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["missing_citations"] == ["doc3"]


class TestDocIdsFiltering:
    """Test doc_ids filtering across analytics endpoints."""

    def test_topics_with_doc_ids(self, app_with_analytics, kb_setup):
        internal_name = kb_setup

        with patch("gangdan.kb_routes.get_analytics") as mock_get:
            mock_analytics = MagicMock()
            mock_analytics.get_topic_clusters.return_value = []
            mock_get.return_value = mock_analytics

            resp = app_with_analytics.post(
                f"/api/kb/{internal_name}/analytics/topics",
                json={"doc_ids": ["doc1", "doc2"]},
            )

            assert resp.status_code == 200
            mock_analytics.get_topic_clusters.assert_called_once_with(
                internal_name, n_clusters=None, method="kmeans", doc_ids=["doc1", "doc2"]
            )

    def test_pointcloud_with_doc_ids(self, app_with_analytics, kb_setup):
        internal_name = kb_setup

        with patch("gangdan.kb_routes.get_analytics") as mock_get:
            mock_analytics = MagicMock()
            mock_cloud = MagicMock()
            mock_cloud.to_dict.return_value = {"points": [], "dimensions": 2, "method": "pca"}
            mock_analytics.get_point_cloud.return_value = mock_cloud
            mock_analytics._get_embeddings_for_kb.return_value = ([], [], [])
            mock_analytics.get_topic_clusters.return_value = []
            mock_get.return_value = mock_analytics

            resp = app_with_analytics.post(
                f"/api/kb/{internal_name}/analytics/point-cloud",
                json={"dimensions": 2, "method": "pca", "doc_ids": ["doc1"]},
            )

            assert resp.status_code == 200
            mock_analytics.get_point_cloud.assert_called_once()
            call_kwargs = mock_analytics.get_point_cloud.call_args
            assert call_kwargs[1]["doc_ids"] == ["doc1"]

    def test_opinions_with_doc_ids(self, app_with_analytics, kb_setup):
        internal_name = kb_setup

        with patch("gangdan.kb_routes.get_analytics") as mock_get:
            mock_analytics = MagicMock()
            mock_analytics.get_opinion_clusters.return_value = []
            mock_get.return_value = mock_analytics

            resp = app_with_analytics.post(
                f"/api/kb/{internal_name}/analytics/opinions",
                json={"topic": "AI", "doc_ids": ["doc1", "doc2"]},
            )

            assert resp.status_code == 200
            mock_analytics.get_opinion_clusters.assert_called_once_with(
                internal_name, topic="AI", max_clusters=5, use_llm=True, doc_ids=["doc1", "doc2"]
            )
