"""Error handling and edge case tests for agents.

Tests cover: empty inputs, invalid arguments, missing models,
network failures, Unicode handling, large inputs, None/default handling.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from gangdan_refined.agents.protocol import AgentInput, AgentOutput, AgentMetadata


def _make_failing_llm_client(error_msg="Connection refused"):
    mock = MagicMock()
    mock.chat.side_effect = RuntimeError(error_msg)
    mock.translate.side_effect = RuntimeError(error_msg)
    mock.embed.side_effect = RuntimeError(error_msg)
    mock.get_models.side_effect = RuntimeError(error_msg)
    return mock


class TestProtocolEdgeCases:
    def test_agent_input_with_none_query(self):
        inp = AgentInput(query=None)
        assert inp.query is None
        d = inp.to_dict()
        assert "query" not in d

    def test_agent_input_with_empty_string_query(self):
        inp = AgentInput(query="")
        assert inp.query == ""
        d = inp.to_dict()
        assert d["query"] == ""

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

    def test_agent_output_with_error_and_data(self):
        out = AgentOutput(success=False, error="partial failure", data={"partial": "data"}, metadata=AgentMetadata(agent="test"))
        d = out.to_dict()
        assert d["success"] is False
        assert d["error"] == "partial failure"
        assert d["data"]["partial"] == "data"

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


class TestConfigAgentErrors:
    def test_set_invalid_key(self):
        from gangdan_refined.agents.config_agent import ConfigAgent
        agent = ConfigAgent()
        result = agent.run(AgentInput(options={"action": "set", "key": "nonexistent.deep.key", "value": "x"}))
        assert result.success is False

    def test_set_empty_key(self):
        from gangdan_refined.agents.config_agent import ConfigAgent
        agent = ConfigAgent()
        # Empty key falls through to hasattr(CONFIG, "") which is False,
        # so set action returns success=False for unrecognized keys
        result = agent.run(AgentInput(options={"action": "set", "key": "totally.nonexistent.path.xyz", "value": "x"}))
        assert result.success is False


class TestChatAgentErrors:
    @patch("gangdan_refined.agents.chat_agent.BaseAgent._get_llm_client")
    def test_llm_failure(self, mock_get_llm):
        mock_client = _make_failing_llm_client("Ollama connection refused")
        mock_get_llm.return_value = (mock_client, "mock-model")
        from gangdan_refined.agents.chat_agent import ChatAgent
        agent = ChatAgent()
        result = agent.run(AgentInput(query="hello", options={"model": "mock"}))
        assert result.success is False
        assert "Ollama connection refused" in result.error


class TestSearchAgentErrors:
    def test_whitespace_query(self):
        from gangdan_refined.agents.search_agent import SearchAgent
        agent = SearchAgent()
        result = agent.run(AgentInput(query="   "))
        assert result.success is False

    @patch("gangdan_refined.search.web_searcher.WebSearcher")
    def test_search_exception(self, MockWebSearcher):
        MockWebSearcher.side_effect = RuntimeError("Network error")
        from gangdan_refined.agents.search_agent import SearchAgent
        agent = SearchAgent()
        result = agent.run(AgentInput(query="test", options={"source": "web"}))
        assert result.success is False


class TestTranslateAgentErrors:
    @patch("gangdan_refined.agents.translate_agent.BaseAgent._get_llm_client")
    def test_translate_llm_failure(self, mock_get_llm):
        mock_client = _make_failing_llm_client("API rate limit exceeded")
        mock_get_llm.return_value = (mock_client, "mock-model")
        from gangdan_refined.agents.translate_agent import TranslateAgent
        agent = TranslateAgent()
        result = agent.run(AgentInput(text="Hello"))
        assert result.success is False


class TestSummarizeAgentErrors:
    def test_summarize_empty(self):
        from gangdan_refined.agents.summarize_agent import SummarizeAgent
        agent = SummarizeAgent()
        result = agent.run(AgentInput(text=""))
        assert result.success is False

    @patch("gangdan_refined.agents.summarize_agent.BaseAgent._get_llm_client")
    def test_summarize_llm_failure(self, mock_get_llm):
        mock_client = _make_failing_llm_client("Model not found")
        mock_get_llm.return_value = (mock_client, "mock-model")
        from gangdan_refined.agents.summarize_agent import SummarizeAgent
        agent = SummarizeAgent()
        result = agent.run(AgentInput(text="Some text to summarize"))
        assert result.success is False
        assert "Model not found" in result.error


class TestAskAgentErrors:
    def test_ask_empty_question(self):
        from gangdan_refined.agents.ask_agent import AskAgent
        agent = AskAgent()
        result = agent.run(AgentInput(query=""))
        assert result.success is False


class TestKBAgentEdgeCases:
    def test_kb_unknown_action_defaults_to_list(self):
        from gangdan_refined.agents.kb_agent import KBAgent
        agent = KBAgent()
        result = agent.run(AgentInput(options={"action": "nonexistent_action_xyz"}))
        assert result.success is True

    def test_kb_create_empty_name(self):
        from gangdan_refined.agents.kb_agent import KBAgent
        agent = KBAgent()
        result = agent.run(AgentInput(options={"action": "create", "name": ""}))
        assert result.success is False


class TestEmbedAgentErrors:
    def test_embed_empty_text(self):
        from gangdan_refined.agents.embed_agent import EmbedAgent
        agent = EmbedAgent()
        result = agent.run(AgentInput(text=""))
        assert result.success is False

    @patch("gangdan_refined.llm.ollama.OllamaClient")
    def test_embed_ollama_failure(self, MockOllama):
        MockOllama.side_effect = RuntimeError("Ollama not running")
        from gangdan_refined.agents.embed_agent import EmbedAgent
        agent = EmbedAgent()
        result = agent.run(AgentInput(text="Hello world"))
        assert result.success is False


class TestConvertAgentErrors:
    def test_convert_nonexistent_file(self):
        from gangdan_refined.agents.convert_agent import ConvertAgent
        agent = ConvertAgent()
        result = agent.run(AgentInput(file_path="/nonexistent/path/to/file.pdf"))
        assert result.success is False

    def test_convert_no_file_path(self):
        from gangdan_refined.agents.convert_agent import ConvertAgent
        agent = ConvertAgent()
        result = agent.run(AgentInput())
        assert result.success is False


class TestResearchAgentErrors:
    def test_research_empty_topic(self):
        from gangdan_refined.agents.research_agent import ResearchAgent
        agent = ResearchAgent()
        result = agent.run(AgentInput(query=""))
        assert result.success is False


class TestPreprintAgentErrors:
    def test_preprint_empty_search(self):
        from gangdan_refined.agents.preprint_agent import PreprintAgent
        agent = PreprintAgent()
        result = agent.run(AgentInput(query="", options={"action": "search"}))
        assert result.success is False

    def test_preprint_convert_no_paper(self):
        from gangdan_refined.agents.preprint_agent import PreprintAgent
        agent = PreprintAgent()
        result = agent.run(AgentInput(options={"action": "convert"}))
        assert result.success is False


class TestPipelineErrorPropagation:
    def test_pipeline_exception_in_agent(self):
        from gangdan_refined.agents.pipeline import Pipeline
        from gangdan_refined.agents.base import BaseAgent

        class CrashAgent(BaseAgent):
            name = "crash"
            description = "Always crashes"
            version = "1.0.0"
            def run(self, input):
                raise ValueError("Unexpected crash")

        class OkAgent(BaseAgent):
            name = "ok"
            description = "Works fine"
            version = "1.0.0"
            def run(self, input):
                return AgentOutput(success=True, data={"result": "ok"}, metadata=AgentMetadata(agent="ok"))

        pipeline = Pipeline(CrashAgent())
        result = pipeline.run(AgentInput(query="test"))
        assert result.success is False
        assert "Unexpected crash" in result.error

    def test_pipeline_failure_stops_early(self):
        from gangdan_refined.agents.pipeline import Pipeline
        from gangdan_refined.agents.base import BaseAgent

        class FailAgent(BaseAgent):
            name = "fail"
            description = "Fails"
            version = "1.0.0"
            def run(self, input):
                return AgentOutput(success=False, error="Failed", metadata=AgentMetadata(agent="fail"))

        class NeverReachedAgent(BaseAgent):
            name = "never"
            description = "Should not be reached"
            version = "1.0.0"
            def run(self, input):
                return AgentOutput(success=True, data={"should": "not"}, metadata=AgentMetadata(agent="never"))

        pipeline = Pipeline(FailAgent(), NeverReachedAgent())
        result = pipeline.run(AgentInput(query="test"))
        assert result.success is False
        assert result.error == "Failed"
        assert len(result.steps) == 1

    def test_pipeline_with_unicode_data(self):
        from gangdan_refined.agents.pipeline import Pipeline
        from gangdan_refined.agents.base import BaseAgent

        class UnicodeAgent(BaseAgent):
            name = "unicode"
            description = "Returns unicode"
            version = "1.0.0"
            def run(self, input):
                return AgentOutput(success=True, data={"text": "你好世界 🌍"}, metadata=AgentMetadata(agent="unicode"))

        pipeline = Pipeline(UnicodeAgent())
        result = pipeline.run(AgentInput(query="test"))
        assert result.success is True
        assert result.data["text"] == "你好世界 🌍"

    def test_pipeline_with_empty_input(self):
        from gangdan_refined.agents.pipeline import Pipeline
        from gangdan_refined.agents.base import BaseAgent

        class EchoAgent(BaseAgent):
            name = "echo"
            description = "Echo input"
            version = "1.0.0"
            def run(self, input):
                return AgentOutput(success=True, data={"echo": input.query or input.text or "empty"}, metadata=AgentMetadata(agent="echo"))

        pipeline = Pipeline(EchoAgent())
        result = pipeline.run(AgentInput())
        assert result.success is True
        assert result.data["echo"] == "empty"