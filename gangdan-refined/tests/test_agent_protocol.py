"""White-box unit tests for agent protocol layer.

Tests cover: AgentMetadata, AgentInput, AgentOutput, encode/decode,
validation, stdin handling, and all edge cases.
"""

import json
import io
import sys
from unittest.mock import patch

import pytest

from gangdan_refined.agents.protocol import (
    AGENT_PROTOCOL_VERSION,
    AgentMetadata,
    AgentInput,
    AgentOutput,
    validate_input,
    validate_output,
    encode_output,
    decode_input,
    pipe_agents,
)


class TestAgentMetadata:
    def test_creation_defaults(self):
        m = AgentMetadata(agent="test")
        assert m.agent == "test"
        assert m.version == "2.0.0"
        assert m.timestamp != ""
        assert m.pipeline_id is None

    def test_creation_full(self):
        m = AgentMetadata(agent="gd-search", version="3.0.0", timestamp="2026-01-01", pipeline_id="p1")
        assert m.agent == "gd-search"
        assert m.version == "3.0.0"
        assert m.timestamp == "2026-01-01"
        assert m.pipeline_id == "p1"

    def test_to_dict_includes_all_fields(self):
        m = AgentMetadata(agent="test", pipeline_id="p1")
        d = m.to_dict()
        assert d["agent"] == "test"
        assert d["pipeline_id"] == "p1"
        assert "version" in d
        assert "timestamp" in d

    def test_to_dict_omits_none_pipeline_id(self):
        m = AgentMetadata(agent="test")
        d = m.to_dict()
        assert "pipeline_id" not in d

    def test_to_dict_omits_none_values(self):
        m = AgentMetadata(agent="test", pipeline_id=None)
        d = m.to_dict()
        assert "pipeline_id" not in d

    def test_from_dict_minimal(self):
        d = {"agent": "test"}
        m = AgentMetadata.from_dict(d)
        assert m.agent == "test"
        assert m.version == "2.0.0"

    def test_from_dict_full(self):
        d = {"agent": "gd-search", "version": "3.0.0", "timestamp": "2026-01-01", "pipeline_id": "p1"}
        m = AgentMetadata.from_dict(d)
        assert m.agent == "gd-search"
        assert m.version == "3.0.0"
        assert m.pipeline_id == "p1"

    def test_from_dict_empty(self):
        m = AgentMetadata.from_dict({})
        assert m.agent == ""
        assert m.version == "2.0.0"

    def test_auto_timestamp(self):
        m1 = AgentMetadata(agent="a")
        m2 = AgentMetadata(agent="b")
        assert m1.timestamp != ""
        assert m2.timestamp != ""

    def test_roundtrip(self):
        m = AgentMetadata(agent="gd-ask", version="2.1.0", pipeline_id="pipe_42")
        d = m.to_dict()
        m2 = AgentMetadata.from_dict(d)
        assert m2.agent == m.agent
        assert m2.version == m.version
        assert m2.pipeline_id == m.pipeline_id


