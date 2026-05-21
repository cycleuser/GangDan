"""Pipeline composition engine for chaining multiple agents.

Usage:
    # Python API
    pipeline = Pipeline(SearchAgent, SummarizeAgent, TranslateAgent)
    result = pipeline.run(AgentInput(query="quantum computing"))
    print(result.data["translation"])

    # CLI (via gd-pipeline command)
    gd-search "query" --json | gd-summarize --stdin --json | gd-translate --stdin --to zh --json
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type

from .base import BaseAgent
from .protocol import AgentInput, AgentOutput, AgentMetadata, AGENT_PROTOCOL_VERSION


@dataclass
class PipelineStep:
    agent: BaseAgent
    name: str = ""
    duration_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None


@dataclass
class PipelineResult:
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    steps: List[PipelineStep] = field(default_factory=list)
    pipeline_id: str = ""
    total_duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "pipeline_id": self.pipeline_id,
            "steps": [
                {"name": s.name, "duration_ms": s.duration_ms, "success": s.success, "error": s.error}
                for s in self.steps
            ],
            "total_duration_ms": self.total_duration_ms,
            "protocol_version": AGENT_PROTOCOL_VERSION,
        }

    def to_json(self, indent: Optional[int] = None) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent or 2)


class Pipeline:
    """Chain multiple agents into a pipeline.

    Each agent's output.data becomes the next agent's input.
    The pipeline tracks timing, errors, and intermediate results.
    """

    def __init__(self, *agent_classes_or_instances: Any):
        self.steps: List[BaseAgent] = []
        for item in agent_classes_or_instances:
            if isinstance(item, type) and issubclass(item, BaseAgent):
                self.steps.append(item())
            elif isinstance(item, BaseAgent):
                self.steps.append(item)
            else:
                raise TypeError(f"Expected BaseAgent class or instance, got {type(item)}")

    def run(self, input: AgentInput, pipeline_id: Optional[str] = None) -> PipelineResult:
        import time

        pid = pipeline_id or f"pipe_{int(time.time() * 1000)}"
        all_steps: List[PipelineStep] = []
        current_data = input.data.copy() if input.data else {}
        current_text = input.text or input.query or ""
        total_start = time.time()
        overall_success = True
        last_error = None

        for i, agent in enumerate(self.steps):
            step_name = agent.name
            step_start = time.time()

            try:
                step_input = AgentInput(
                    query=input.query if i == 0 else None,
                    text=current_text,
                    data=current_data,
                    options=input.options,
                    metadata=AgentMetadata(
                        agent=agent.name,
                        version=agent.version,
                        pipeline_id=pid,
                    ),
                )

                result = agent.run(step_input)

                step_duration = (time.time() - step_start) * 1000
                all_steps.append(PipelineStep(
                    agent=agent,
                    name=step_name,
                    duration_ms=round(step_duration, 1),
                    success=result.success,
                    error=result.error if not result.success else None,
                ))

                if result.success:
                    current_data.update(result.data)
                    text_keys = ["response", "summary", "translation", "answer", "markdown", "text", "content"]
                    for key in text_keys:
                        if key in result.data:
                            current_text = result.data[key]
                            break
                else:
                    overall_success = False
                    last_error = result.error
                    break

            except Exception as e:
                step_duration = (time.time() - step_start) * 1000
                all_steps.append(PipelineStep(
                    agent=agent,
                    name=step_name,
                    duration_ms=round(step_duration, 1),
                    success=False,
                    error=str(e),
                ))
                overall_success = False
                last_error = str(e)
                break

        total_duration = (time.time() - total_start) * 1000

        return PipelineResult(
            success=overall_success,
            data=current_data,
            error=last_error,
            steps=all_steps,
            pipeline_id=pid,
            total_duration_ms=round(total_duration, 1),
            metadata={"protocol_version": AGENT_PROTOCOL_VERSION},
        )

    def __or__(self, other: Any) -> "Pipeline":
        if isinstance(other, type) and issubclass(other, BaseAgent):
            other = other()
        if not isinstance(other, BaseAgent):
            raise TypeError(f"Cannot pipe to {type(other)}")
        new_pipeline = Pipeline()
        new_pipeline.steps = self.steps + [other]
        return new_pipeline

    def __repr__(self) -> str:
        names = " → ".join(s.name for s in self.steps)
        return f"Pipeline({names})"