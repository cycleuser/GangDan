"""GangDan Agent Pipeline System.

Each agent is an independent, composable unit that communicates via JSON.
Agents can be chained through Unix pipes for complex workflows.

Usage:
    # Single agent
    gd-search "quantum computing" --json

    # Pipeline composition
    gd-search "transformer" --json | gd-summarize --stdin --json

    # Python API
    from gangdan_refined.agents import SearchAgent, SummarizeAgent
    result = SearchAgent().run(AgentInput(query="transformer"))
    summary = SummarizeAgent().run(AgentInput(text=result.data["summary"]))
"""

from .base import BaseAgent, AgentInput, AgentOutput, AgentMetadata
from .protocol import (
    AGENT_PROTOCOL_VERSION,
    validate_input,
    validate_output,
    encode_output,
    decode_input,
    pipe_agents,
)
from .pipeline import Pipeline, PipelineResult

AGENT_REGISTRY = {}


def _register_all():
    from .config_agent import ConfigAgent
    from .models_agent import ModelsAgent
    from .chat_agent import ChatAgent
    from .search_agent import SearchAgent
    from .summarize_agent import SummarizeAgent
    from .translate_agent import TranslateAgent
    from .embed_agent import EmbedAgent
    from .ask_agent import AskAgent
    from .kb_agent import KBAgent
    from .docs_agent import DocsAgent
    from .convert_agent import ConvertAgent
    from .research_agent import ResearchAgent
    from .learn_agent import LearnAgent
    from .preprint_agent import PreprintAgent

    agents = [
        ConfigAgent, ModelsAgent, ChatAgent, SearchAgent, SummarizeAgent,
        TranslateAgent, EmbedAgent, AskAgent, KBAgent, DocsAgent,
        ConvertAgent, ResearchAgent, LearnAgent, PreprintAgent,
    ]
    for agent_cls in agents:
        instance = agent_cls()
        AGENT_REGISTRY[instance.name] = instance


def get_agent(name: str) -> BaseAgent:
    if not AGENT_REGISTRY:
        _register_all()
    if name in AGENT_REGISTRY:
        return AGENT_REGISTRY[name]
    prefixed = f"gd-{name}" if not name.startswith("gd-") else name
    if prefixed in AGENT_REGISTRY:
        return AGENT_REGISTRY[prefixed]
    raise KeyError(f"Agent '{name}' not found. Available: {list(AGENT_REGISTRY.keys())}")


def list_agents():
    if not AGENT_REGISTRY:
        _register_all()
    return list(AGENT_REGISTRY.keys())


__all__ = [
    "BaseAgent",
    "AgentInput",
    "AgentOutput",
    "AgentMetadata",
    "AGENT_PROTOCOL_VERSION",
    "validate_input",
    "validate_output",
    "encode_output",
    "decode_input",
    "pipe_agents",
    "Pipeline",
    "PipelineResult",
    "AGENT_REGISTRY",
    "get_agent",
    "list_agents",
]