class TestAgentInput:
    def test_default_creation(self):
        inp = AgentInput()
        assert inp.query is None
        assert inp.text is None
        assert inp.file_path is None
        assert inp.data == {}
        assert inp.options == {}
        assert inp.metadata is None

    def test_creation_with_query(self):
        inp = AgentInput(query="quantum computing")
        assert inp.query == "quantum computing"

    def test_creation_with_text(self):
        inp = AgentInput(text="Long text content")
        assert inp.text == "Long text content"

    def test_creation_with_file_path(self):
        inp = AgentInput(file_path="/path/to/file.pdf")
        assert inp.file_path == "/path/to/file.pdf"

    def test_creation_with_options(self):
        inp = AgentInput(options={"model": "qwen3:7b", "language": "zh"})
        assert inp.options["model"] == "qwen3:7b"
        assert inp.options["language"] == "zh"

    def test_creation_with_metadata(self):
        meta = AgentMetadata(agent="test", pipeline_id="p1")
        inp = AgentInput(query="q", metadata=meta)
        assert inp.metadata.agent == "test"
        assert inp.metadata.pipeline_id == "p1"

    def test_creation_with_data(self):
        inp = AgentInput(data={"key": "value", "nested": {"a": 1}})
        assert inp.data["key"] == "value"
        assert inp.data["nested"]["a"] == 1

    def test_to_dict_with_query(self):
        inp = AgentInput(query="test query", options={"model": "qwen"})
        d = inp.to_dict()
        assert d["query"] == "test query"
        assert d["options"]["model"] == "qwen"
        assert "text" not in d
        assert "file_path" not in d

    def test_to_dict_with_text(self):
        inp = AgentInput(text="some text")
        d = inp.to_dict()
        assert d["text"] == "some text"
        assert "query" not in d

    def test_to_dict_with_all_fields(self):
        meta = AgentMetadata(agent="gd-ask")
        inp = AgentInput(query="q", text="t", file_path="/f", data={"k": "v"}, options={"m": "x"}, metadata=meta)
        d = inp.to_dict()
        assert d["query"] == "q"
        assert d["text"] == "t"
        assert d["file_path"] == "/f"
        assert d["data"]["k"] == "v"
        assert d["options"]["m"] == "x"
        assert d["metadata"]["agent"] == "gd-ask"

    def test_to_dict_empty(self):
        inp = AgentInput()
        d = inp.to_dict()
        assert d == {}

    def test_from_dict_minimal(self):
        d = {"query": "test"}
        inp = AgentInput.from_dict(d)
        assert inp.query == "test"

    def test_from_dict_full(self):
        d = {
            "query": "q",
            "text": "t",
            "file_path": "/f",
            "data": {"key": "val"},
            "options": {"model": "qwen"},
            "metadata": {"agent": "gd-ask", "version": "2.0.0", "timestamp": "2026-01-01"},
        }
        inp = AgentInput.from_dict(d)
        assert inp.query == "q"
        assert inp.text == "t"
        assert inp.file_path == "/f"
        assert inp.data["key"] == "val"
        assert inp.options["model"] == "qwen"
        assert inp.metadata.agent == "gd-ask"

    def test_from_dict_empty(self):
        inp = AgentInput.from_dict({})
        assert inp.query is None
        assert inp.text is None
        assert inp.data == {}
        assert inp.options == {}

    def test_roundtrip(self):
        inp = AgentInput(query="hello", text="world", options={"lang": "en"}, data={"x": 1})
        d = inp.to_dict()
        inp2 = AgentInput.from_dict(d)
        assert inp2.query == inp.query
        assert inp2.text == inp.text
        assert inp2.options == inp.options
        assert inp2.data == inp.data


