"""Comprehensive functional tests for all 14 agents.

Tests cover:
- Core functionality with mocked dependencies
- Input validation and error handling
- Option parsing and configuration
- Pipeline composition scenarios
- Edge cases and boundary conditions
- SOTA design compliance checks
"""

import json
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path

from gangdan_refined.agents.protocol import AgentInput, AgentOutput, AgentMetadata


# ============================================================================
# Mock Helpers
# ============================================================================

def make_mock_llm_client(response="Mock response", **kwargs):
    """Create a mock LLM client with configurable responses."""
    mock = MagicMock()
    mock.chat.return_value = response
    mock.translate.return_value = kwargs.get("translation", "Mock translation")
    mock.get_models.return_value = [{"name": "mock-model"}]
    return mock


def make_mock_ollama_client(embedding=None, **kwargs):
    """Create a mock Ollama client for embedding operations."""
    mock = MagicMock()
    mock.embed.return_value = embedding or [0.1] * 384
    mock.get_models.return_value = ["qwen2.5:7b", "nomic-embed-text"]
    mock.is_available.return_value = True
    return mock


def make_mock_chroma(collections=None, search_results=None):
    """Create a mock ChromaDB client."""
    mock = MagicMock()
    if collections:
        mock.collection_exists.side_effect = lambda name: name in collections
    else:
        mock.collection_exists.return_value = True
    if search_results:
        mock.search.return_value = search_results
    else:
        mock.search.return_value = [{"content": "Test context", "metadata": {"source": "test"}}]
    return mock


def make_mock_kb_manager(kbs=None):
    """Create a mock KB manager."""
    mock = MagicMock()
    if kbs:
        mock.list_kbs.return_value = kbs
    else:
        mock.list_kbs.return_value = []
    mock.create_kb.return_value = MagicMock(to_dict=lambda: {"name": "test-kb"})
    mock.delete_kb.return_value = True
    mock.get_kb.return_value = MagicMock(to_dict=lambda: {"name": "test-kb"})
    mock.search_kb.return_value = [{"content": "result", "metadata": {}}]
    mock.search_all_kbs.return_value = [{"content": "result", "metadata": {}}]
    return mock


# ============================================================================
# Test ConfigAgent
# ============================================================================

class TestConfigAgentFunctional:
    def test_show_config_returns_all_groups(self):
        from gangdan_refined.agents.config_agent import ConfigAgent
        agent = ConfigAgent()
        result = agent.run(AgentInput(options={"action": "show"}))
        assert result.success is True
        assert "config" in result.data
        config = result.data["config"]
        expected_groups = ["proxy", "llm", "storage", "search", "document", "preprint", "research", "adaptive", "ui"]
        for group in expected_groups:
            assert group in config, f"Missing config group: {group}"

    def test_get_valid_key(self):
        from gangdan_refined.agents.config_agent import ConfigAgent
        agent = ConfigAgent()
        result = agent.run(AgentInput(options={"action": "get", "key": "llm.chat_model"}))
        assert result.success is True
        assert result.data["key"] == "llm.chat_model"
        assert "value" in result.data

    def test_get_invalid_key(self):
        from gangdan_refined.agents.config_agent import ConfigAgent
        agent = ConfigAgent()
        result = agent.run(AgentInput(options={"action": "get", "key": "nonexistent.key.xyz"}))
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_set_string_value(self):
        from gangdan_refined.agents.config_agent import ConfigAgent
        agent = ConfigAgent()
        result = agent.run(AgentInput(options={"action": "set", "key": "llm.chat_model", "value": "test-model"}))
        assert result.success is True
        assert result.data["value"] == "test-model"

    def test_set_boolean_value(self):
        from gangdan_refined.agents.config_agent import ConfigAgent
        agent = ConfigAgent()
        result = agent.run(AgentInput(options={"action": "set", "key": "adaptive.auto_chunk_size", "value": "true"}))
        assert result.success is True
        assert result.data["value"] is True

    def test_set_integer_value(self):
        from gangdan_refined.agents.config_agent import ConfigAgent
        agent = ConfigAgent()
        result = agent.run(AgentInput(options={"action": "set", "key": "storage.top_k", "value": "20"}))
        assert result.success is True
        assert result.data["value"] == 20

    def test_set_float_value(self):
        from gangdan_refined.agents.config_agent import ConfigAgent
        agent = ConfigAgent()
        result = agent.run(AgentInput(options={"action": "set", "key": "llm.chat_temperature", "value": "0.85"}))
        assert result.success is True
        assert result.data["value"] == 0.85

    def test_list_providers(self):
        from gangdan_refined.agents.config_agent import ConfigAgent
        agent = ConfigAgent()
        result = agent.run(AgentInput(options={"action": "providers"}))
        assert result.success is True
        assert "providers" in result.data
        assert len(result.data["providers"]) > 0

    def test_reset_config(self):
        from gangdan_refined.agents.config_agent import ConfigAgent
        agent = ConfigAgent()
        result = agent.run(AgentInput(options={"action": "reset"}))
        assert result.success is True
        assert "reset" in result.data.get("message", "").lower()

    def test_unknown_action_defaults_to_show(self):
        from gangdan_refined.agents.config_agent import ConfigAgent
        agent = ConfigAgent()
        result = agent.run(AgentInput(options={"action": "unknown_action_xyz"}))
        assert result.success is True
        assert "config" in result.data


