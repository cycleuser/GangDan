"""Tests for web API routes."""

import json
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def app_client():
    """Create a test Flask app client."""
    os = __import__("os")
    os.environ.setdefault("GANGLAN_REFINED_DATA_DIR", "/tmp/gangdan_test_routes")
    from gangdan_refined.web.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestHealthEndpoint:
    def test_health_returns_ok(self, app_client):
        r = app_client.get("/api/health")
        assert r.status_code == 200
        assert r.json["status"] == "ok"


class TestModelsEndpoint:
    @patch("gangdan_refined.llm.factory.create_chat_client")
    def test_models_returns_list(self, mock_factory, app_client):
        mock_client = MagicMock()
        mock_client.get_models.return_value = [{"name": "test-model"}]
        mock_factory.return_value = mock_client
        r = app_client.get("/api/models")
        assert r.status_code == 200


class TestProviderEndpoints:
    def test_providers_returns_list(self, app_client):
        r = app_client.get("/api/providers")
        assert r.status_code == 200
        assert "providers" in r.json

    def test_chat_providers(self, app_client):
        r = app_client.get("/api/chat-providers")
        assert r.status_code == 200

    def test_provider_keys_get(self, app_client):
        r = app_client.get("/api/provider/keys")
        assert r.status_code == 200
        assert r.json["success"] is True


class TestWikiEndpoints:
    def test_wiki_list(self, app_client):
        r = app_client.get("/api/wiki/list")
        assert r.status_code == 200
        assert r.json["success"] is True
        assert "wikis" in r.json

    def test_wiki_status(self, app_client):
        r = app_client.get("/api/wiki/status")
        assert r.status_code == 200
        assert r.json["success"] is True

    def test_wiki_pages(self, app_client):
        r = app_client.get("/api/wiki/pages")
        assert r.status_code == 200
        assert r.json["success"] is True


class TestSystemEndpoints:
    def test_system_stats(self, app_client):
        r = app_client.get("/api/system/stats")
        assert r.status_code == 200
        assert r.json["success"] is True
        assert "stats" in r.json


class TestDocsEndpoints:
    def test_docs_list(self, app_client):
        r = app_client.get("/api/docs/list")
        assert r.status_code == 200
        assert r.json["success"] is True

    def test_docs_batch_download_requires_sources(self, app_client):
        r = app_client.post("/api/docs/batch-download", json={"sources": []})
        assert r.status_code == 200

    def test_docs_upload_no_file(self, app_client):
        r = app_client.post("/api/docs/upload")
        assert r.status_code == 400


class TestKBEndpoints:
    def test_kb_list(self, app_client):
        r = app_client.get("/api/kb/list")
        assert r.status_code == 200

    def test_kb_files_requires_name(self, app_client):
        r = app_client.get("/api/kb/files")
        assert r.status_code == 400

    def test_kb_delete_files_requires_name(self, app_client):
        r = app_client.post("/api/kb/delete-files", json={})
        assert r.status_code == 400

    def test_kb_gallery_requires_name(self, app_client):
        r = app_client.get("/api/kb/gallery")
        assert r.status_code == 400

    def test_kb_detailed_stats_no_name(self, app_client):
        r = app_client.get("/api/kb/detailed-stats")
        assert r.status_code == 200

    def test_kb_dimension_matrix(self, app_client):
        r = app_client.get("/api/kb/dimension-matrix")
        assert r.status_code == 200


class TestLearningEndpoints:
    def test_learning_kb_list(self, app_client):
        r = app_client.get("/api/learning/kb/list")
        assert r.status_code == 200

    def test_learning_questions_generate_no_kb(self, app_client):
        r = app_client.post("/api/learning/questions/generate", json={"kb_names": []})
        assert r.status_code == 200

    def test_learning_guide_sessions(self, app_client):
        r = app_client.get("/api/learning/guide/sessions")
        assert r.status_code == 200

    def test_learning_exam_list(self, app_client):
        r = app_client.get("/api/learning/exam/list")
        assert r.status_code == 200

    def test_learning_lecture_list(self, app_client):
        r = app_client.get("/api/learning/lecture/list")
        assert r.status_code == 200

    def test_learning_research_reports(self, app_client):
        r = app_client.get("/api/learning/research/reports")
        assert r.status_code == 200


class TestResearchEndpoints:
    def test_research_search_requires_query(self, app_client):
        r = app_client.post("/api/research/search", json={})
        assert r.status_code == 400

    def test_research_config_get(self, app_client):
        r = app_client.get("/api/research/config")
        assert r.status_code == 200
        assert r.json["success"] is True

    def test_research_autocomplete_no_query(self, app_client):
        r = app_client.get("/api/research/autocomplete")
        assert r.status_code == 200


class TestPreprintEndpoints:
    def test_preprint_categories(self, app_client):
        r = app_client.get("/api/preprint/categories")
        assert r.status_code == 200

    def test_preprint_scheduler_status(self, app_client):
        r = app_client.get("/api/preprint/scheduler/status")
        assert r.status_code == 200

    def test_preprint_subscriptions_get(self, app_client):
        r = app_client.get("/api/preprint/subscriptions")
        assert r.status_code == 200


class TestTerminalEndpoints:
    def test_terminal_no_command(self, app_client):
        r = app_client.post("/api/terminal", json={})
        assert r.status_code == 400

    def test_execute_no_command(self, app_client):
        r = app_client.post("/api/execute", json={})
        assert r.status_code == 400

    def test_ai_command_no_command(self, app_client):
        r = app_client.post("/api/ai-command", json={})
        assert r.status_code == 400


class TestExportImportEndpoints:
    def test_export_raw_files_no_name(self, app_client):
        r = app_client.get("/api/export-raw-files")
        assert r.status_code == 400

    def test_export_kb_no_name(self, app_client):
        r = app_client.get("/api/export-kb")
        assert r.status_code == 400

    def test_import_raw_files_no_file(self, app_client):
        r = app_client.post("/api/import-raw-files")
        assert r.status_code == 400

    def test_import_kb_no_file(self, app_client):
        r = app_client.post("/api/import-kb")
        assert r.status_code == 400


class TestGithubEndpoints:
    def test_github_search_no_query(self, app_client):
        r = app_client.post("/api/github-search", json={})
        assert r.status_code == 400

    def test_github_download_no_url(self, app_client):
        r = app_client.post("/api/github-download", json={})
        assert r.status_code == 400


class TestChatEndpoints:
    def test_chat_no_message(self, app_client):
        r = app_client.post("/api/chat", json={})
        assert r.status_code == 400

    def test_clear_conversation(self, app_client):
        r = app_client.post("/api/clear")
        assert r.status_code == 200


class TestSettingsEndpoints:
    def test_settings_get(self, app_client):
        r = app_client.get("/api/settings/")
        assert r.status_code == 200

    def test_set_language(self, app_client):
        r = app_client.post("/api/set-language", json={"language": "en"})
        assert r.status_code == 200


class TestPageRoutes:
    def test_index_page(self, app_client):
        r = app_client.get("/")
        assert r.status_code == 200

    def test_research_page(self, app_client):
        r = app_client.get("/research")
        assert r.status_code == 200

    def test_question_page(self, app_client):
        r = app_client.get("/question")
        assert r.status_code == 200

    def test_guide_page(self, app_client):
        r = app_client.get("/guide")
        assert r.status_code == 200