class TestAgentOutput:
    def test_success_output(self):
        out = AgentOutput(success=True, data={"key": "val"}, metadata=AgentMetadata(agent="test"))
        assert out.success is True
        assert out.error is None
        assert out.data["key"] == "val"

    def test_error_output(self):
        out = AgentOutput(success=False, error="Something went wrong", metadata=AgentMetadata(agent="test"))
        assert out.success is False
        assert out.error == "Something went wrong"
        assert out.data == {}

    def test_to_dict(self):
        out = AgentOutput(success=True, data={"x": 1}, metadata=AgentMetadata(agent="gd-search"))
        d = out.to_dict()
        assert d["success"] is True
        assert d["data"]["x"] == 1
        assert d["metadata"]["agent"] == "gd-search"
        assert d["protocol_version"] == AGENT_PROTOCOL_VERSION

    def test_to_dict_error(self):
        out = AgentOutput(success=False, error="fail", metadata=AgentMetadata(agent="test"))
        d = out.to_dict()
        assert d["success"] is False
        assert d["error"] == "fail"

    def test_to_json(self):
        out = AgentOutput(success=True, data={"result": "hello"}, metadata=AgentMetadata(agent="test"))
        j = out.to_json()
        parsed = json.loads(j)
        assert parsed["success"] is True
        assert parsed["data"]["result"] == "hello"

    def test_to_json_indent(self):
        out = AgentOutput(success=True, data={"x": 1}, metadata=AgentMetadata(agent="test"))
        j = out.to_json(indent=4)
        assert "\n" in j
        parsed = json.loads(j)
        assert parsed["success"] is True

    def test_from_dict(self):
        d = {"success": True, "data": {"x": 1}, "error": None, "metadata": {"agent": "test", "version": "2.0.0", "timestamp": "2026"}}
        out = AgentOutput.from_dict(d)
        assert out.success is True
        assert out.data["x"] == 1
        assert out.error is None

    def test_from_dict_error(self):
        d = {"success": False, "data": {}, "error": "broken", "metadata": {"agent": "test", "version": "2.0.0", "timestamp": ""}}
        out = AgentOutput.from_dict(d)
        assert out.success is False
        assert out.error == "broken"

    def test_from_json(self):
        j = '{"success": true, "data": {"x": 1}, "error": null, "metadata": {"agent": "test", "version": "2.0.0", "timestamp": ""}}'
        out = AgentOutput.from_json(j)
        assert out.success is True
        assert out.data["x"] == 1

    def test_from_json_with_special_chars(self):
        j = '{"success": true, "data": {"text": "Hello \\u4e16\\u754c"}, "error": null, "metadata": {"agent": "test", "version": "2.0.0", "timestamp": ""}}'
        out = AgentOutput.from_json(j)
        assert out.data["text"] == "Hello 世界"

    def test_roundtrip(self):
        out = AgentOutput(success=True, data={"key": "val", "items": [1, 2, 3]}, metadata=AgentMetadata(agent="gd-ask", pipeline_id="p1"))
        j = out.to_json()
        out2 = AgentOutput.from_json(j)
        assert out2.success == out.success
        assert out2.data["key"] == "val"
        assert out2.data["items"] == [1, 2, 3]
        assert out2.metadata.agent == "gd-ask"
        assert out2.metadata.pipeline_id == "p1"

    def test_to_stdout_text_response(self):
        out = AgentOutput(success=True, data={"response": "Hello world"}, metadata=AgentMetadata(agent="test"))
        assert out.to_stdout_text() == "Hello world"

    def test_to_stdout_text_summary(self):
        out = AgentOutput(success=True, data={"summary": "Short summary"}, metadata=AgentMetadata(agent="test"))
        assert out.to_stdout_text() == "Short summary"

    def test_to_stdout_text_translation(self):
        out = AgentOutput(success=True, data={"translation": "翻译"}, metadata=AgentMetadata(agent="test"))
        assert out.to_stdout_text() == "翻译"

    def test_to_stdout_text_answer(self):
        out = AgentOutput(success=True, data={"answer": "42"}, metadata=AgentMetadata(agent="test"))
        assert out.to_stdout_text() == "42"

    def test_to_stdout_text_markdown(self):
        out = AgentOutput(success=True, data={"markdown": "# Title\nContent"}, metadata=AgentMetadata(agent="test"))
        assert "# Title" in out.to_stdout_text()

    def test_to_stdout_text_results_list(self):
        out = AgentOutput(success=True, data={"results": [{"title": "Paper A"}, {"title": "Paper B"}]}, metadata=AgentMetadata(agent="test"))
        text = out.to_stdout_text()
        assert "- Paper A" in text
        assert "- Paper B" in text

    def test_to_stdout_text_results_strings(self):
        out = AgentOutput(success=True, data={"results": ["item1", "item2"]}, metadata=AgentMetadata(agent="test"))
        text = out.to_stdout_text()
        assert "- item1" in text

    def test_to_stdout_text_fallback_dict(self):
        out = AgentOutput(success=True, data={"custom_key": "custom_val"}, metadata=AgentMetadata(agent="test"))
        text = out.to_stdout_text()
        assert "custom_key" in text

    def test_to_stdout_text_error(self):
        out = AgentOutput(success=False, error="Something broke", metadata=AgentMetadata(agent="test"))
        assert "Error: Something broke" in out.to_stdout_text()


class TestValidateInput:
    def test_validate_input_dict(self):
        inp = validate_input({"query": "test", "options": {"model": "qwen"}})
        assert isinstance(inp, AgentInput)
        assert inp.query == "test"
        assert inp.options["model"] == "qwen"

    def test_validate_input_agent_input(self):
        original = AgentInput(query="test")
        result = validate_input(original)
        assert result is original

    def test_validate_input_json_string(self):
        inp = validate_input('{"query": "test"}')
        assert isinstance(inp, AgentInput)
        assert inp.query == "test"