# ============================================================================
# Test ChatAgent
# ============================================================================

class TestChatAgentFunctional:
    @patch("gangdan_refined.agents.chat_agent.BaseAgent._get_llm_client")
    def test_basic_chat(self, mock_get_llm):
        mock_client = make_mock_llm_client("Hello! How can I help?")
        mock_get_llm.return_value = (mock_client, "mock-model")
        from gangdan_refined.agents.chat_agent import ChatAgent
        agent = ChatAgent()
        result = agent.run(AgentInput(query="Hello", options={"model": "mock"}))
        assert result.success is True
        assert result.data["response"] == "Hello! How can I help?"
        assert result.data["model"] == "mock-model"

    def test_empty_message_fails(self):
        from gangdan_refined.agents.chat_agent import ChatAgent
        agent = ChatAgent()
        result = agent.run(AgentInput(query=""))
        assert result.success is False
        assert "message" in result.error.lower()

    @patch("gangdan_refined.agents.chat_agent.BaseAgent._get_llm_client")
    def test_chat_with_system_prompt(self, mock_get_llm):
        mock_client = make_mock_llm_client("Custom response")
        mock_get_llm.return_value = (mock_client, "mock-model")
        from gangdan_refined.agents.chat_agent import ChatAgent
        agent = ChatAgent()
        result = agent.run(AgentInput(query="Hello", options={"system_prompt": "You are a pirate"}))
        assert result.success is True
        call_args = mock_client.chat.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        assert any(m["role"] == "system" and "pirate" in m["content"] for m in messages)

    @patch("gangdan_refined.agents.chat_agent.BaseAgent._get_llm_client")
    def test_chat_with_language(self, mock_get_llm):
        mock_client = make_mock_llm_client("Bonjour!")
        mock_get_llm.return_value = (mock_client, "mock-model")
        from gangdan_refined.agents.chat_agent import ChatAgent
        agent = ChatAgent()
        result = agent.run(AgentInput(query="Hello", options={"language": "zh"}))
        assert result.success is True
        call_args = mock_client.chat.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        assert any(m["role"] == "system" and "zh" in m["content"] for m in messages)

    @patch("gangdan_refined.agents.chat_agent.BaseAgent._get_llm_client")
    def test_chat_llm_failure(self, mock_get_llm):
        mock_client = MagicMock()
        mock_client.chat.side_effect = RuntimeError("Connection refused")
        mock_get_llm.return_value = (mock_client, "mock-model")
        from gangdan_refined.agents.chat_agent import ChatAgent
        agent = ChatAgent()
        result = agent.run(AgentInput(query="Hello", options={"model": "mock"}))
        assert result.success is False
        assert "Connection refused" in result.error

    @patch("gangdan_refined.agents.chat_agent.BaseAgent._get_llm_client")
    def test_chat_with_provider_and_api_key(self, mock_get_llm):
        mock_client = make_mock_llm_client("API response")
        mock_get_llm.return_value = (mock_client, "gpt-4")
        from gangdan_refined.agents.chat_agent import ChatAgent
        agent = ChatAgent()
        result = agent.run(AgentInput(query="Hello", options={
            "provider": "openai",
            "api_key": "sk-test",
            "base_url": "https://api.openai.com",
            "model": "gpt-4"
        }))
        assert result.success is True
        mock_get_llm.assert_called_once_with(
            provider="openai",
            model="gpt-4",
            api_key="sk-test",
            base_url="https://api.openai.com"
        )


# ============================================================================
# Test SearchAgent
# ============================================================================

