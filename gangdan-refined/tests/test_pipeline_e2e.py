"""Pipeline composition end-to-end tests.

Tests cover: multi-agent pipelines, data propagation,
text flow, error handling, and real agent composition patterns.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from gangdan_refined.agents.protocol import AgentInput, AgentOutput, AgentMetadata
from gangdan_refined.agents.pipeline import Pipeline, PipelineResult, PipelineStep
from gangdan_refined.agents.base import BaseAgent


class DoubleAgent(BaseAgent):
    name = "gd-double"
    description = "Doubles the input value"
    version = "2.0.0"

    def run(self, input: AgentInput) -> AgentOutput:
        val = input.data.get("value", 0)
        if isinstance(val, (int, float)):
            new_val = val * 2
        else:
            new_val = val
        return AgentOutput(
            success=True,
            data={"value": new_val, "text": str(new_val)},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )


class AppendAgent(BaseAgent):
    name = "gd-append"
    description = "Appends text to input"
    version = "2.0.0"

    def __init__(self, suffix="!"):
        super().__init__()
        self.suffix = suffix

    def run(self, input: AgentInput) -> AgentOutput:
        text = input.text or input.query or ""
        new_text = text + self.suffix
        return AgentOutput(
            success=True,
            data={"appended": new_text, "text": new_text},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )


class CounterAgent(BaseAgent):
    name = "gd-counter"
    description = "Counts characters"
    version = "2.0.0"

    def run(self, input: AgentInput) -> AgentOutput:
        text = input.text or input.query or ""
        return AgentOutput(
            success=True,
            data={"count": len(text), "text": str(len(text))},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )


class SplitAgent(BaseAgent):
    name = "gd-split"
    description = "Splits text into words"
    version = "2.0.0"

    def run(self, input: AgentInput) -> AgentOutput:
        text = input.text or input.query or ""
        words = text.split()
        return AgentOutput(
            success=True,
            data={"words": words, "count": len(words), "text": " ".join(words)},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )


class ConditionalAgent(BaseAgent):
    name = "gd-conditional"
    description = "Fails if input value is negative"
    version = "2.0.0"

    def run(self, input: AgentInput) -> AgentOutput:
        val = input.data.get("value", 0)
        if val < 0:
            return AgentOutput(
                success=False,
                error=f"Negative value: {val}",
                metadata=AgentMetadata(agent=self.name, version=self.version),
            )
        return AgentOutput(
            success=True,
            data={"value": val, "positive": True},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )


class TestPipelineComposition:
    def test_double_pipeline(self):
        pipeline = Pipeline(DoubleAgent(), DoubleAgent())
        result = pipeline.run(AgentInput(data={"value": 3}))
        assert result.success is True
        assert result.data["value"] == 12

    def test_triple_pipeline(self):
        pipeline = Pipeline(DoubleAgent(), DoubleAgent(), DoubleAgent())
        result = pipeline.run(AgentInput(data={"value": 1}))
        assert result.success is True
        assert result.data["value"] == 8

    def test_append_then_count(self):
        pipeline = Pipeline(AppendAgent(suffix=" world"), CounterAgent())
        result = pipeline.run(AgentInput(query="hello"))
        assert result.success is True
        assert result.data["count"] == 11

    def test_append_chain(self):
        pipeline = Pipeline(AppendAgent(suffix=" world"), AppendAgent(suffix="!"))
        result = pipeline.run(AgentInput(query="hello"))
        assert result.success is True
        assert result.data["text"] == "hello world!"

    def test_split_accumulates_data(self):
        pipeline = Pipeline(SplitAgent())
        result = pipeline.run(AgentInput(text="hello world foo"))
        assert result.success is True
        assert result.data["count"] == 3
        assert result.data["words"] == ["hello", "world", "foo"]

    def test_split_then_double_value(self):
        class ValueFromCountAgent(BaseAgent):
            name = "gd-valfromcount"
            description = "Extracts value from count"
            version = "2.0.0"
            def run(self, input):
                return AgentOutput(
                    success=True,
                    data={"value": input.data.get("count", 0) * 2},
                    metadata=AgentMetadata(agent=self.name, version=self.version),
                )
        pipeline = Pipeline(SplitAgent(), ValueFromCountAgent())
        result = pipeline.run(AgentInput(text="a b c"))
        assert result.success is True
        assert result.data["value"] == 6

    def test_conditional_success(self):
        pipeline = Pipeline(ConditionalAgent(), DoubleAgent())
        result = pipeline.run(AgentInput(data={"value": 5}))
        assert result.success is True
        assert result.data["value"] == 10

    def test_conditional_failure_stops_pipeline(self):
        pipeline = Pipeline(ConditionalAgent(), DoubleAgent())
        result = pipeline.run(AgentInput(data={"value": -1}))
        assert result.success is False
        assert result.error == "Negative value: -1"
        assert len(result.steps) == 1

    def test_pipeline_data_accumulation(self):
        class AddKeyAgent(BaseAgent):
            name = "gd-addkey"
            description = "Adds a key"
            version = "2.0.0"
            def __init__(self, key, val):
                super().__init__()
                self.key = key
                self.val = val
            def run(self, input):
                data = dict(input.data) if input.data else {}
                data[self.key] = self.val
                return AgentOutput(success=True, data=data, metadata=AgentMetadata(agent=self.name, version=self.version))

        pipeline = Pipeline(AddKeyAgent("a", 1), AddKeyAgent("b", 2), AddKeyAgent("c", 3))
        result = pipeline.run(AgentInput())
        assert result.success is True
        assert result.data["a"] == 1
        assert result.data["b"] == 2
        assert result.data["c"] == 3

    def test_pipeline_text_propagation(self):
        class UpperAgent(BaseAgent):
            name = "gd-upper"
            description = "Uppercase"
            version = "2.0.0"
            def run(self, input):
                text = input.text or input.query or ""
                return AgentOutput(success=True, data={"text": text.upper(), "response": text.upper()}, metadata=AgentMetadata(agent=self.name, version=self.version))

        pipeline = Pipeline(AppendAgent(suffix=" world"), UpperAgent())
        result = pipeline.run(AgentInput(query="hello"))
        assert result.success is True
        assert "HELLO WORLD" in result.data.get("text", result.data.get("response", ""))

    def test_pipeline_or_operator(self):
        pipeline = Pipeline(DoubleAgent()) | DoubleAgent()
        assert len(pipeline.steps) == 2

    def test_pipeline_or_operator_chain(self):
        pipeline = Pipeline(AppendAgent(suffix=" A")) | AppendAgent(suffix=" B") | AppendAgent(suffix=" C")
        result = pipeline.run(AgentInput(query="start"))
        assert result.success is True
        assert result.data["text"] == "start A B C"

    def test_pipeline_result_serialization(self):
        pipeline = Pipeline(DoubleAgent())
        result = pipeline.run(AgentInput(data={"value": 7}))
        d = result.to_dict()
        assert d["success"] is True
        assert d["data"]["value"] == 14
        assert d["pipeline_id"].startswith("pipe_")
        assert d["protocol_version"] == "2.0"
        j = result.to_json()
        parsed = json.loads(j)
        assert parsed["success"] is True

    def test_pipeline_step_timing(self):
        pipeline = Pipeline(DoubleAgent(), AppendAgent(suffix="!"))
        result = pipeline.run(AgentInput(data={"value": 5}, query="hello"))
        assert result.success is True
        assert len(result.steps) == 2
        assert result.steps[0].success is True
        assert result.steps[1].success is True
        assert result.steps[0].duration_ms >= 0
        assert result.steps[1].duration_ms >= 0

    def test_pipeline_with_initial_query(self):
        class QueryAgent(BaseAgent):
            name = "gd-query"
            description = "Uses query"
            version = "2.0.0"
            def run(self, input):
                return AgentOutput(success=True, data={"query": input.query or ""}, metadata=AgentMetadata(agent=self.name, version=self.version))

        pipeline = Pipeline(QueryAgent(), DoubleAgent())
        result = pipeline.run(AgentInput(query="test query"))
        assert result.success is True
        assert result.data["query"] == "test query"


class TestPipelineWithRealAgents:
    def test_config_agent_in_pipeline(self):
        from gangdan_refined.agents.config_agent import ConfigAgent
        pipeline = Pipeline(ConfigAgent())
        result = pipeline.run(AgentInput(options={"action": "show"}))
        assert result.success is True
        assert "config" in result.data

    def test_kb_agent_list_in_pipeline(self):
        from gangdan_refined.agents.kb_agent import KBAgent
        pipeline = Pipeline(KBAgent())
        result = pipeline.run(AgentInput(options={"action": "list"}))
        assert result.success is True
        assert "kbs" in result.data

    def test_models_agent_in_pipeline(self):
        from gangdan_refined.agents.models_agent import ModelsAgent
        pipeline = Pipeline(ModelsAgent())
        result = pipeline.run(AgentInput(options={"provider": "ollama"}))
        assert result.success is True

    def test_docs_agent_list_in_pipeline(self):
        from gangdan_refined.agents.docs_agent import DocsAgent
        pipeline = Pipeline(DocsAgent())
        result = pipeline.run(AgentInput(options={"action": "list"}))
        assert result.success is True
        assert "sources" in result.data

    def test_config_then_kb_pipeline(self):
        from gangdan_refined.agents.config_agent import ConfigAgent
        from gangdan_refined.agents.kb_agent import KBAgent
        pipeline = Pipeline(ConfigAgent(), KBAgent())
        result = pipeline.run(AgentInput(options={"action": "show"}))
        assert result.success is True

    def test_pipeline_repr(self):
        pipeline = Pipeline(DoubleAgent(), AppendAgent())
        r = repr(pipeline)
        assert "gd-double" in r
        assert "gd-append" in r
        assert "→" in r