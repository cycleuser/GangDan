"""Tests for the agent pipeline system."""

import json
import pytest

from gangdan_refined.agents import (
    BaseAgent, AgentInput, AgentOutput, AgentMetadata,
    Pipeline, PipelineResult, get_agent, list_agents,
    AGENT_PROTOCOL_VERSION,
)
from gangdan_refined.agents.protocol import encode_output, decode_input, validate_output


class TestAgentProtocol:
    def test_agent_input_to_dict(self):
        inp = AgentInput(query="test", text="hello", options={"key": "val"})
        d = inp.to_dict()
        assert d["query"] == "test"
        assert d["text"] == "hello"
        assert d["options"]["key"] == "val"

    def test_agent_input_from_dict(self):
        d = {"query": "test", "data": {"x": 1}, "options": {"model": "qwen"}}
        inp = AgentInput.from_dict(d)
        assert inp.query == "test"
        assert inp.data["x"] == 1
        assert inp.options["model"] == "qwen"

    def test_agent_output_to_dict(self):
        out = AgentOutput(success=True, data={"key": "val"}, metadata=AgentMetadata(agent="test"))
        d = out.to_dict()
        assert d["success"] is True
        assert d["data"]["key"] == "val"
        assert d["protocol_version"] == AGENT_PROTOCOL_VERSION

    def test_agent_output_to_json(self):
        out = AgentOutput(success=True, data={"x": 1}, metadata=AgentMetadata(agent="test"))
        j = out.to_json()
        parsed = json.loads(j)
        assert parsed["success"] is True
        assert parsed["data"]["x"] == 1

    def test_agent_output_from_json(self):
        j = '{"success": true, "data": {"x": 1}, "error": null, "metadata": {"agent": "test", "version": "2.0.0", "timestamp": "", "pipeline_id": null}}'
        out = AgentOutput.from_json(j)
        assert out.success is True
        assert out.data["x"] == 1

    def test_agent_output_text_fallback(self):
        out = AgentOutput(success=False, error="something went wrong")
        assert "something went wrong" in out.to_stdout_text()

    def test_encode_output_json(self):
        out = AgentOutput(success=True, data={"x": 1}, metadata=AgentMetadata(agent="test"))
        text = encode_output(out, json_mode=True)
        parsed = json.loads(text)
        assert parsed["success"] is True

    def test_encode_output_text(self):
        out = AgentOutput(success=True, data={"response": "hello world"}, metadata=AgentMetadata(agent="test"))
        text = encode_output(out, json_mode=False)
        assert "hello world" in text

    def test_validate_output(self):
        out = validate_output({"success": True, "data": {"x": 1}, "metadata": {}})
        assert isinstance(out, AgentOutput)
        assert out.success is True

    def test_decode_input_from_json_string(self):
        inp = decode_input(raw_json='{"query": "test", "data": {}}')
        assert inp.query == "test"

    def test_agent_metadata(self):
        meta = AgentMetadata(agent="gd-search", version="2.0.0", pipeline_id="pipe_123")
        d = meta.to_dict()
        assert d["agent"] == "gd-search"
        assert d["pipeline_id"] == "pipe_123"
        assert d["version"] == "2.0.0"
        assert d["timestamp"] != ""


class TestAgentRegistry:
    def test_list_agents(self):
        agents = list_agents()
        assert len(agents) == 14
        assert "gd-config" in agents
        assert "gd-search" in agents
        assert "gd-ask" in agents

    def test_get_agent(self):
        config = get_agent("gd-config")
        assert config.name == "gd-config"
        assert config.version == "2.0.0"

    def test_get_agent_with_prefix(self):
        agent = get_agent("gd-search")
        assert agent.name == "gd-search"

    def test_get_agent_not_found(self):
        with pytest.raises(KeyError):
            get_agent("gd-nonexistent")


class TestConfigAgent:
    def test_show_config(self):
        agent = get_agent("gd-config")
        result = agent.run(AgentInput(options={"action": "show"}))
        assert result.success is True
        assert "config" in result.data
        assert "data_dir" in result.data

    def test_get_config_key(self):
        agent = get_agent("gd-config")
        result = agent.run(AgentInput(options={"action": "get", "key": "llm.chat_model"}))
        assert result.success is True
        assert result.data["key"] == "llm.chat_model"

    def test_list_providers(self):
        agent = get_agent("gd-config")
        result = agent.run(AgentInput(options={"action": "providers"}))
        assert result.success is True
        assert "providers" in result.data


class TestModelsAgent:
    def test_list_models(self):
        agent = get_agent("gd-models")
        result = agent.run(AgentInput(options={"provider": "ollama"}))
        assert result.success is True
        assert "models" in result.data
        assert "count" in result.data


class TestSearchAgent:
    def test_web_search(self):
        agent = get_agent("gd-search")
        result = agent.run(AgentInput(query="test query", options={"source": "web"}))
        assert isinstance(result, AgentOutput)


class TestTranslateAgent:
    def test_translate(self):
        agent = get_agent("gd-translate")
        result = agent.run(AgentInput(text="Hello", options={"target_language": "zh"}))
        assert isinstance(result, AgentOutput)
        assert result.success is True
        assert "translation" in result.data


class TestSummarizeAgent:
    def test_summarize(self):
        agent = get_agent("gd-summarize")
        result = agent.run(AgentInput(text="This is a test text to summarize.", options={"style": "paragraph", "length": "brief"}))
        assert isinstance(result, AgentOutput)


class TestKBAgent:
    def test_list_kbs(self):
        agent = get_agent("gd-kb")
        result = agent.run(AgentInput(options={"action": "list"}))
        assert result.success is True
        assert "kbs" in result.data


class TestDocsAgent:
    def test_list_sources(self):
        agent = get_agent("gd-docs")
        result = agent.run(AgentInput(options={"action": "list"}))
        assert result.success is True
        assert "sources" in result.data


class TestPipeline:
    def test_basic_pipeline(self):
        pipeline = Pipeline(get_agent("gd-config"), get_agent("gd-models"))
        result = pipeline.run(AgentInput(options={"action": "show"}))
        assert isinstance(result, PipelineResult)
        assert len(result.steps) == 2
        assert result.success is True
        assert result.total_duration_ms > 0

    def test_pipeline_repr(self):
        pipeline = Pipeline(get_agent("gd-config"), get_agent("gd-models"))
        assert "gd-config" in repr(pipeline)
        assert "gd-models" in repr(pipeline)

    def test_pipeline_result_to_json(self):
        pipeline = Pipeline(get_agent("gd-config"), get_agent("gd-models"))
        result = pipeline.run(AgentInput(options={"action": "show"}))
        j = result.to_json()
        parsed = json.loads(j)
        assert parsed["success"] is True
        assert "steps" in parsed
        assert "pipeline_id" in parsed

    def test_pipeline_chaining_via_or(self):
        config = get_agent("gd-config")
        models = get_agent("gd-models")
        pipeline = Pipeline(config) | models
        assert len(pipeline.steps) == 2

    def test_pipeline_error_handling(self):
        agent = get_agent("gd-ask")
        result = agent.run(AgentInput(query=""))  # Empty question should fail
        assert result.success is False
        assert result.error is not None