class TestSearchAgentFunctional:
    def test_empty_query_fails(self):
        from gangdan_refined.agents.search_agent import SearchAgent
        agent = SearchAgent()
        result = agent.run(AgentInput(query=""))
        assert result.success is False
        assert "query" in result.error.lower()

    @patch("gangdan_refined.search.web_searcher.WebSearcher")
    def test_web_search(self, MockWebSearcher):
        mock_searcher = MagicMock()
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"title": "Test Result", "url": "https://example.com"}
        mock_searcher.search.return_value = [mock_result]
        MockWebSearcher.return_value = mock_searcher

        from gangdan_refined.agents.search_agent import SearchAgent
        agent = SearchAgent()
        result = agent.run(AgentInput(query="quantum computing", options={"source": "web"}))
        assert result.success is True
        assert result.data["count"] == 1
        assert result.data["source"] == "web"
        assert "results" in result.data

    @patch("gangdan_refined.search.web_searcher.WebSearcher")
    def test_web_search_exception(self, MockWebSearcher):
        MockWebSearcher.side_effect = RuntimeError("Network error")
        from gangdan_refined.agents.search_agent import SearchAgent
        agent = SearchAgent()
        result = agent.run(AgentInput(query="test", options={"source": "web"}))
        assert result.success is False
        assert "Network error" in result.error

    @patch("gangdan_refined.search.research_searcher.ResearchSearcher")
    def test_academic_search(self, MockResearchSearcher):
        mock_searcher = MagicMock()
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"title": "Paper", "url": "https://arxiv.org/abs/1234"}
        mock_searcher.search.return_value = [mock_result]
        MockResearchSearcher.return_value = mock_searcher

        from gangdan_refined.agents.search_agent import SearchAgent
        agent = SearchAgent()
        result = agent.run(AgentInput(query="machine learning", options={"source": "arxiv"}))
        assert result.success is True
        assert result.data["source"] == "arxiv"
        assert result.data["count"] >= 0


# ============================================================================
# Test SummarizeAgent
# ============================================================================

class TestSummarizeAgentFunctional:
    @patch("gangdan_refined.agents.summarize_agent.BaseAgent._get_llm_client")
    def test_summarize_paragraph(self, mock_get_llm):
        mock_client = make_mock_llm_client("This is a summary.")
        mock_get_llm.return_value = (mock_client, "mock-model")
        from gangdan_refined.agents.summarize_agent import SummarizeAgent
        agent = SummarizeAgent()
        result = agent.run(AgentInput(text="Long text to summarize.", options={"style": "paragraph"}))
        assert result.success is True
        assert result.data["summary"] == "This is a summary."
        assert result.data["style"] == "paragraph"

    def test_empty_text_fails(self):
        from gangdan_refined.agents.summarize_agent import SummarizeAgent
        agent = SummarizeAgent()
        result = agent.run(AgentInput(text=""))
        assert result.success is False
        assert "text" in result.error.lower()

    @patch("gangdan_refined.agents.summarize_agent.BaseAgent._get_llm_client")
    def test_summarize_bullet_style(self, mock_get_llm):
        mock_client = make_mock_llm_client("• Point 1\n• Point 2")
        mock_get_llm.return_value = (mock_client, "mock-model")
        from gangdan_refined.agents.summarize_agent import SummarizeAgent
        agent = SummarizeAgent()
        result = agent.run(AgentInput(text="Some text.", options={"style": "bullet"}))
        assert result.success is True
        assert result.data["style"] == "bullet"

    @patch("gangdan_refined.agents.summarize_agent.BaseAgent._get_llm_client")
    def test_summarize_with_language(self, mock_get_llm):
        mock_client = make_mock_llm_client("中文摘要")
        mock_get_llm.return_value = (mock_client, "mock-model")
        from gangdan_refined.agents.summarize_agent import SummarizeAgent
        agent = SummarizeAgent()
        result = agent.run(AgentInput(text="English text", options={"language": "zh"}))
        assert result.success is True


# ============================================================================
# Test TranslateAgent
# ============================================================================

class TestTranslateAgentFunctional:
    @patch("gangdan_refined.agents.translate_agent.BaseAgent._get_llm_client")
    def test_translate(self, mock_get_llm):
        mock_client = make_mock_llm_client(translation="你好世界")
        mock_get_llm.return_value = (mock_client, "mock-model")
        from gangdan_refined.agents.translate_agent import TranslateAgent
        agent = TranslateAgent()
        result = agent.run(AgentInput(text="Hello world", options={"target_language": "zh"}))
        assert result.success is True
        assert result.data["translation"] == "你好世界"

    def test_empty_text_fails(self):
        from gangdan_refined.agents.translate_agent import TranslateAgent
        agent = TranslateAgent()
        result = agent.run(AgentInput(text=""))
        assert result.success is False
        assert "text" in result.error.lower()


