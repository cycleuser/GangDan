"""Guided learning session manager for the learning module."""

import sys
from pathlib import Path
from datetime import datetime
from typing import Iterator, Dict, List, Optional

from gangdan.learning.models import KnowledgePoint, LearningSession, generate_id
from gangdan.learning.prompts import get_prompt
from gangdan.learning.rag_helper import retrieve_context, collect_kb_documents
from gangdan.learning.utils import parse_json, llm_call_with_retry, llm_stream_with_timeout, validate_knowledge_points


# In-memory session cache
_sessions: Dict[str, LearningSession] = {}


def _get_session(session_id: str, save_dir: Path) -> Optional[LearningSession]:
    """Load session from cache or disk."""
    if session_id in _sessions:
        return _sessions[session_id]
    filepath = save_dir / f"session_{session_id}.json"
    if filepath.exists():
        session = LearningSession.load(filepath)
        _sessions[session_id] = session
        return session
    return None


def _save_session(session: LearningSession, save_dir: Path):
    """Save session to cache and disk."""
    _sessions[session.session_id] = session
    session.save(save_dir)


def create_session(
    kb_names: List[str],
    ollama,
    chroma,
    config,
    docs_dir: Path,
    save_dir: Path,
    web_search: bool = False,
) -> Dict:
    """Create a new learning session by analyzing KB content.

    Returns: {"session_id": ..., "knowledge_points": [...], "status": ...}
    """
    lang = config.language if config.language in ("zh", "en") else "en"

    # Collect document content from KB directories
    content = collect_kb_documents(kb_names, docs_dir, max_total_chars=6000)
    if not content.strip():
        return {"error": "No documents found in selected knowledge bases." if lang == "en" else "所选知识库中未找到文档。"}

    # Web search enrichment: canary test + merge
    web_available = False
    web_searcher_ref = None
    if web_search:
        try:
            from gangdan.core.web_searcher import WebSearcher
            web_searcher_ref = WebSearcher()
            canary = web_searcher_ref.search(kb_names[0] if kb_names else "knowledge", num_results=1)
            if canary:
                web_available = True
                # Enrich content with web results
                web_results = web_searcher_ref.search(" ".join(kb_names), num_results=3)
                if web_results:
                    web_context = "\n".join(
                        f"\n[Web: {r.get('title', '')}]\n{r.get('snippet', '')}"
                        for r in web_results
                    )
                    content += "\n" + web_context
                    print(f"[Guided] Web search enriched content with {len(web_context)} chars", file=sys.stderr)
        except Exception as e:
            print(f"[Guided] Web search canary failed: {e}", file=sys.stderr)

    # Use LLM to analyze and extract knowledge points
    prompt_template = get_prompt("guide_analyze_kb", lang)
    prompt = prompt_template.format(content=content[:5000])

    messages = [{"role": "user", "content": prompt}]
    data = llm_call_with_retry(
        ollama, config, messages, temperature=0.5,
        max_retries=2, parse_json_response=True, label="guide_analyze_kb",
    )

    # Quality gate: validate knowledge points structure
    if data:
        is_valid, reason = validate_knowledge_points(data)
        if not is_valid:
            print(f"[Guided] KP validation failed: {reason}. Retrying once.", file=sys.stderr)
            # Retry with explicit hint
            retry_messages = [{"role": "user", "content": prompt + "\n\nIMPORTANT: Return valid JSON with a 'knowledge_points' array. Each item must have a 'title' field."}]
            data = llm_call_with_retry(
                ollama, config, retry_messages, temperature=0.5,
                max_retries=1, parse_json_response=True, label="guide_analyze_kb_retry",
            )

    if not data or "knowledge_points" not in data:
        return {"error": "Failed to analyze knowledge base content." if lang == "en" else "无法分析知识库内容。"}

    kps = []
    for kp_data in data["knowledge_points"][:5]:
        kps.append(KnowledgePoint(
            title=kp_data.get("title", "Untitled"),
            description=kp_data.get("description", ""),
            key_concepts=kp_data.get("key_concepts", []),
        ))

    if not kps:
        return {"error": "No knowledge points identified." if lang == "en" else "未识别到知识点。"}

    session = LearningSession(
        session_id=generate_id("guide_"),
        kb_names=kb_names,
        created_at=datetime.now().isoformat(),
        knowledge_points=kps,
        current_index=0,
        status="initialized",
        analytics={"web_available": web_available},
    )
    _save_session(session, save_dir)

    return {
        "session_id": session.session_id,
        "knowledge_points": [
            {"title": kp.title, "description": kp.description, "key_concepts": kp.key_concepts}
            for kp in kps
        ],
        "status": session.status,
    }