class TestValidateOutput:
    def test_validate_output_dict(self):
        out = validate_output({"success": True, "data": {"x": 1}, "metadata": {"agent": "test", "version": "2.0.0", "timestamp": ""}})
        assert isinstance(out, AgentOutput)
        assert out.success is True

    def test_validate_output_agent_output(self):
        original = AgentOutput(success=True, data={}, metadata=AgentMetadata(agent="test"))
        result = validate_output(original)
        assert result is original

    def test_validate_output_json_string(self):
        out = validate_output('{"success": true, "data": {"x": 1}, "metadata": {"agent": "test", "version": "2.0.0", "timestamp": ""}}')
        assert isinstance(out, AgentOutput)
        assert out.success is True


class TestEncodeOutput:
    def test_encode_json_mode(self):
        out = AgentOutput(success=True, data={"x": 1}, metadata=AgentMetadata(agent="test"))
        text = encode_output(out, json_mode=True)
        parsed = json.loads(text)
        assert parsed["success"] is True

    def test_encode_text_mode(self):
        out = AgentOutput(success=True, data={"response": "hello"}, metadata=AgentMetadata(agent="test"))
        text = encode_output(out, json_mode=False)
        assert "hello" in text

    def test_encode_json_no_indent(self):
        out = AgentOutput(success=True, data={"x": 1}, metadata=AgentMetadata(agent="test"))
        text = encode_output(out, json_mode=True, indent=0)
        parsed = json.loads(text)
        assert parsed["success"] is True


class TestDecodeInput:
    def test_decode_stdin_piped_agent_output(self):
        agent_json = json.dumps({
            "success": True,
            "data": {"query": "quantum", "summary": "Short summary"},
            "metadata": {"agent": "gd-search", "version": "2.0.0", "timestamp": "2026"},
            "protocol_version": "2.0",
        })
        with patch("sys.stdin", io.StringIO(agent_json)):
            with patch("sys.stdin.isatty", return_value=False):
                result = decode_input(use_stdin=True)
                assert result is not None
                assert result.data["query"] == "quantum"
                assert result.text == "Short summary" or result.query == "quantum"

    def test_decode_stdin_plain_text(self):
        with patch("sys.stdin", io.StringIO("plain text input")):
            with patch("sys.stdin.isatty", return_value=False):
                result = decode_input(use_stdin=True)
                assert result is not None
                assert result.text == "plain text input"

    def test_decode_stdin_tty(self):
        with patch("sys.stdin.isatty", return_value=True):
            result = decode_input(use_stdin=True)
            assert result is None

    def test_decode_raw_json(self):
        result = decode_input(raw_json='{"query": "test"}')
        assert result is not None
        assert result.query == "test"

    def test_decode_raw_json_invalid(self):
        result = decode_input(raw_json="not json")
        assert result is not None
        assert result.text == "not json"

    def test_decode_no_input(self):
        result = decode_input(use_stdin=False, raw_json=None)
        assert result is None

    def test_decode_stdin_empty(self):
        with patch("sys.stdin", io.StringIO("")):
            with patch("sys.stdin.isatty", return_value=False):
                result = decode_input(use_stdin=True)
                assert result is None


class TestPipeAgents:
    def test_pipe_agents_creates_pipeline(self):
        from gangdan_refined.agents.base import BaseAgent
        from gangdan_refined.agents import get_agent
        cfg_cls = type(get_agent("gd-config"))
        p = pipe_agents(cfg_cls, cfg_cls)
        from gangdan_refined.agents.pipeline import Pipeline
        assert isinstance(p, Pipeline)
        assert len(p.steps) == 2


class TestAgentProtocolVersion:
    def test_protocol_version_format(self):
        assert AGENT_PROTOCOL_VERSION.count(".") == 1
        major, minor = AGENT_PROTOCOL_VERSION.split(".")
        assert major.isdigit()
        assert minor.isdigit()

    def test_protocol_version_in_output(self):
        out = AgentOutput(success=True, data={}, metadata=AgentMetadata(agent="test"))
        d = out.to_dict()
        assert d["protocol_version"] == AGENT_PROTOCOL_VERSION