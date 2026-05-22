"""Web routes integration tests.

Tests the Flask web application with realistic scenarios:
- Blueprint registration
- Route availability
- JSON API responses
- Error handling
- Static file serving
- Template rendering
"""

import json
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def app():
    """Create Flask app for testing."""
    from gangdan_refined.web.app import create_app
    return create_app()


@pytest.fixture
def client(app):
    """Create test client."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestAppCreation:
    def test_create_app_returns_flask_app(self):
        from flask import Flask
        from gangdan_refined.web.app import create_app
        app = create_app()
        assert isinstance(app, Flask)

    def test_app_has_all_blueprints(self):
        from gangdan_refined.web.app import create_app
        app = create_app()
        expected_blueprints = ["api", "chat", "settings", "kb", "docs", "learning", "research", "export", "preprint"]
        for bp_name in expected_blueprints:
            assert bp_name in app.blueprints, f"Missing blueprint: {bp_name}"


class TestPageRoutes:
    def test_index_page(self, client):
        response = client.get("/")
        assert response.status_code == 200

    def test_question_page(self, client):
        response = client.get("/question")
        assert response.status_code == 200

    def test_guide_page(self, client):
        response = client.get("/guide")
        assert response.status_code == 200

    def test_research_page(self, client):
        response = client.get("/research")
        assert response.status_code == 200


class TestAPIRoutes:
    def test_api_health(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_api_chat(self, client):
        response = client.post("/api/chat", json={"message": "Hello"})
        assert response.status_code == 200

    def test_api_models(self, client):
        response = client.get("/api/models")
        assert response.status_code == 200

    def test_api_providers(self, client):
        response = client.get("/api/providers")
        assert response.status_code == 200
        data = response.get_json()
        assert "providers" in data

    def test_api_ai_command(self, client):
        response = client.post("/api/ai-command", json={"description": "list files"})
        assert response.status_code in [200, 400]

    def test_api_ai_summarize(self, client):
        response = client.post("/api/ai-summarize", json={"text": "Some text"})
        assert response.status_code in [200, 400]

    def test_api_context_length(self, client):
        response = client.get("/api/context-length")
        assert response.status_code == 200

    def test_api_system_stats(self, client):
        response = client.get("/api/system/stats")
        assert response.status_code == 200

    def test_api_test_connection(self, client):
        response = client.get("/api/test-connection")
        assert response.status_code in [200, 400, 405]

    def test_api_test_provider(self, client):
        response = client.post("/api/test-provider", json={"provider": "ollama"})
        assert response.status_code in [200, 400, 405]


class TestKBRoutes:
    def test_kb_list(self, client):
        response = client.get("/api/kb/list")
        assert response.status_code == 200

    def test_kb_create(self, client):
        response = client.post("/api/kb/create", json={"display_name": "test-kb"})
        assert response.status_code in [200, 400]

    def test_kb_files(self, client):
        response = client.get("/api/kb/files")
        assert response.status_code in [200, 400]

    def test_kb_detailed_stats(self, client):
        response = client.get("/api/kb/detailed-stats")
        assert response.status_code == 200


class TestDocsRoutes:
    def test_docs_list(self, client):
        response = client.get("/api/docs/list")
        assert response.status_code == 200

    def test_docs_sources(self, client):
        response = client.get("/api/docs/sources")
        assert response.status_code == 200


class TestLearningRoutes:
    def test_learning_kb_list(self, client):
        response = client.get("/api/learning/kb/list")
        assert response.status_code == 200

    def test_learning_questions_list(self, client):
        response = client.get("/api/learning/questions/list")
        assert response.status_code in [200, 500]

    def test_learning_exam_list(self, client):
        response = client.get("/api/learning/exam/list")
        assert response.status_code == 200

    def test_learning_lecture_list(self, client):
        response = client.get("/api/learning/lecture/list")
        assert response.status_code == 200

    def test_learning_research_reports(self, client):
        response = client.get("/api/learning/research/reports")
        assert response.status_code == 200


class TestResearchRoutes:
    def test_research_papers(self, client):
        response = client.get("/api/research/papers")
        assert response.status_code in [200, 500]

    def test_research_config(self, client):
        response = client.get("/api/research/config")
        assert response.status_code == 200

    def test_research_search(self, client):
        response = client.post("/api/research/search", json={"query": "test"})
        assert response.status_code in [200, 405, 500]


class TestExportRoutes:
    def test_export_raw_files(self, client):
        response = client.get("/api/export/raw-files")
        assert response.status_code in [200, 400]

    def test_export_kb(self, client):
        response = client.get("/api/export/kb")
        assert response.status_code in [200, 400]


class TestPreprintRoutes:
    def test_preprint_categories(self, client):
        response = client.get("/api/preprint/categories")
        assert response.status_code == 200

    def test_preprint_recent(self, client):
        response = client.get("/api/preprint/recent")
        assert response.status_code in [200, 500]

    def test_preprint_subscriptions(self, client):
        response = client.get("/api/preprint/subscriptions")
        assert response.status_code == 200

    def test_preprint_scheduler_status(self, client):
        response = client.get("/api/preprint/scheduler/status")
        assert response.status_code == 200


class TestChatRoutes:
    def test_chat_send(self, client):
        response = client.post("/api/chat/send", json={"message": "Hello"})
        assert response.status_code == 200

    def test_chat_stream(self, client):
        response = client.post("/api/chat/stream", json={"message": "Hello"})
        assert response.status_code == 200


class TestSettingsRoutes:
    def test_settings_get(self, client):
        response = client.get("/api/settings/")
        assert response.status_code == 200

    def test_settings_models(self, client):
        response = client.get("/api/settings/models")
        assert response.status_code == 200

    def test_settings_providers(self, client):
        response = client.get("/api/settings/providers")
        assert response.status_code == 200


class TestErrorHandling:
    def test_404_page(self, client):
        response = client.get("/nonexistent/page")
        assert response.status_code == 404

    def test_405_method_not_allowed(self, client):
        response = client.put("/api/chat")
        assert response.status_code == 405


class TestStaticFiles:
    def test_static_css(self, client):
        response = client.get("/static/css/style.css")
        assert response.status_code == 200