# ============================================================================
# Test EmbedAgent
# ============================================================================

class TestEmbedAgentFunctional:
    @patch("gangdan_refined.llm.ollama.OllamaClient")
    def test_embed(self, MockOllama):
        mock_client = make_mock_ollama_client()
        MockOllama.return_value = mock_client
        from gangdan_refined.agents.embed_agent import EmbedAgent
        agent = EmbedAgent()
        result = agent.run(AgentInput(text="Hello world", options={"model": "nomic-embed-text"}))
        assert result.success is True
        assert "dimension" in result.data
        assert result.data["dimension"] == 384

    def test_empty_text_fails(self):
        from gangdan_refined.agents.embed_agent import EmbedAgent
        agent = EmbedAgent()
        result = agent.run(AgentInput(text=""))
        assert result.success is False
        assert "text" in result.error.lower()

    @patch("gangdan_refined.llm.ollama.OllamaClient")
    def test_embed_ollama_failure(self, MockOllama):
        MockOllama.side_effect = RuntimeError("Ollama not running")
        from gangdan_refined.agents.embed_agent import EmbedAgent
        agent = EmbedAgent()
        result = agent.run(AgentInput(text="Hello world"))
        assert result.success is False
        assert "Ollama not running" in result.error


# ============================================================================
# Test AskAgent
# ============================================================================

class TestAskAgentFunctional:
    def test_empty_question_fails(self):
        from gangdan_refined.agents.ask_agent import AskAgent
        agent = AskAgent()
        result = agent.run(AgentInput(query=""))
        assert result.success is False
        assert "question" in result.error.lower()

    @patch("gangdan_refined.agents.ask_agent.BaseAgent._get_llm_client")
    @patch("gangdan_refined.agents.ask_agent.BaseAgent._get_chroma")
    def test_ask_with_kb(self, mock_get_chroma, mock_get_llm):
        mock_chroma = make_mock_chroma(collections=["test_kb"])
        mock_get_chroma.return_value = mock_chroma
        mock_client = make_mock_llm_client("The answer is 42.")
        mock_get_llm.return_value = (mock_client, "mock-model")
        from gangdan_refined.agents.ask_agent import AskAgent
        agent = AskAgent()
        result = agent.run(AgentInput(query="What is the answer?", options={"kb_names": ["test_kb"]}))
        assert result.success is True
        assert result.data["answer"] == "The answer is 42."
        assert result.data["context_used"] >= 0

    @patch("gangdan_refined.agents.ask_agent.BaseAgent._get_llm_client")
    @patch("gangdan_refined.agents.ask_agent.BaseAgent._get_chroma")
    def test_ask_without_kb(self, mock_get_chroma, mock_get_llm):
        mock_chroma = make_mock_chroma(collections=[])
        mock_get_chroma.return_value = mock_chroma
        mock_client = make_mock_llm_client("General answer.")
        mock_get_llm.return_value = (mock_client, "mock-model")
        from gangdan_refined.agents.ask_agent import AskAgent
        agent = AskAgent()
        result = agent.run(AgentInput(query="What is RAG?", options={"kb_names": []}))
        assert result.success is True
        assert result.data["answer"] == "General answer."


# ============================================================================
# Test KBAgent
# ============================================================================

class TestKBAgentFunctional:
    @patch("gangdan_refined.storage.kb_manager.CustomKBManager")
    def test_list_kbs(self, MockKBManager):
        mock_mgr = make_mock_kb_manager()
        MockKBManager.return_value = mock_mgr
        from gangdan_refined.agents.kb_agent import KBAgent
        agent = KBAgent()
        result = agent.run(AgentInput(options={"action": "list"}))
        assert result.success is True
        assert "kbs" in result.data
        assert "count" in result.data

    def test_create_without_name_fails(self):
        from gangdan_refined.agents.kb_agent import KBAgent
        agent = KBAgent()
        result = agent.run(AgentInput(options={"action": "create", "name": ""}))
        assert result.success is False
        assert "name" in result.error.lower()

    def test_delete_without_name_fails(self):
        from gangdan_refined.agents.kb_agent import KBAgent
        agent = KBAgent()
        result = agent.run(AgentInput(options={"action": "delete", "name": ""}))
        assert result.success is False
        assert "name" in result.error.lower()

    def test_search_without_query_fails(self):
        from gangdan_refined.agents.kb_agent import KBAgent
        agent = KBAgent()
        result = agent.run(AgentInput(options={"action": "search"}))
        assert result.success is False
        assert "query" in result.error.lower()

    def test_info_without_name_fails(self):
        from gangdan_refined.agents.kb_agent import KBAgent
        agent = KBAgent()
        result = agent.run(AgentInput(options={"action": "info"}))
        assert result.success is False
        assert "name" in result.error.lower()

    def test_unknown_action_defaults_to_list(self):
        from gangdan_refined.agents.kb_agent import KBAgent
        agent = KBAgent()
        result = agent.run(AgentInput(options={"action": "unknown_action_xyz"}))
        assert result.success is True
        assert "kbs" in result.data


