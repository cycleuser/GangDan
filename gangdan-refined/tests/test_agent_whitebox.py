"""White-box unit tests for each agent with mocked dependencies.

Each agent is tested in isolation with all external dependencies mocked.
Tests cover: valid inputs, edge cases, error handling, option parsing.
"""

import json
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from gangdan_refined.agents.protocol import AgentInput, AgentOutput, AgentMetadata


def _make_llm_client_mock(response="Mock response", translation="Mock translation"):
    mock = MagicMock()
    mock.chat.return_value = response
    mock.translate.return_value = translation
    mock.get_models.return_value = [{"name": "mock-model"}]
    return mock


def _make_ollama_mock():
    mock = MagicMock()
    mock.chat.return_value = "Ollama response"
    mock.embed.return_value = [0.1] * 384
    mock.get_models.return_value = ["qwen2.5:7b"]
    mock.is_available.return_value = True
    return mock


class TestConfigAgentWhiteBox:
    def test_show_config(self):
        from gangdan_refined.agents.config_agent import ConfigAgent
        agent = ConfigAgent()
        result = agent.run(AgentInput(options={"action": "show"}))
        assert result.success is True
        assert "config" in result.data
        assert "data_dir" in result.data

    def test_get_config_key(self):
        from gangdan_refined.agents.config_agent import ConfigAgent
        agent = ConfigAgent()
        result = agent.run(AgentInput(options={"action": "get", "key": "llm.chat_model"}))
        assert result.success is True
        assert result.data["key"] == "llm.chat_model"
        assert "value" in result.data

    def test_get_config_nonexistent_key(self):
        from gangdan_refined.agents.config_agent import ConfigAgent
        agent = ConfigAgent()
        result = agent.run(AgentInput(options={"action": "get", "key": "nonexistent.key.that.does.not.exist"}))
        assert result.success is False
        assert "not found" in result.error

    def test_set_config_value(self):
        from gangdan_refined.agents.config_agent import ConfigAgent
        agent = ConfigAgent()
        original = agent.config.llm.chat_model
        try:
            result = agent.run(AgentInput(options={"action": "set", "key": "llm.chat_model", "value": "test-model"}))
            assert result.success is True
            assert result.data["value"] == "test-model"
        finally:
            agent.config.llm.chat_model = original

    def test_set_config_string_to_bool(self):
        from gangdan_refined.agents.config_agent import ConfigAgent
        agent = ConfigAgent()
        result = agent.run(AgentInput(options={"action": "set", "key": "adaptive.auto_chunk_size", "value": "true"}))
        assert result.success is True
        assert result.data["value"] is True

    def test_set_config_string_to_int(self):
        from gangdan_refined.agents.config_agent import ConfigAgent
        agent = ConfigAgent()
        result = agent.run(AgentInput(options={"action": "set", "key": "storage.top_k", "value": "20"}))
        assert result.success is True
        assert result.data["value"] == 20

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

    def test_unknown_action_defaults_to_show(self):
        from gangdan_refined.agents.config_agent import ConfigAgent
        agent = ConfigAgent()
        result = agent.run(AgentInput(options={"action": "unknown"}))
        assert result.success is True
        assert "config" in result.data


class TestModelsAgentWhiteBox:
    @patch("gangdan_refined.agents.models_agent.BaseAgent._get_llm_client")
    def test_list_models(self, mock_get_llm):
        mock_client, _ = _make_llm_client_mock(), "mock-model"
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


