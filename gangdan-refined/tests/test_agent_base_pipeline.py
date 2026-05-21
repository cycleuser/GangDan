"""White-box unit tests for BaseAgent abstract class and pipeline composition.

Tests cover: agent registration, build_input, output formatting,
error handling, pipeline execution, pipeline __or__, and error propagation.
"""

import json
import sys
import io
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from gangdan_refined.agents.base import BaseAgent, AgentInput, AgentOutput, AgentMetadata
from gangdan_refined.agents.pipeline import Pipeline, PipelineResult, PipelineStep
from gangdan_refined.agents import get_agent, list_agents, AGENT_REGISTRY


class ConcreteAgent(BaseAgent):
    """Test concrete agent for unit testing."""

    name = "test-agent"
    description = "Test agent for unit tests"
    version = "1.0.0"

    def __init__(self, should_fail=False, result_data=None):
        super().__init__()
        self.should_fail = should_fail
        self.result_data = result_data or {"result": "ok"}

    def run(self, input: AgentInput) -> AgentOutput:
        if self.should_fail:
            return AgentOutput(
                success=False,
                error="Intentional failure",
                metadata=AgentMetadata(agent=self.name, version=self.version),
            )
        return AgentOutput(
            success=True,
            data=self.result_data,
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )


class AddOneAgent(BaseAgent):
    """Agent that adds 1 to input.data['value']."""

    name = "add-one"
    description = "Add one"
    version = "1.0.0"

    def run(self, input: AgentInput) -> AgentOutput:
        val = input.data.get("value", 0)
        return AgentOutput(
            success=True,
            data={"value": val + 1, "text": str(val + 1)},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )


class FailAgent(BaseAgent):
    """Agent that always fails."""

    name = "fail-agent"
    description = "Always fails"
    version = "1.0.0"

    def run(self, input: AgentInput) -> AgentOutput:
        return AgentOutput(
            success=False,
            error="Agent failed",
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )


class TestBaseAgent:
    def test_concrete_agent_run_success(self):
        agent = ConcreteAgent()
        result = agent.run(AgentInput(query="test"))
        assert result.success is True
        assert result.data["result"] == "ok"

    def test_concrete_agent_run_failure(self):
        agent = ConcreteAgent(should_fail=True)
        result = agent.run(AgentInput(query="test"))
        assert result.success is False
        assert result.error == "Intentional failure"

    def test_agent_custom_result_data(self):
        agent = ConcreteAgent(result_data={"custom": "data", "count": 42})
        result = agent.run(AgentInput())
        assert result.data["custom"] == "data"
        assert result.data["count"] == 42

    def test_agent_ensure_config(self):
        agent = ConcreteAgent()
        config = agent._ensure_config()
        assert config is not None
        assert hasattr(config, "llm")

    def test_agent_config_property(self):
        agent = ConcreteAgent()
        assert agent.config is not None

    def test_agent_add_common_args(self):
        import argparse
        parser = argparse.ArgumentParser()
        agent = ConcreteAgent()
        agent.add_common_args(parser)
        args = parser.parse_args(["--json", "--model", "qwen3:7b", "--provider", "ollama"])
        assert args.json is True
        assert args.model == "qwen3:7b"
        assert args.provider == "ollama"

    def test_agent_build_input(self):
        import argparse
        parser = argparse.ArgumentParser()
        agent = ConcreteAgent()
        agent.add_common_args(parser)
        args = parser.parse_args(["--json", "--model", "qwen3:7b"])
        inp = agent.build_input(args)
        assert inp.options["model"] == "qwen3:7b"

    def test_agent_output_json_mode(self):
        agent = ConcreteAgent()
        import argparse
        parser = argparse.ArgumentParser()
        agent.add_common_args(parser)
        args = parser.parse_args(["--json"])
        result = AgentOutput(success=True, data={"x": 1}, metadata=AgentMetadata(agent="test"))
        with patch("builtins.print") as mock_print:
            agent.output(result, args)
            output_str = mock_print.call_args[0][0]
            parsed = json.loads(output_str)
            assert parsed["success"] is True

    def test_agent_output_text_mode(self):
        agent = ConcreteAgent()
        import argparse
        parser = argparse.ArgumentParser()
        agent.add_common_args(parser)
        args = parser.parse_args([])
        result = AgentOutput(success=True, data={"response": "hello"}, metadata=AgentMetadata(agent="test"))
        with patch("builtins.print") as mock_print:
            agent.output(result, args)
            mock_print.assert_called_once()
            assert "hello" in mock_print.call_args[0][0]

    def test_agent_output_error(self):
        agent = ConcreteAgent()
        import argparse
        parser = argparse.ArgumentParser()
        agent.add_common_args(parser)
        args = parser.parse_args(["--json"])
        with pytest.raises(SystemExit):
            agent.output_error("test error", args)

    def test_agent_output_error_text_mode(self):
        agent = ConcreteAgent()
        import argparse
        parser = argparse.ArgumentParser()
        agent.add_common_args(parser)
        args = parser.parse_args([])
        with pytest.raises(SystemExit):
            agent.output_error("test error", args)