# ============================================================================
# Test DocsAgent
# ============================================================================

class TestDocsAgentFunctional:
    def test_list_sources(self):
        from gangdan_refined.agents.docs_agent import DocsAgent
        agent = DocsAgent()
        result = agent.run(AgentInput(options={"action": "list"}))
        assert result.success is True
        assert "sources" in result.data
        assert "count" in result.data

    def test_download_without_source_fails(self):
        from gangdan_refined.agents.docs_agent import DocsAgent
        agent = DocsAgent()
        result = agent.run(AgentInput(options={"action": "download"}))
        assert result.success is False
        assert "source" in result.error.lower()

    def test_index_without_source_fails(self):
        from gangdan_refined.agents.docs_agent import DocsAgent
        agent = DocsAgent()
        result = agent.run(AgentInput(options={"action": "index"}))
        assert result.success is False
        assert "source" in result.error.lower()


# ============================================================================
# Test ConvertAgent
# ============================================================================

class TestConvertAgentFunctional:
    def test_no_file_fails(self):
        from gangdan_refined.agents.convert_agent import ConvertAgent
        agent = ConvertAgent()
        result = agent.run(AgentInput())
        assert result.success is False
        assert "file" in result.error.lower()

    def test_nonexistent_file_fails(self):
        from gangdan_refined.agents.convert_agent import ConvertAgent
        agent = ConvertAgent()
        result = agent.run(AgentInput(file_path="/nonexistent/file.pdf"))
        assert result.success is False
        assert "not found" in result.error.lower() or "file" in result.error.lower()


# ============================================================================
# Test ResearchAgent
# ============================================================================

class TestResearchAgentFunctional:
    def test_empty_topic_fails(self):
        from gangdan_refined.agents.research_agent import ResearchAgent
        agent = ResearchAgent()
        result = agent.run(AgentInput(query=""))
        assert result.success is False
        assert "topic" in result.error.lower()


# ============================================================================
# Test LearnAgent
# ============================================================================

class TestLearnAgentFunctional:
    def test_question_action_default(self):
        from gangdan_refined.agents.learn_agent import LearnAgent
        agent = LearnAgent()
        result = agent.run(AgentInput(query="", options={"feature": "question"}))
        assert isinstance(result, AgentOutput)

    def test_unknown_feature_defaults_to_question(self):
        from gangdan_refined.agents.learn_agent import LearnAgent
        agent = LearnAgent()
        result = agent.run(AgentInput(query="", options={"feature": "nonexistent_feature_xyz"}))
        assert isinstance(result, AgentOutput)


# ============================================================================
# Test PreprintAgent
# ============================================================================

class TestPreprintAgentFunctional:
    def test_empty_query_fails(self):
        from gangdan_refined.agents.preprint_agent import PreprintAgent
        agent = PreprintAgent()
        result = agent.run(AgentInput(query="", options={"action": "search"}))
        assert result.success is False
        assert "query" in result.error.lower()

    def test_categories(self):
        from gangdan_refined.agents.preprint_agent import PreprintAgent
        agent = PreprintAgent()
        result = agent.run(AgentInput(options={"action": "categories"}))
        assert result.success is True
        assert "categories" in result.data

    def test_convert_without_paper_fails(self):
        from gangdan_refined.agents.preprint_agent import PreprintAgent
        agent = PreprintAgent()
        result = agent.run(AgentInput(options={"action": "convert"}))
        assert result.success is False
        assert "paper_id" in result.error.lower() or "source_url" in result.error.lower()

    def test_unknown_action_defaults_to_search(self):
        from gangdan_refined.agents.preprint_agent import PreprintAgent
        agent = PreprintAgent()
        result = agent.run(AgentInput(query="", options={"action": "unknown_action_xyz"}))
        assert result.success is False


# ============================================================================
# Test ModelsAgent
# ============================================================================

