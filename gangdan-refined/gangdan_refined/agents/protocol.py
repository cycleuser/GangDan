"""Agent protocol definitions for JSON communication.

Every agent produces and consumes JSON following this protocol.
The protocol version allows backward-compatible evolution.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

AGENT_PROTOCOL_VERSION = "2.0"


@dataclass
class AgentMetadata:
    agent: str
    version: str = "2.0.0"
    timestamp: str = ""
    pipeline_id: Optional[str] = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AgentMetadata":
        return cls(
            agent=d.get("agent", ""),
            version=d.get("version", "2.0.0"),
            timestamp=d.get("timestamp", ""),
            pipeline_id=d.get("pipeline_id"),
        )


@dataclass
class AgentInput:
    query: Optional[str] = None
    text: Optional[str] = None
    file_path: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    options: Dict[str, Any] = field(default_factory=dict)
    metadata: Optional[AgentMetadata] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {}
        if self.query is not None:
            result["query"] = self.query
        if self.text is not None:
            result["text"] = self.text
        if self.file_path is not None:
            result["file_path"] = self.file_path
        if self.data:
            result["data"] = self.data
        if self.options:
            result["options"] = self.options
        if self.metadata is not None:
            result["metadata"] = self.metadata.to_dict()
        return result

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AgentInput":
        meta = None
        if "metadata" in d and d["metadata"]:
            meta = AgentMetadata.from_dict(d["metadata"])
        return cls(
            query=d.get("query"),
            text=d.get("text"),
            file_path=d.get("file_path"),
            data=d.get("data", {}),
            options=d.get("options", {}),
            metadata=meta,
        )


@dataclass
class AgentOutput:
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    metadata: AgentMetadata = field(default_factory=lambda: AgentMetadata(agent="unknown"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata.to_dict(),
            "protocol_version": AGENT_PROTOCOL_VERSION,
        }

    def to_json(self, indent: Optional[int] = None) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AgentOutput":
        meta = AgentMetadata.from_dict(d.get("metadata", {}))
        return cls(
            success=d.get("success", False),
            data=d.get("data", {}),
            error=d.get("error"),
            metadata=meta,
        )

    @classmethod
    def from_json(cls, json_str: str) -> "AgentOutput":
        return cls.from_dict(json.loads(json_str))

    def to_stdout_text(self) -> str:
        if not self.success:
            return f"Error: {self.error}"
        if "response" in self.data:
            return self.data["response"]
        if "summary" in self.data:
            return self.data["summary"]
        if "translation" in self.data:
            return self.data["translation"]
        if "answer" in self.data:
            return self.data["answer"]
        if "markdown" in self.data:
            return self.data["markdown"]
        if "results" in self.data:
            results = self.data["results"]
            if isinstance(results, list):
                lines = []
                for r in results:
                    if isinstance(r, dict):
                        lines.append(f"- {r.get('title', r.get('name', str(r)))}")
                    else:
                        lines.append(f"- {r}")
                return "\n".join(lines)
        return json.dumps(self.data, ensure_ascii=False, indent=2)


def validate_input(data: Dict[str, Any]) -> AgentInput:
    if isinstance(data, AgentInput):
        return data
    if isinstance(data, str):
        data = json.loads(data)
    return AgentInput.from_dict(data)


def validate_output(data: Dict[str, Any]) -> AgentOutput:
    if isinstance(data, AgentOutput):
        return data
    if isinstance(data, str):
        data = json.loads(data)
    return AgentOutput.from_dict(data)


def encode_output(output: AgentOutput, json_mode: bool = True, indent: Optional[int] = None) -> str:
    if json_mode:
        return output.to_json(indent=indent or 2)
    return output.to_stdout_text()


def decode_input(use_stdin: bool = False, raw_json: Optional[str] = None) -> Optional[AgentInput]:
    if use_stdin and not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
        if raw:
            try:
                d = json.loads(raw)
                if "success" in d and "data" in d:
                    return AgentInput(
                        data=d.get("data", {}),
                        metadata=AgentMetadata.from_dict(d.get("metadata", {})) if d.get("metadata") else None,
                        query=d.get("data", {}).get("query"),
                        text=d.get("data", {}).get("text") or d.get("data", {}).get("summary") or d.get("data", {}).get("response") or d.get("data", {}).get("answer"),
                    )
                else:
                    return AgentInput.from_dict(d)
            except json.JSONDecodeError:
                return AgentInput(text=raw)
        return None
    if raw_json:
        try:
            d = json.loads(raw_json)
            return AgentInput.from_dict(d)
        except json.JSONDecodeError:
            return AgentInput(text=raw_json)
    return None


def pipe_agents(*agent_classes: type) -> "Pipeline":
    from .pipeline import Pipeline
    return Pipeline(*agent_classes)