class TestPipelineStep:
    def test_pipeline_step_creation(self):
        agent = ConcreteAgent()
        step = PipelineStep(agent=agent, name="test-step", duration_ms=100.0, success=True)
        assert step.name == "test-step"
        assert step.duration_ms == 100.0
        assert step.success is True
        assert step.error is None

    def test_pipeline_step_with_error(self):
        agent = ConcreteAgent()
        step = PipelineStep(agent=agent, name="fail-step", duration_ms=50.0, success=False, error="timeout")
        assert step.success is False
        assert step.error == "timeout"


class TestPipelineResult:
    def test_pipeline_result_creation(self):
        result = PipelineResult(
            success=True,
            data={"value": 42},
            pipeline_id="pipe_1",
            total_duration_ms=150.0,
        )
        assert result.success is True
        assert result.data["value"] == 42
        assert result.pipeline_id == "pipe_1"
        assert result.total_duration_ms == 150.0

    def test_pipeline_result_to_dict(self):
        result = PipelineResult(
            success=True,
            data={"x": 1},
            steps=[PipelineStep(agent=MagicMock(), name="step1", duration_ms=100.0, success=True)],
            pipeline_id="pipe_1",
            total_duration_ms=100.0,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["pipeline_id"] == "pipe_1"
        assert len(d["steps"]) == 1
        assert d["steps"][0]["name"] == "step1"
        assert d["total_duration_ms"] == 100.0
        assert d["protocol_version"] == "2.0"

    def test_pipeline_result_to_json(self):
        result = PipelineResult(
            success=True,
            data={"x": 1},
            steps=[],
            pipeline_id="pipe_1",
            total_duration_ms=50.0,
        )
        j = result.to_json()
        parsed = json.loads(j)
        assert parsed["success"] is True
        assert parsed["pipeline_id"] == "pipe_1"


class TestPipeline:
    def test_pipeline_single_agent(self):
        pipeline = Pipeline(ConcreteAgent())
        assert len(pipeline.steps) == 1
        assert pipeline.steps[0].name == "test-agent"

    def test_pipeline_multiple_agents(self):
        pipeline = Pipeline(ConcreteAgent(), AddOneAgent(), AddOneAgent())
        assert len(pipeline.steps) == 3

    def test_pipeline_run_success(self):
        pipeline = Pipeline(AddOneAgent(), AddOneAgent())
        result = pipeline.run(AgentInput(data={"value": 0}))
        assert result.success is True
        assert result.data["value"] == 2
        assert len(result.steps) == 2
        assert result.steps[0].success is True
        assert result.steps[1].success is True
        assert result.total_duration_ms >= 0

    def test_pipeline_run_with_initial_query(self):
        pipeline = Pipeline(ConcreteAgent())
        result = pipeline.run(AgentInput(query="hello"))
        assert result.success is True
        assert result.data["result"] == "ok"

    def test_pipeline_failure_stops(self):
        pipeline = Pipeline(ConcreteAgent(), FailAgent(), AddOneAgent())
        result = pipeline.run(AgentInput(data={"value": 5}))
        assert result.success is False
        assert result.error == "Agent failed"
        assert len(result.steps) == 2
        assert result.steps[0].success is True
        assert result.steps[1].success is False

    def test_pipeline_or_operator(self):
        pipeline = Pipeline(ConcreteAgent()) | AddOneAgent()
        assert len(pipeline.steps) == 2

    def test_pipeline_or_with_class(self):
        pipeline = Pipeline(ConcreteAgent()) | AddOneAgent
        assert len(pipeline.steps) == 2

    def test_pipeline_or_invalid_type(self):
        with pytest.raises(TypeError):
            Pipeline(ConcreteAgent()) | "not_an_agent"

    def test_pipeline_repr(self):
        pipeline = Pipeline(ConcreteAgent(), AddOneAgent())
        assert "test-agent" in repr(pipeline)
        assert "add-one" in repr(pipeline)

    def test_pipeline_custom_id(self):
        pipeline = Pipeline(ConcreteAgent())
        result = pipeline.run(AgentInput(query="test"), pipeline_id="custom_pipe")
        assert result.pipeline_id == "custom_pipe"

    def test_pipeline_auto_id(self):
        pipeline = Pipeline(ConcreteAgent())
        result = pipeline.run(AgentInput(query="test"))
        assert result.pipeline_id.startswith("pipe_")

    def test_pipeline_exception_handling(self):
        class BrokenAgent(BaseAgent):
            name = "broken"
            description = "Raises exception"
            version = "1.0.0"
            def run(self, input):
                raise RuntimeError("Agent crashed")

        pipeline = Pipeline(BrokenAgent())
        result = pipeline.run(AgentInput(query="test"))
        assert result.success is False
        assert "Agent crashed" in result.error

    def test_pipeline_data_accumulation(self):
        pipeline = Pipeline(
            ConcreteAgent(result_data={"a": 1}),
            ConcreteAgent(result_data={"b": 2}),
        )
        result = pipeline.run(AgentInput())
        assert result.success is True
        assert result.data.get("a") == 1
        assert result.data.get("b") == 2

    def test_pipeline_text_propagation(self):
        pipeline = Pipeline(AddOneAgent(), AddOneAgent(), AddOneAgent())
        result = pipeline.run(AgentInput(data={"value": 0}))
        assert result.success is True
        assert result.data["value"] == 3


class TestAgentRegistry:
    def test_get_all_agents(self):
        agents = list_agents()
        assert len(agents) == 14

    def test_get_each_agent(self):
        agent_names = [
            "gd-config", "gd-models", "gd-chat", "gd-search", "gd-summarize",
            "gd-translate", "gd-embed", "gd-ask", "gd-kb", "gd-docs",
            "gd-convert", "gd-research", "gd-learn", "gd-preprint",
        ]
        for name in agent_names:
            agent = get_agent(name)
            assert agent.name == name
            assert agent.version == "2.0.0"

    def test_get_agent_with_prefix(self):
        agent = get_agent("gd-config")
        assert agent.name == "gd-config"

    def test_get_agent_strips_gd_prefix(self):
        agent = get_agent("config")
        assert agent.name == "gd-config"

    def test_get_agent_not_found_raises(self):
        with pytest.raises(KeyError) as exc_info:
            get_agent("nonexistent-agent")
        assert "nonexistent-agent" in str(exc_info.value)

    def test_all_agents_have_run_method(self):
        for name in list_agents():
            agent = get_agent(name)
            assert hasattr(agent, "run")
            assert callable(agent.run)

    def test_all_agents_have_metadata(self):
        for name in list_agents():
            agent = get_agent(name)
            assert agent.name.startswith("gd-")
            assert len(agent.version) > 0
            assert len(agent.description) > 0

    def test_all_agents_return_agent_output(self):
        for name in ["gd-config", "gd-models", "gd-kb", "gd-docs"]:
            agent = get_agent(name)
            result = agent.run(AgentInput())
            assert isinstance(result, AgentOutput)
            assert isinstance(result.success, bool)
            assert isinstance(result.data, dict)
            assert result.metadata.agent.startswith("gd-")