class TestModelsAgentFunctional:
    @patch("gangdan_refined.agents.models_agent.BaseAgent._get_llm_client")
    def test_list_models(self, mock_get_llm):
        mock_client = make_mock_llm_client()
        mock_get_llm.return_value = (mock_client, "mock-model")
        from gangdan_refined.agents.models_agent import ModelsAgent
        agent = ModelsAgent()
        result = agent.run(AgentInput(options={"provider": "ollama"}))
        assert result.success is True
        assert "models" in result.data

    def test_model_info_with_name(self):
        from gangdan_refined.agents.models_agent import ModelsAgent
        agent = ModelsAgent()
        result = agent.run(AgentInput(query="qwen2.5:7b"))
        assert isinstance(result, AgentOutput)

    @patch("gangdan_refined.agents.models_agent.BaseAgent._get_llm_client")
    def test_list_models_exception(self, mock_get_llm):
        mock_get_llm.side_effect = RuntimeError("Connection failed")
        from gangdan_refined.agents.models_agent import ModelsAgent
        agent = ModelsAgent()
        result = agent.run(AgentInput())
        assert result.success is False
        assert "Connection failed" in result.error


# ============================================================================
# Test Pipeline Composition - Real-World Scenarios
# ============================================================================

class TestPipelineRealWorldScenarios:
    def test_search_summarize_translate_pipeline(self):
        """Test a realistic search → summarize → translate pipeline."""
        from gangdan_refined.agents.pipeline import Pipeline
        from gangdan_refined.agents.base import BaseAgent

        class MockSearchAgent(BaseAgent):
            name = "gd-search"
            description = "Search"
            version = "2.0.0"
            def run(self, input):
                return AgentOutput(
                    success=True,
                    data={"results": [{"title": "Quantum Computing Overview", "content": "Quantum computing uses quantum mechanical phenomena..."}], "count": 1, "source": "web"},
                    metadata=AgentMetadata(agent=self.name, version=self.version),
                )

        class MockSummarizeAgent(BaseAgent):
            name = "gd-summarize"
            description = "Summarize"
            version = "2.0.0"
            def run(self, input):
                return AgentOutput(
                    success=True,
                    data={"summary": "Quantum computing uses quantum mechanics for computation.", "style": "paragraph"},
                    metadata=AgentMetadata(agent=self.name, version=self.version),
                )

        class MockTranslateAgent(BaseAgent):
            name = "gd-translate"
            description = "Translate"
            version = "2.0.0"
            def run(self, input):
                return AgentOutput(
                    success=True,
                    data={"translation": "量子计算利用量子力学进行计算。", "source_language": "en", "target_language": "zh"},
                    metadata=AgentMetadata(agent=self.name, version=self.version),
                )

        pipeline = Pipeline(MockSearchAgent(), MockSummarizeAgent(), MockTranslateAgent())
        result = pipeline.run(AgentInput(query="quantum computing"))
        assert result.success is True
        assert len(result.steps) == 3
        assert all(step.success for step in result.steps)
        assert "translation" in result.data
        assert "量子计算" in result.data["translation"]

    def test_kb_ask_pipeline(self):
        """Test a knowledge base query pipeline."""
        from gangdan_refined.agents.pipeline import Pipeline
        from gangdan_refined.agents.base import BaseAgent

        class MockKBAgent(BaseAgent):
            name = "gd-kb"
            description = "KB"
            version = "2.0.0"
            def run(self, input):
                return AgentOutput(
                    success=True,
                    data={"kbs": [{"name": "ml-kb", "count": 10}], "count": 1},
                    metadata=AgentMetadata(agent=self.name, version=self.version),
                )

        class MockAskAgent(BaseAgent):
            name = "gd-ask"
            description = "Ask"
            version = "2.0.0"
            def run(self, input):
                return AgentOutput(
                    success=True,
                    data={"answer": "Machine learning is a subset of AI.", "context_used": 5},
                    metadata=AgentMetadata(agent=self.name, version=self.version),
                )

        pipeline = Pipeline(MockKBAgent(), MockAskAgent())
        result = pipeline.run(AgentInput(query="What is ML?", options={"kb_names": ["ml-kb"]}))
        assert result.success is True
        assert len(result.steps) == 2
        assert "answer" in result.data

    def test_pipeline_error_propagation(self):
        """Test that errors properly propagate through pipeline."""
        from gangdan_refined.agents.pipeline import Pipeline
        from gangdan_refined.agents.base import BaseAgent

        class FailingAgent(BaseAgent):
            name = "gd-fail"
            description = "Fails"
            version = "2.0.0"
            def run(self, input):
                return AgentOutput(
                    success=False,
                    error="Service unavailable",
                    metadata=AgentMetadata(agent=self.name, version=self.version),
                )

        class NeverReachedAgent(BaseAgent):
            name = "gd-never"
            description = "Never reached"
            version = "2.0.0"
            def run(self, input):
                return AgentOutput(
                    success=True,
                    data={"should": "not"},
                    metadata=AgentMetadata(agent=self.name, version=self.version),
                )

        pipeline = Pipeline(FailingAgent(), NeverReachedAgent())
        result = pipeline.run(AgentInput(query="test"))
        assert result.success is False
        assert result.error == "Service unavailable"
        assert len(result.steps) == 1
        assert result.steps[0].success is False

    def test_pipeline_data_accumulation(self):
        """Test that pipeline accumulates data across steps."""
        from gangdan_refined.agents.pipeline import Pipeline
        from gangdan_refined.agents.base import BaseAgent

        class AddKeyAgent(BaseAgent):
            name = "gd-addkey"
            description = "Add key"
            version = "2.0.0"
            def __init__(self, key, val):
                super().__init__()
                self.key = key
                self.val = val
            def run(self, input):
                data = dict(input.data) if input.data else {}
                data[self.key] = self.val
                return AgentOutput(
                    success=True,
                    data=data,
                    metadata=AgentMetadata(agent=self.name, version=self.version),
                )

        pipeline = Pipeline(AddKeyAgent("a", 1), AddKeyAgent("b", 2), AddKeyAgent("c", 3))
        result = pipeline.run(AgentInput())
        assert result.success is True
        assert result.data["a"] == 1
        assert result.data["b"] == 2
        assert result.data["c"] == 3

    def test_pipeline_text_propagation(self):
        """Test that text flows correctly through pipeline."""
        from gangdan_refined.agents.pipeline import Pipeline
        from gangdan_refined.agents.base import BaseAgent

        class TextTransformAgent(BaseAgent):
            name = "gd-transform"
            description = "Transform text"
            version = "2.0.0"
            def __init__(self, transform_fn):
                super().__init__()
                self.transform_fn = transform_fn
            def run(self, input):
                text = input.text or input.query or ""
                transformed = self.transform_fn(text)
                return AgentOutput(
                    success=True,
                    data={"text": transformed, "response": transformed},
                    metadata=AgentMetadata(agent=self.name, version=self.version),
                )

        pipeline = Pipeline(
            TextTransformAgent(lambda x: x.upper()),
            TextTransformAgent(lambda x: x + "!"),
            TextTransformAgent(lambda x: f"Result: {x}")
        )
        result = pipeline.run(AgentInput(query="hello"))
        assert result.success is True
        assert "Result: HELLO!" in result.data.get("text", result.data.get("response", ""))