class TestChatAgentWhiteBox:
    @patch("gangdan_refined.agents.chat_agent.BaseAgent._get_llm_client")
    def test_basic_chat(self, mock_get_llm):
        mock_client = _make_llm_client_mock("Hello! How can I help?")
        mock_get_llm.return_value = (mock_client, "mock-model")
        from gangdan_refined.agents.chat_agent import ChatAgent
        agent = ChatAgent()
        result = agent.run(AgentInput(query="Hello", options={"model": "mock"}))
        assert result.success is True
        assert result.data["response"] == "Hello! How can I help?"

    def test_empty_message_fails(self):
        from gangdan_refined.agents.chat_agent import ChatAgent
        agent = ChatAgent()
        result = agent.run(AgentInput(query=""))
        assert result.success is False
        assert "No message" in result.error

    @patch("gangdan_refined.agents.chat_agent.BaseAgent._get_llm_client")
    def test_chat_with_system_prompt(self, mock_get_llm):
        mock_client = _make_llm_client_mock("Custom response")
        mock_get_llm.return_value = (mock_client, "mock-model")
        from gangdan_refined.agents.chat_agent import ChatAgent
        agent = ChatAgent()
        result = agent.run(AgentInput(query="Hello", options={"system_prompt": "You are a pirate"}))
        assert result.success is True
        call_args = mock_client.chat.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        assert any(m["role"] == "system" for m in messages)

    @patch("gangdan_refined.agents.chat_agent.BaseAgent._get_llm_client")
    def test_chat_with_language(self, mock_get_llm):
        mock_client = _make_llm_client_mock("Bonjour!")
        mock_get_llm.return_value = (mock_client, "mock-model")
        from gangdan_refined.agents.chat_agent import ChatAgent
        agent = ChatAgent()
        result = agent.run(AgentInput(query="Hello", options={"language": "zh"}))
        assert result.success is True


class TestSummarizeAgentWhiteBox:
    @patch("gangdan_refined.agents.summarize_agent.BaseAgent._get_llm_client")
    def test_summarize_paragraph(self, mock_get_llm):
        mock_client = _make_llm_client_mock("This is a summary.")
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

    @patch("gangdan_refined.agents.summarize_agent.BaseAgent._get_llm_client")
    def test_summarize_bullet_style(self, mock_get_llm):
        mock_client = _make_llm_client_mock("• Point 1\n• Point 2")
        mock_get_llm.return_value = (mock_client, "mock-model")
        from gangdan_refined.agents.summarize_agent import SummarizeAgent
        agent = SummarizeAgent()
        result = agent.run(AgentInput(text="Some text.", options={"style": "bullet"}))
        assert result.success is True
        assert result.data["style"] == "bullet"


class TestTranslateAgentWhiteBox:
    @patch("gangdan_refined.agents.translate_agent.BaseAgent._get_llm_client")
    def test_translate(self, mock_get_llm):
        mock_client = _make_llm_client_mock(translation="你好世界")
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


class TestEmbedAgentWhiteBox:
    @patch("gangdan_refined.llm.ollama.OllamaClient")
    def test_embed(self, MockOllama):
        mock_client = MagicMock()
        mock_client.embed.return_value = [0.1] * 384
        MockOllama.return_value = mock_client
        from gangdan_refined.agents.embed_agent import EmbedAgent
        agent = EmbedAgent()
        result = agent.run(AgentInput(text="Hello world", options={"model": "nomic-embed-text"}))
        assert result.success is True
        assert "dimension" in result.data

    def test_empty_text_fails(self):
        from gangdan_refined.agents.embed_agent import EmbedAgent
        agent = EmbedAgent()
        result = agent.run(AgentInput(text=""))
        assert result.success is False


class TestAskAgentWhiteBox:
    def test_empty_question_fails(self):
        from gangdan_refined.agents.ask_agent import AskAgent
        agent = AskAgent()
        result = agent.run(AgentInput(query=""))
        assert result.success is False
        assert "Question required" in result.error

    @patch("gangdan_refined.agents.ask_agent.BaseAgent._get_llm_client")
    @patch("gangdan_refined.agents.ask_agent.BaseAgent._get_chroma")
    def test_ask_with_kb(self, mock_get_chroma, mock_get_llm):
        mock_chroma = MagicMock()
        mock_chroma.collection_exists.return_value = True
        mock_chroma.search.return_value = [{"content": "relevant context", "metadata": {}}]
        mock_get_chroma.return_value = mock_chroma
        mock_client = _make_llm_client_mock("The answer is 42.")
        mock_get_llm.return_value = (mock_client, "mock-model")
        from gangdan_refined.agents.ask_agent import AskAgent
        agent = AskAgent()
        result = agent.run(AgentInput(query="What is the answer?", options={"kb_names": ["test_kb"]}))
        assert result.success is True
        assert result.data["answer"] == "The answer is 42."
        assert result.data["context_used"] == 1


