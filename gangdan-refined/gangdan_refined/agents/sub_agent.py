"""Recursive sub-agent execution for GangDan Refined.

Inspired by rlm-minimal's RLM_REPL recursive pattern and nanobot's subagent system.
Sub-agents receive an isolated task description and context, optionally can spawn
child sub-agents up to a configurable depth limit.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_DEPTH = 2  # prevent infinite recursion
MAX_ITERATIONS = 5


@dataclass
class SubAgentResult:
    """Result from a sub-agent execution."""
    task: str
    answer: str = ""
    sources: List[str] = field(default_factory=list)
    confidence: float = 0.5
    iterations: int = 0
    error: str = ""
    success: bool = True
    duration_seconds: float = 0.0


class SubAgent:
    """An isolated sub-agent that can research a single task independently.

    Each sub-agent gets a focused task description, optional context from
    knowledge bases, and can optionally spawn child sub-agents for sub-tasks.

    Attributes
    ----------
    name : str
        Agent identifier.
    depth : int
        Current recursion depth (0 = root agent).
    max_depth : int
        Maximum allowed depth for child sub-agents.
    config : Config
        Application configuration.
    ollama : OllamaClient
        LLM client instance.
    chroma : ChromaManager
        Vector DB for knowledge retrieval.
    """

    def __init__(
        self,
        name: str = "sub-agent",
        depth: int = 0,
        config: Any = None,
        ollama: Any = None,
        chroma: Any = None,
    ) -> None:
        self.name = name
        self.depth = depth
        self.config = config
        self.ollama = ollama
        self.chroma = chroma

    def execute(
        self,
        task: str,
        context: str = "",
        kb_names: Optional[List[str]] = None,
        max_iterations: int = MAX_ITERATIONS,
        spawn_children: bool = True,
    ) -> SubAgentResult:
        """Execute a research task.

        Parameters
        ----------
        task : str
            The specific task/question to answer.
        context : str
            Optional background context.
        kb_names : List[str] or None
            Knowledge base names to search.
        max_iterations : int
            Maximum analysis iterations.
        spawn_children : bool
            Whether to allow spawning child sub-agents.

        Returns
        -------
        SubAgentResult
            Completed result with answer, sources, confidence.
        """
        t0 = time.time()
        try:
            result = self._run(task, context, kb_names or [], max_iterations, spawn_children)
            result.duration_seconds = round(time.time() - t0, 2)
            return result
        except Exception as e:
            logger.error("SubAgent '%s' failed: %s", self.name, e)
            return SubAgentResult(
                task=task, success=False, error=str(e),
                duration_seconds=round(time.time() - t0, 2),
            )

    def _run(
        self,
        task: str,
        context: str,
        kb_names: List[str],
        max_iterations: int,
        spawn_children: bool,
    ) -> SubAgentResult:
        """Core execution loop with optional child sub-agent spawning."""
        if not self.ollama or not self.config:
            return SubAgentResult(task=task, success=False, error="No LLM client configured")

        # Retrieve relevant context from KBs
        kb_context = ""
        sources = []
        if kb_names and self.chroma and hasattr(self.ollama, 'embed'):
            try:
                from gangdan_refined.learning.rag_helper import retrieve_context
                q_emb = self.ollama.embed(task, self.config.embedding_model)
                ctx_text, src_list = retrieve_context(
                    task, kb_names, self.ollama, self.chroma, self.config,
                    max_chars=2500, top_k=5,
                )
                kb_context = ctx_text
                sources = src_list
            except Exception as e:
                logger.debug("SubAgent RAG: %s", e)

        # Initial analysis
        answer = self._analyze(task, context + "\n" + kb_context)

        # Check if task can be decomposed into sub-tasks
        if spawn_children and self.depth < MAX_DEPTH:
            children = self._decompose_tasks(task, answer)
            if children:
                child_results = []
                for child_task in children[:3]:  # limit parallelism
                    child = SubAgent(
                        name=f"{self.name}.child",
                        depth=self.depth + 1,
                        config=self.config,
                        ollama=self.ollama,
                        chroma=self.chroma,
                    )
                    cr = child.execute(child_task, context + "\n" + answer, kb_names,
                                       max_iterations=2, spawn_children=False)
                    child_results.append(cr)

                # Synthesize child answers
                if child_results:
                    child_synthesis = "\n".join(
                        f"Sub-task: {cr.task}\nAnswer: {cr.answer}"
                        for cr in child_results if cr.success
                    )
                    answer = self._synthesize(task, answer, child_synthesis)
                    sources = list(set(sources + [
                        s for cr in child_results for s in cr.sources
                    ]))

        return SubAgentResult(
            task=task, answer=answer, sources=sources,
            confidence=0.7, iterations=1, success=True,
        )

    def _analyze(self, task: str, context: str) -> str:
        """Single-pass analysis call."""
        prompt = (
            "You are a research sub-agent. Answer the following task concisely "
            "using the provided context. Be factual, cite sources when possible.\n\n"
            f"Task: {task}\n\nContext:\n{context[:3000]}\n\nAnswer:"
        )
        try:
            msgs = [{"role": "user", "content": prompt}]
            resp = self.ollama.chat_complete(
                msgs, self.config.chat_model, temperature=0.3,
            )
            return resp.strip() if resp else "No answer produced."
        except Exception as e:
            return f"Analysis failed: {e}"

    def _decompose_tasks(self, task: str, preliminary: str) -> List[str]:
        """Use LLM to decompose a task into sub-tasks."""
        prompt = (
            "Break the following research task into 2-3 independent sub-tasks "
            "that can be researched separately. Each sub-task should be a single clear question.\n\n"
            f"Task: {task}\nPreliminary findings: {preliminary[:500]}\n\n"
            "Return ONLY a JSON array of strings: [\"sub-task 1\", \"sub-task 2\"]"
        )
        try:
            msgs = [{"role": "user", "content": prompt}]
            resp = self.ollama.chat_complete(
                msgs, self.config.chat_model, temperature=0.5,
            )
            match = re.search(r"\[.*\]", resp or "", re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception:
            pass
        return []

    def _synthesize(self, task: str, initial: str, children: str) -> str:
        """Synthesize child sub-agent results with initial analysis."""
        prompt = (
            "Synthesize the following into a coherent answer for the original task.\n\n"
            f"Original task: {task}\n\n"
            f"Initial analysis: {initial[:800]}\n\n"
            f"Sub-task results:\n{children[:2000]}\n\n"
            "Synthesized answer:"
        )
        try:
            msgs = [{"role": "user", "content": prompt}]
            resp = self.ollama.chat_complete(
                msgs, self.config.chat_model, temperature=0.4,
            )
            return resp.strip() if resp else initial
        except Exception:
            return initial


def run_multi_agent(
    topic: str,
    kb_names: List[str],
    ollama: Any,
    chroma: Any,
    config: Any,
) -> Dict[str, Any]:
    """Run multi-agent analysis on a topic.

    Parameters
    ----------
    topic : str
        Main research topic.
    kb_names : List[str]
        Knowledge bases to search.
    ollama : OllamaClient
        LLM client.
    chroma : ChromaManager
        Vector DB.
    config : Config
        App configuration.

    Returns
    -------
    dict
        With keys: topic, main_answer, sub_results, sources.
    """
    # Decompose topic
    root = SubAgent(name="root", depth=0, config=config, ollama=ollama, chroma=chroma)
    sub_tasks = root._decompose_tasks(topic, "")

    if not sub_tasks:
        # Single-agent fallback
        result = root.execute(topic, kb_names=kb_names, spawn_children=False)
        return {
            "topic": topic,
            "main_answer": result.answer,
            "sub_results": [],
            "sources": result.sources,
        }

    # Run sub-agents in sequence
    results = []
    all_sources = []
    for task in sub_tasks[:4]:
        agent = SubAgent(name=f"agent-{len(results)}", depth=1, config=config, ollama=ollama, chroma=chroma)
        r = agent.execute(task, kb_names=kb_names, spawn_children=False)
        results.append({"task": r.task, "answer": r.answer, "confidence": r.confidence, "sources": r.sources})
        all_sources.extend(r.sources)

    # Synthesize
    synthesis = root._synthesize(
        topic, "",
        "\n".join(f"Q: {r['task']}\nA: {r['answer']}" for r in results),
    )

    return {
        "topic": topic,
        "main_answer": synthesis,
        "sub_results": results,
        "sources": list(set(all_sources)),
    }
