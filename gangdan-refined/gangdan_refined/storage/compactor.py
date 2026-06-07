"""Context compaction for GangDan Refined.

When a conversation exceeds 80% of the model's context window, this module
compresses older messages into a structured summary, preserving key facts
while freeing token budget.

Inspired by DeepSeek-Reasonix's compaction system and nanobot's autocompact.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

# Compaction triggers (fraction of context window)
SOFT_WARN_RATIO = 0.5   # start showing token usage indicator
COMPACT_RATIO = 0.8      # trigger compaction at this fraction
FORCE_RATIO = 0.9        # force compaction regardless
TARGET_RATIO = 0.5       # compact down to this fraction
TAIL_TOKENS = 8192       # keep this many tokens of recent messages verbatim
MIN_KEEP_MESSAGES = 3    # never drop the last N messages
FALLBACK_TOK_PER_CHAR = 0.25  # ~4 chars per token fallback estimate

SUMMARY_PROMPT = """You are compacting the earlier part of a conversation to save context.
The agent will keep ONLY your summary (original messages are dropped), so it must be able to resume from it alone.
Write a briefing under these exact headings, omitting a heading only if it has no content:

## Goal
The user's request and intent, kept close to their own words. Include explicit requirements, constraints, and preferences.

## Decisions & rationale
Key choices made so far and why — so they are not re-litigated or reversed.

## Files & code
Files read or modified, with specific facts: signatures, line locations, data shapes, exact edits applied.

## Commands & outcomes
Commands run (builds, tests, git) and their relevant results — what passed, what failed, error text that matters.

## Current state
Where things stand right now — what works, what doesn't, what is blocked.

## Next steps
The immediate next action to take. Be concrete."""


def estimate_tokens(text: str) -> int:
    """Rough token count estimate."""
    if not text:
        return 0
    return int(len(text) * FALLBACK_TOK_PER_CHAR)


def compact_conversation(
    messages: List[dict],
    context_limit: int,
    ollama_client: Any,
    model: str = "",
) -> List[dict]:
    """Compact older messages into a structured summary.

    Parameters
    ----------
    messages : List[dict]
        List of {"role": "...", "content": "..."} dicts.
    context_limit : int
        Model's context window in tokens.
    ollama_client : OllamaClient
        LLM client for generating the compaction summary.
    model : str
        Model name override.

    Returns
    -------
    List[dict]
        Compressed message list with summary injected.
    """
    if not messages:
        return messages

    total_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)
    compact_trigger = int(context_limit * COMPACT_RATIO)

    if total_tokens <= compact_trigger:
        return messages

    # Find split point: keep recent TAIL_TOKENS tokens verbatim
    tail_tokens = 0
    split_idx = len(messages)
    for i in range(len(messages) - 1, -1, -1):
        msg_tokens = estimate_tokens(messages[i].get("content", ""))
        if tail_tokens + msg_tokens > TAIL_TOKENS and i < len(messages) - MIN_KEEP_MESSAGES:
            break
        tail_tokens += msg_tokens
        split_idx = i

    if split_idx <= 0:
        return messages

    # Messages to compact: [0, split_idx)
    old_messages = messages[:split_idx]
    recent_messages = messages[split_idx:]

    # Build conversation text for LLM to summarize
    conv_text = ""
    for m in old_messages:
        role = m.get("role", "unknown")
        content = m.get("content", "")[:1200]  # truncate very long messages
        conv_text += f"**[{role}]**: {content}\n\n"

    # Generate compaction summary via LLM
    summary = _generate_summary(conv_text[:6000], ollama_client, model)

    # Build compacted message list
    compacted = [
        {
            "role": "system",
            "content": f"<compaction-summary>\n{summary}\n</compaction-summary>\n\n"
                       f"The above is a summary of the earlier conversation. Continue helping the user.",
        }
    ]
    compacted.extend(recent_messages)

    new_total = sum(estimate_tokens(m.get("content", "")) for m in compacted)
    logger.info(
        "Compactor: %d messages → %d messages, %d → %d tokens",
        len(messages), len(compacted), total_tokens, new_total,
    )

    return compacted


def _generate_summary(conversation_text: str, client: Any, model: str = "") -> str:
    """Ask the LLM to summarize older conversation."""
    try:
        prompt = f"{SUMMARY_PROMPT}\n\nConversation to summarize:\n\n{conversation_text}\n\nBriefing:"
        msgs = [{"role": "user", "content": prompt}]
        model_name = model or getattr(client, '_model', "qwen2.5:7b")
        resp = client.chat_complete(msgs, model_name, temperature=0.2)
        if resp and len(resp.strip()) > 20:
            return resp.strip()
    except Exception as e:
        logger.warning("Compactor: LLM call failed: %s", e)

    # Fallback: simple truncation-based summary
    lines = conversation_text.split("\n")
    key_lines = [l for l in lines if l.strip() and not l.strip().startswith("**[system]")]
    return "Earlier conversation — key points:\n" + "\n".join(key_lines[:15]) + "\n...(truncated)"


def should_compact(messages: List[dict], context_limit: int) -> bool:
    """Check if conversation should be compacted."""
    total = sum(estimate_tokens(m.get("content", "")) for m in messages)
    return total >= int(context_limit * COMPACT_RATIO)


def token_usage_level(messages: List[dict], context_limit: int) -> str:
    """Get token usage level for UI indicator.

    Returns
    -------
    str
        "low", "warn", or "critical".
    """
    total = sum(estimate_tokens(m.get("content", "")) for m in messages)
    ratio = total / max(context_limit, 1)
    if ratio >= FORCE_RATIO:
        return "critical"
    if ratio >= SOFT_WARN_RATIO:
        return "warn"
    return "low"
