"""Shared utilities for the learning module.

Consolidates duplicated logic (JSON parsing) and provides infrastructure
for retry, timeout, validation, and SSE error boundaries.

Design patterns applied:
- autoresearch: iterative retry with quality gates
- symphony: exponential backoff, stall detection
"""

import re
import sys
import json
import time
import functools
from typing import Optional, Union, Iterator, List, Tuple, Callable


# =============================================================================
# JSON Parsing (consolidated from question_gen.py, guided.py, research.py)
# =============================================================================

def parse_json(text: str, label: str = "") -> Optional[dict]:
    """Robust JSON parsing with multiple fallback strategies.

    Merges the best strategies from all 3 previous implementations:
    1. Direct parse
    2. Strip markdown code blocks
    3. Find JSON brace boundaries
    4. Clean control characters and retry
    5. Handle nested/array JSON boundaries

    Args:
        text: Raw LLM output that may contain JSON.
        label: Diagnostic label for logging which caller failed.

    Returns:
        Parsed dict, or None if all strategies fail.
    """
    if not text:
        return None

    # Strategy 1: Direct parse
    try:
        return json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: Strip markdown code blocks
    md_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if md_match:
        try:
            return json.loads(md_match.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 3: Find JSON object boundaries
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(text[first_brace:last_brace + 1])
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 4: Clean control characters and retry
    cleaned = re.sub(r'[\x00-\x1f\x7f]', ' ', text)
    cleaned = cleaned.replace('\n', ' ')
    first_brace = cleaned.find('{')
    last_brace = cleaned.rfind('}')
    if first_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(cleaned[first_brace:last_brace + 1])
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 5: Try to fix common LLM JSON errors (trailing commas, single quotes)
    if first_brace != -1 and last_brace > first_brace:
        candidate = cleaned[first_brace:last_brace + 1]
        # Remove trailing commas before } or ]
        candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            pass

    log_prefix = f"[Utils:{label}]" if label else "[Utils]"
    print(f"{log_prefix} All JSON parse strategies failed for: {text[:200]}...", file=sys.stderr)
    return None


# =============================================================================
# LLM Call with Retry (symphony: exponential backoff, autoresearch: retry loop)
# =============================================================================

def llm_call_with_retry(
    ollama,
    config,
    messages: list,
    temperature: float,
    max_retries: int = 2,
    parse_json_response: bool = True,
    label: str = "",
) -> Union[str, dict, None]:
    """Call LLM with retry on failure, optional JSON parsing per attempt.

    Wraps ollama.chat_complete() with:
    - Exponential backoff between retries (1s, 2s)
    - JSON parse validation on each attempt (if parse_json_response=True)
    - Diagnostic logging per attempt

    Args:
        ollama: OllamaClient instance.
        config: App config with chat_model.
        messages: Chat messages to send.
        temperature: Sampling temperature.
        max_retries: Number of retries after first failure (total attempts = 1 + max_retries).
        parse_json_response: If True, parse response as JSON and retry on parse failure.
        label: Diagnostic label for logging.

    Returns:
        Parsed dict (if parse_json_response), raw string (if not), or None on total failure.
    """
    log_prefix = f"[Utils:{label}]" if label else "[Utils]"
    backoff_delays = [1, 2, 4]  # seconds between retries

    for attempt in range(1 + max_retries):
        try:
            response = ollama.chat_complete(messages, config.chat_model, temperature=temperature)
        except Exception as e:
            print(f"{log_prefix} LLM call error (attempt {attempt + 1}): {e}", file=sys.stderr)
            if attempt < max_retries:
                delay = backoff_delays[min(attempt, len(backoff_delays) - 1)]
                time.sleep(delay)
                continue
            return None

        if not response:
            print(f"{log_prefix} Empty response (attempt {attempt + 1})", file=sys.stderr)
            if attempt < max_retries:
                delay = backoff_delays[min(attempt, len(backoff_delays) - 1)]
                time.sleep(delay)
                continue
            return None

        if not parse_json_response:
            return response

        # Parse JSON
        data = parse_json(response, label=label)
        if data is not None:
            return data

        print(f"{log_prefix} JSON parse failed (attempt {attempt + 1}/{1 + max_retries})", file=sys.stderr)
        if attempt < max_retries:
            delay = backoff_delays[min(attempt, len(backoff_delays) - 1)]
            time.sleep(delay)

    print(f"{log_prefix} All {1 + max_retries} attempts failed", file=sys.stderr)
    return None


# =============================================================================
# LLM Stream with Timeout (symphony: stall detection)
# =============================================================================

def llm_stream_with_timeout(
    ollama,
    config,
    messages: list,
    temperature: float,
    timeout_seconds: int = 120,
    label: str = "",
) -> Iterator[str]:
    """Stream LLM response with stall detection.

    Wraps ollama.chat_stream() and monitors time between chunks.
    If no chunk arrives within timeout_seconds, yields a timeout marker and stops.

    Args:
        ollama: OllamaClient instance.
        config: App config with chat_model.
        messages: Chat messages to send.
        temperature: Sampling temperature.
        timeout_seconds: Max seconds to wait between chunks before declaring stall.
        label: Diagnostic label for logging.

    Yields:
        Text chunks from LLM, or "[Timeout]" if stalled.
    """
    log_prefix = f"[Utils:{label}]" if label else "[Utils]"
    last_chunk_time = time.time()

    try:
        for chunk in ollama.chat_stream(messages, config.chat_model, temperature=temperature):
            now = time.time()
            if now - last_chunk_time > timeout_seconds:
                print(f"{log_prefix} Stream stall detected after {timeout_seconds}s", file=sys.stderr)
                yield "\n\n[Timeout: generation stalled]"
                return
            if ollama.is_stopped():
                yield "\n\n[Stopped]"
                return
            last_chunk_time = now
            yield chunk
    except Exception as e:
        print(f"{log_prefix} Stream error: {e}", file=sys.stderr)
        yield f"\n\n[Error: {str(e)[:100]}]"


# =============================================================================
# Structural Validation
# =============================================================================

def validate_json_structure(data: dict, required_keys: list, label: str = "") -> bool:
    """Check that required keys exist and have non-empty values.

    Args:
        data: Parsed JSON dict to validate.
        required_keys: List of key names that must be present and non-empty.
        label: Diagnostic label for logging.

    Returns:
        True if all required keys exist and are non-empty.
    """
    if not isinstance(data, dict):
        return False
    for key in required_keys:
        val = data.get(key)
        if val is None:
            return False
        if isinstance(val, str) and not val.strip():
            return False
        if isinstance(val, (list, dict)) and len(val) == 0:
            return False
    return True


# =============================================================================
# SSE Error Boundary
# =============================================================================

def safe_sse_generator(gen_func: Callable) -> Callable:
    """Decorator that wraps an SSE generator with error boundary.

    If the wrapped generator raises an unhandled exception, this yields
    a JSON error event instead of letting the stream crash silently.

    Usage:
        @safe_sse_generator
        def my_generator():
            yield f"data: {json.dumps(event)}\\n\\n"
    """
    @functools.wraps(gen_func)
    def wrapper(*args, **kwargs):
        try:
            yield from gen_func(*args, **kwargs)
        except GeneratorExit:
            # Client disconnected, not an error
            return
        except Exception as e:
            print(f"[SSE Error Boundary] Unhandled error in {gen_func.__name__}: {e}", file=sys.stderr)
            error_event = {"type": "error", "message": f"Internal error: {str(e)[:200]}"}
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
    return wrapper


# =============================================================================
# Text Similarity (used for diversity checking, section-notes matching)
# =============================================================================

def jaccard_word_similarity(text_a: str, text_b: str) -> float:
    """Compute Jaccard similarity between two texts based on word tokens.

    Returns a value between 0.0 (completely different) and 1.0 (identical).
    """
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


# =============================================================================
# Quality Gate Validators (Phase 2)
# =============================================================================

def validate_question(data: dict, question_type: str) -> Tuple[bool, str]:
    """Validate a generated question meets structural and content thresholds.

    Rule-based quality gate — no LLM call required.

    Args:
        data: Parsed question dict from LLM.
        question_type: Expected type (choice, written, fill_blank, true_false).

    Returns:
        (is_valid, reason) — reason is empty string if valid.
    """
    if not isinstance(data, dict):
        return False, "Not a dict"

    qt = data.get("question_text", "")
    if not qt or len(qt.strip()) < 10:
        return False, "question_text missing or too short"

    ca = data.get("correct_answer", "")
    if not ca or not str(ca).strip():
        return False, "correct_answer missing"

    if question_type == "choice":
        opts = data.get("options", {})
        if not isinstance(opts, dict) or len(opts) < 2:
            return False, "choice question needs at least 2 options"
        # Check answer key matches an option
        if str(ca).strip().upper() not in [k.upper() for k in opts.keys()]:
            return False, f"correct_answer '{ca}' not in option keys {list(opts.keys())}"

    return True, ""


def validate_knowledge_points(data: dict) -> Tuple[bool, str]:
    """Validate LLM-generated knowledge points structure.

    Args:
        data: Parsed dict with 'knowledge_points' key.

    Returns:
        (is_valid, reason)
    """
    if not isinstance(data, dict):
        return False, "Not a dict"

    kps = data.get("knowledge_points")
    if not isinstance(kps, list) or len(kps) < 1:
        return False, "knowledge_points missing or empty"
    if len(kps) > 10:
        return False, f"Too many knowledge points ({len(kps)}), expected <=10"

    for i, kp in enumerate(kps):
        if not isinstance(kp, dict):
            return False, f"knowledge_points[{i}] is not a dict"
        title = kp.get("title", "")
        if not title or not str(title).strip():
            return False, f"knowledge_points[{i}] missing title"

    return True, ""


def validate_research_subtopics(data: dict, expected_count: int) -> Tuple[bool, str]:
    """Validate LLM-generated research subtopics structure.

    Args:
        data: Parsed dict with 'subtopics' key.
        expected_count: Expected number of subtopics.

    Returns:
        (is_valid, reason)
    """
    if not isinstance(data, dict):
        return False, "Not a dict"

    sts = data.get("subtopics")
    if not isinstance(sts, list) or len(sts) < 2:
        return False, "subtopics missing or fewer than 2"

    for i, st in enumerate(sts):
        if not isinstance(st, dict):
            return False, f"subtopics[{i}] is not a dict"
        title = st.get("title", "")
        if not title or not str(title).strip():
            return False, f"subtopics[{i}] missing title"

    return True, ""