# ============================================================================
# Test Edge Cases and Boundary Conditions
# ============================================================================

class TestEdgeCases:
    def test_agent_input_with_none_values(self):
        inp = AgentInput(query=None, text=None, file_path=None)
        assert inp.query is None
        assert inp.text is None
        assert inp.file_path is None
        d = inp.to_dict()
        assert d == {}

    def test_agent_output_with_empty_data(self):
        out = AgentOutput(success=True, data={}, metadata=AgentMetadata(agent="test"))
        assert out.data == {}
        assert out.to_stdout_text() == "{}"

    def test_agent_output_with_nested_data(self):
        out = AgentOutput(success=True, data={"a": {"b": {"c": [1, 2, 3]}}}, metadata=AgentMetadata(agent="test"))
        d = out.to_dict()
        assert d["data"]["a"]["b"]["c"] == [1, 2, 3]

    def test_agent_output_unicode(self):
        out = AgentOutput(success=True, data={"text": "你好世界 🌍"}, metadata=AgentMetadata(agent="test"))
        j = out.to_json()
        parsed = json.loads(j)
        assert parsed["data"]["text"] == "你好世界 🌍"

    def test_agent_metadata_with_special_chars(self):
        m = AgentMetadata(agent="gd-中文", pipeline_id="pipe_测试")
        d = m.to_dict()
        assert d["agent"] == "gd-中文"
        assert d["pipeline_id"] == "pipe_测试"

    def test_validate_input_empty_dict(self):
        from gangdan_refined.agents.protocol import validate_input
        inp = validate_input({})
        assert isinstance(inp, AgentInput)
        assert inp.query is None

    def test_validate_output_empty_dict(self):
        from gangdan_refined.agents.protocol import validate_output
        out = validate_output({})
        assert isinstance(out, AgentOutput)
        assert out.success is False

    def test_decode_input_empty_json_object(self):
        from gangdan_refined.agents.protocol import decode_input
        result = decode_input(raw_json="{}")
        assert result is not None
        assert result.query is None

    def test_decode_input_non_json_string(self):
        from gangdan_refined.agents.protocol import decode_input
        result = decode_input(raw_json="not json at all")
        assert result is not None
        assert result.text == "not json at all"

    def test_agent_input_roundtrip_complex(self):
        inp = AgentInput(
            query="test query with special chars: @#$%",
            text="text with\nnewlines\nand tabs\t",
            file_path="/path/to/file.pdf",
            data={"key": [1, 2, 3], "nested": {"a": True, "b": None}},
            options={"model": "qwen3:7b", "language": "zh"},
            metadata=AgentMetadata(agent="gd-test", pipeline_id="pipe_123"),
        )
        d = inp.to_dict()
        inp2 = AgentInput.from_dict(d)
        assert inp2.query == inp.query
        assert inp2.text == inp.text
        assert inp2.data["key"] == [1, 2, 3]

    def test_agent_output_roundtrip_with_error(self):
        out = AgentOutput(success=False, error="test error", metadata=AgentMetadata(agent="test"))
        j = out.to_json()
        out2 = AgentOutput.from_json(j)
        assert out2.success is False
        assert out2.error == "test error"