def generate_lesson(
    session_id: str,
    ollama,
    chroma,
    config,
    docs_dir: Path,
    save_dir: Path,
    web_search: bool = False,
) -> Iterator[Dict]:
    """Generate lesson content for the current knowledge point. Yields SSE dicts."""
    lang = config.language if config.language in ("zh", "en") else "en"
    session = _get_session(session_id, save_dir)
    if not session:
        yield {"type": "error", "message": "Session not found."}
        return

    kp = session.current_point
    if not kp:
        yield {"type": "error", "message": "No current knowledge point."}
        return

    # Check if we have cached content
    idx_key = str(session.current_index)
    if idx_key in session.lesson_contents and session.lesson_contents[idx_key]:
        yield {"type": "content", "content": session.lesson_contents[idx_key], "done": True}
        return

    session.status = "learning"

    # Retrieve context from KB for this knowledge point
    context, _ = retrieve_context(
        f"{kp.title} {kp.description}", session.kb_names, ollama, chroma, config, max_chars=2000
    )

    # Web search enrichment for lesson content
    web_available = session.analytics.get("web_available", False) if session.analytics else False
    if web_search or web_available:
        try:
            from gangdan.core.web_searcher import WebSearcher
            ws = WebSearcher()
            web_results = ws.search(f"{kp.title} {kp.description}", num_results=3)
            if web_results:
                web_ctx = "\n".join(
                    f"\n[Web: {r.get('title', '')}]\n{r.get('snippet', '')}"
                    for r in web_results
                )
                context = (context or "") + "\n" + web_ctx
        except Exception as e:
            print(f"[Guided] Web search for lesson failed: {e}", file=sys.stderr)

    prompt_template = get_prompt("guide_generate_lesson", lang)
    prompt = prompt_template.format(
        title=kp.title,
        description=kp.description,
        concepts=", ".join(kp.key_concepts) if kp.key_concepts else "N/A",
        context=context if context else "No additional context available.",
    )

    messages = [{"role": "user", "content": prompt}]
    full_text = ""
    for chunk in llm_stream_with_timeout(ollama, config, messages, temperature=0.6, timeout_seconds=120, label="guide_lesson"):
        if ollama.is_stopped():
            yield {"type": "content", "content": "\n\n[Stopped]", "done": True}
            break
        full_text += chunk
        yield {"type": "content", "content": chunk, "done": False}

    # Cache the lesson content
    session.lesson_contents[idx_key] = full_text
    _save_session(session, save_dir)
    yield {"type": "content", "content": "", "done": True}


def chat_in_session(
    session_id: str,
    user_message: str,
    ollama,
    chroma,
    config,
    save_dir: Path,
    web_search: bool = False,
) -> Iterator[Dict]:
    """Chat within a learning session context. Yields SSE dicts."""
    lang = config.language if config.language in ("zh", "en") else "en"
    session = _get_session(session_id, save_dir)
    if not session:
        yield {"type": "error", "message": "Session not found."}
        return

    kp = session.current_point
    if not kp:
        yield {"type": "error", "message": "No current knowledge point."}
        return

    idx_key = str(session.current_index)

    # Build chat history string (last 6 messages for context window)
    history = session.chat_histories.get(idx_key, [])
    history_str = ""
    for msg in history[-6:]:
        role = "Student" if msg["role"] == "user" else "Teacher"
        history_str += f"**{role}**: {msg['content']}\n\n"

    prompt_template = get_prompt("guide_chat", lang)
    prompt = prompt_template.format(
        title=kp.title,
        description=kp.description,
        chat_history=history_str if history_str else "No previous conversation.",
    )

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_message},
    ]

    full_text = ""
    for chunk in llm_stream_with_timeout(ollama, config, messages, temperature=0.6, timeout_seconds=120, label="guide_chat"):
        if ollama.is_stopped():
            yield {"type": "content", "content": "\n\n[Stopped]", "done": True}
            break
        full_text += chunk
        yield {"type": "content", "content": chunk, "done": False}

    # Save chat history
    if idx_key not in session.chat_histories:
        session.chat_histories[idx_key] = []
    session.chat_histories[idx_key].append({"role": "user", "content": user_message})
    session.chat_histories[idx_key].append({"role": "assistant", "content": full_text})
    _save_session(session, save_dir)
    yield {"type": "content", "content": "", "done": True}