class TestKBAgentWhiteBox:
    def test_list_kbs(self):
        from gangdan_refined.agents.kb_agent import KBAgent
        agent = KBAgent()
        result = agent.run(AgentInput(options={"action": "list"}))
        assert result.success is True
        assert "kbs" in result.data

    def test_create_without_name_fails(self):
        from gangdan_refined.agents.kb_agent import KBAgent
        agent = KBAgent()
        result = agent.run(AgentInput(options={"action": "create", "name": ""}))
        assert result.success is False

    def test_delete_without_name_fails(self):
        from gangdan_refined.agents.kb_agent import KBAgent
        agent = KBAgent()
        result = agent.run(AgentInput(options={"action": "delete", "name": ""}))
        assert result.success is False

    def test_search_without_query_fails(self):
        from gangdan_refined.agents.kb_agent import KBAgent
        agent = KBAgent()
        result = agent.run(AgentInput(options={"action": "search"}))
        assert result.success is False

    def test_info_without_name_fails(self):
        from gangdan_refined.agents.kb_agent import KBAgent
        agent = KBAgent()
        result = agent.run(AgentInput(options={"action": "info"}))
        assert result.success is False

    def test_unknown_action_defaults_to_list(self):
        from gangdan_refined.agents.kb_agent import KBAgent
        agent = KBAgent()
        result = agent.run(AgentInput(options={"action": "unknown_action"}))
        assert result.success is True
        assert "kbs" in result.data


class TestDocsAgentWhiteBox:
    def test_list_sources(self):
        from gangdan_refined.agents.docs_agent import DocsAgent
        agent = DocsAgent()
        result = agent.run(AgentInput(options={"action": "list"}))
        assert result.success is True
        assert "sources" in result.data

    def test_download_without_source_fails(self):
        from gangdan_refined.agents.docs_agent import DocsAgent
        agent = DocsAgent()
        result = agent.run(AgentInput(options={"action": "download"}))
        assert result.success is False

    def test_index_without_source_fails(self):
        from gangdan_refined.agents.docs_agent import DocsAgent
        agent = DocsAgent()
        result = agent.run(AgentInput(options={"action": "index"}))
        assert result.success is False


class TestConvertAgentWhiteBox:
    def test_no_file_fails(self):
        from gangdan_refined.agents.convert_agent import ConvertAgent
        agent = ConvertAgent()
        result = agent.run(AgentInput())
        assert result.success is False

    def test_nonexistent_file_fails(self):
        from gangdan_refined.agents.convert_agent import ConvertAgent
        agent = ConvertAgent()
        result = agent.run(AgentInput(file_path="/nonexistent/file.pdf"))
        assert result.success is False
        assert "not found" in result.error.lower() or "No such file" in result.error


class TestSearchAgentWhiteBox:
    def test_empty_query_fails(self):
        from gangdan_refined.agents.search_agent import SearchAgent
        agent = SearchAgent()
        result = agent.run(AgentInput(query=""))
        assert result.success is False

    @patch("gangdan_refined.search.web_searcher.WebSearcher")
    def test_web_search_with_mock(self, MockWebSearcher):
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


class TestResearchAgentWhiteBox:
    def test_empty_topic_fails(self):
        from gangdan_refined.agents.research_agent import ResearchAgent
        agent = ResearchAgent()
        result = agent.run(AgentInput(query=""))
        assert result.success is False


class TestLearnAgentWhiteBox:
    def test_question_action_default(self):
        from gangdan_refined.agents.learn_agent import LearnAgent
        agent = LearnAgent()
        result = agent.run(AgentInput(query="", options={"feature": "question"}))
        assert isinstance(result, AgentOutput)

    def test_unknown_feature_defaults_to_question(self):
        from gangdan_refined.agents.learn_agent import LearnAgent
        agent = LearnAgent()
        result = agent.run(AgentInput(query="", options={"feature": "nonexistent"}))
        assert isinstance(result, AgentOutput)


class TestPreprintAgentWhiteBox:
    def test_empty_query_fails(self):
        from gangdan_refined.agents.preprint_agent import PreprintAgent
        agent = PreprintAgent()
        result = agent.run(AgentInput(query="", options={"action": "search"}))
        assert result.success is False

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

    def test_unknown_action_defaults_to_search(self):
        from gangdan_refined.agents.preprint_agent import PreprintAgent
        agent = PreprintAgent()
        result = agent.run(AgentInput(query="", options={"action": "unknown"}))
        assert result.success is False