# ============================================================================
# Test SOTA Design Compliance
# ============================================================================

class TestSOTACompliance:
    def test_all_agents_have_unique_names(self):
        """All agents must have unique names for routing."""
        from gangdan_refined.agents import list_agents, get_agent
        names = list_agents()
        assert len(names) == len(set(names)), "Duplicate agent names found"

    def test_all_agents_follow_protocol(self):
        """All agents must return AgentOutput."""
        from gangdan_refined.agents import list_agents, get_agent
        for name in list_agents():
            agent = get_agent(name)
            result = agent.run(AgentInput())
            assert isinstance(result, AgentOutput), f"{name} does not return AgentOutput"

    def test_all_agents_have_metadata(self):
        """All agents must have name, description, version."""
        from gangdan_refined.agents import list_agents, get_agent
        for name in list_agents():
            agent = get_agent(name)
            assert agent.name, f"{name} has no name"
            assert agent.description, f"{name} has no description"
            assert agent.version, f"{name} has no version"
            assert agent.version == "2.0.0", f"{name} has wrong version"

    def test_all_agents_handle_empty_input_gracefully(self):
        """All agents must handle empty input without crashing."""
        from gangdan_refined.agents import list_agents, get_agent
        for name in list_agents():
            agent = get_agent(name)
            result = agent.run(AgentInput())
            assert isinstance(result, AgentOutput), f"{name} crashed on empty input"

    def test_protocol_version_consistency(self):
        """All agent outputs must include protocol_version."""
        from gangdan_refined.agents import list_agents, get_agent
        from gangdan_refined.agents.protocol import AGENT_PROTOCOL_VERSION
        for name in list_agents():
            agent = get_agent(name)
            result = agent.run(AgentInput())
            d = result.to_dict()
            assert d.get("protocol_version") == AGENT_PROTOCOL_VERSION, f"{name} missing protocol_version"

    def test_pipeline_or_operator_commutativity(self):
        """Pipeline | operator should work correctly."""
        from gangdan_refined.agents.pipeline import Pipeline
        from gangdan_refined.agents.base import BaseAgent

        class A(BaseAgent):
            name = "gd-a"
            description = "A"
            version = "2.0.0"
            def run(self, input):
                return AgentOutput(success=True, data={"a": 1}, metadata=AgentMetadata(agent=self.name))

        class B(BaseAgent):
            name = "gd-b"
            description = "B"
            version = "2.0.0"
            def run(self, input):
                return AgentOutput(success=True, data={"b": 2}, metadata=AgentMetadata(agent=self.name))

        p1 = Pipeline(A()) | B()
        p2 = Pipeline(A(), B())
        assert len(p1.steps) == len(p2.steps) == 2

    def test_agent_registry_get_agent_with_prefix(self):
        """get_agent should work with and without gd- prefix."""
        from gangdan_refined.agents import get_agent
        agent1 = get_agent("gd-config")
        agent2 = get_agent("config")
        assert agent1.name == agent2.name

    def test_agent_registry_list_agents(self):
        """list_agents should return all 14 agents."""
        from gangdan_refined.agents import list_agents
        agents = list_agents()
        assert len(agents) == 14
        expected = ["gd-config", "gd-models", "gd-chat", "gd-search", "gd-summarize", "gd-translate", "gd-embed", "gd-ask", "gd-kb", "gd-docs", "gd-convert", "gd-research", "gd-learn", "gd-preprint"]
        for name in expected:
            assert name in agents, f"Missing agent: {name}"