def next_point(session_id: str, save_dir: Path) -> Dict:
    """Advance to the next knowledge point.

    Returns: {"current_index", "knowledge_point", "is_complete", "progress_pct"}
    """
    session = _get_session(session_id, save_dir)
    if not session:
        return {"error": "Session not found."}

    next_idx = session.current_index + 1
    if next_idx >= len(session.knowledge_points):
        session.status = "completed"
        _save_session(session, save_dir)
        return {
            "is_complete": True,
            "current_index": session.current_index,
            "progress_pct": 100,
        }

    session.current_index = next_idx
    _save_session(session, save_dir)

    kp = session.current_point
    return {
        "is_complete": False,
        "current_index": next_idx,
        "knowledge_point": {
            "title": kp.title,
            "description": kp.description,
            "key_concepts": kp.key_concepts,
        },
        "progress_pct": session.progress_pct,
    }


def generate_summary(
    session_id: str,
    ollama,
    config,
    save_dir: Path,
) -> Iterator[Dict]:
    """Generate a learning summary. Yields SSE dicts."""
    lang = config.language if config.language in ("zh", "en") else "en"
    session = _get_session(session_id, save_dir)
    if not session:
        yield {"type": "error", "message": "Session not found."}
        return

    # Build points summary
    points_summary = ""
    for i, kp in enumerate(session.knowledge_points):
        points_summary += f"{i+1}. **{kp.title}**: {kp.description}\n"

    # Build chat summary
    chat_summary = ""
    for idx_key, messages in session.chat_histories.items():
        idx = int(idx_key)
        if idx < len(session.knowledge_points):
            kp_title = session.knowledge_points[idx].title
            chat_summary += f"\n--- {kp_title} ---\n"
            for msg in messages[-4:]:
                role = "Student" if msg["role"] == "user" else "Teacher"
                chat_summary += f"**{role}**: {msg['content'][:200]}\n"

    prompt_template = get_prompt("guide_summary", lang)
    prompt = prompt_template.format(
        points_summary=points_summary,
        chat_summary=chat_summary if chat_summary else "No Q&A interactions recorded.",
    )

    messages = [{"role": "user", "content": prompt}]
    full_text = ""
    for chunk in llm_stream_with_timeout(ollama, config, messages, temperature=0.5, timeout_seconds=120, label="guide_summary"):
        if ollama.is_stopped():
            yield {"type": "content", "content": "\n\n[Stopped]", "done": True}
            break
        full_text += chunk
        yield {"type": "content", "content": chunk, "done": False}

    session.summary = full_text
    _save_session(session, save_dir)
    yield {"type": "content", "content": "", "done": True}


def get_session_state(session_id: str, save_dir: Path) -> Optional[Dict]:
    """Get the current state of a session."""
    session = _get_session(session_id, save_dir)
    if not session:
        return None
    kp = session.current_point
    return {
        "session_id": session.session_id,
        "kb_names": session.kb_names,
        "status": session.status,
        "current_index": session.current_index,
        "total_points": len(session.knowledge_points),
        "progress_pct": session.progress_pct,
        "current_point": {
            "title": kp.title,
            "description": kp.description,
            "key_concepts": kp.key_concepts,
        } if kp else None,
        "knowledge_points": [
            {"title": p.title, "description": p.description, "key_concepts": p.key_concepts}
            for p in session.knowledge_points
        ],
        "has_summary": bool(session.summary),
    }


def list_sessions(save_dir: Path) -> List[Dict]:
    """List all saved sessions."""
    sessions = []
    if not save_dir.exists():
        return sessions
    for f in sorted(save_dir.glob("session_*.json"), reverse=True):
        try:
            session = LearningSession.load(f)
            sessions.append({
                "session_id": session.session_id,
                "kb_names": session.kb_names,
                "created_at": session.created_at,
                "status": session.status,
                "total_points": len(session.knowledge_points),
                "current_index": session.current_index,
                "progress_pct": session.progress_pct,
            })
        except Exception:
            continue
    return sessions

