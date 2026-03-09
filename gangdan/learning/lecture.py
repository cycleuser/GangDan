"""Lecture & handout generation pipeline for the learning module."""

import sys
from pathlib import Path
from datetime import datetime
from typing import Iterator, Dict, List

from gangdan.learning.models import LectureSection, LectureDocument, generate_id
from gangdan.learning.prompts import get_prompt
from gangdan.learning.rag_helper import retrieve_context, collect_kb_documents
from gangdan.learning.utils import parse_json, llm_call_with_retry, llm_stream_with_timeout


def generate_lecture(
    topic: str,
    kb_names: List[str],
    ollama,
    chroma,
    config,
    docs_dir: Path,
    save_dir: Path,
    web_search: bool = False,
) -> Iterator[Dict]:
    """Generate a lecture/handout document. Yields SSE-compatible dicts.

    4-Phase Pipeline:
        1. Analyzing - Extract lecture structure from KB content
        2. Outlining - Refine section ordering and emphasis
        3. Writing   - Write each section with RAG context
        4. Summarizing - Generate abstract/summary

    Yields:
        {"type": "phase", "phase": "...", "message": "..."} - phase transitions
        {"type": "status", "message": "..."} - progress updates
        {"type": "outline", "data": [...]} - outline data
        {"type": "section", "index": i, "title": "..."} - section start
        {"type": "content", "content": "...", "done": bool} - streamed content
        {"type": "done", "lecture_id": "..."} - completion
        {"type": "error", "message": "..."} - errors
    """
    lang = config.language if config.language in ("zh", "en") else "en"
    lecture_id = generate_id("lecture_")

    # =========================================================================
    # Phase 1: Analyzing - Extract structure from KB
    # =========================================================================
    yield {"type": "phase", "phase": "analyzing",
           "message": "Analyzing knowledge base..." if lang == "en" else "正在分析知识库..."}

    # Collect KB content
    content = collect_kb_documents(kb_names, docs_dir, max_total_chars=6000)
    rag_context, _ = retrieve_context(topic, kb_names, ollama, chroma, config, max_chars=3000)

    combined = content
    if rag_context:
        combined += "\n\n" + rag_context

    if not combined.strip():
        yield {"type": "error",
               "message": "No content found in knowledge base." if lang == "en" else "知识库中未找到内容。"}
        return

    # Web search canary + enrichment
    web_available = False
    web_searcher = None
    if web_search:
        try:
            from gangdan.core.web_searcher import WebSearcher
            web_searcher = WebSearcher()
            canary = web_searcher.search(topic, num_results=1)
            if canary:
                web_available = True
                yield {"type": "status",
                       "message": "Web search available" if lang == "en" else "网络搜索可用"}
            else:
                yield {"type": "status",
                       "message": "Web search returned no results" if lang == "en" else "网络搜索无结果"}
        except Exception as e:
            print(f"[Lecture] Web search canary failed: {e}", file=sys.stderr)
            yield {"type": "status",
                   "message": "Web search unavailable" if lang == "en" else "网络搜索不可用"}

    # LLM: extract sections
    yield {"type": "status",
           "message": "Extracting lecture structure..." if lang == "en" else "正在提取讲义结构..."}

    prompt = get_prompt("lecture_analyze_kb", lang).format(topic=topic, content=combined[:5000])
    messages = [{"role": "user", "content": prompt}]
    data = llm_call_with_retry(
        ollama, config, messages, temperature=0.5,
        max_retries=2, parse_json_response=True, label="lecture_analyze_kb",
    )

    if not data or "sections" not in data or not data["sections"]:
        yield {"type": "error",
               "message": "Failed to analyze KB structure." if lang == "en" else "无法分析知识库结构。"}
        return

    raw_sections = data["sections"][:8]
    yield {"type": "outline", "data": raw_sections}
    print(f"[Lecture] Extracted {len(raw_sections)} sections", file=sys.stderr)

    # =========================================================================
    # Phase 2: Outlining - Refine order and emphasis
    # =========================================================================
    yield {"type": "phase", "phase": "outlining",
           "message": "Refining outline..." if lang == "en" else "正在优化大纲..."}

    import json as _json
    sections_json = _json.dumps(raw_sections, ensure_ascii=False, indent=2)
    prompt = get_prompt("lecture_outline", lang).format(topic=topic, sections_json=sections_json)
    messages = [{"role": "user", "content": prompt}]
    outline_data = llm_call_with_retry(
        ollama, config, messages, temperature=0.5,
        max_retries=1, parse_json_response=True, label="lecture_outline",
    )

    if outline_data and "outline" in outline_data and outline_data["outline"]:
        sections_plan = outline_data["outline"][:8]
    else:
        # Fallback: use raw sections with empty emphasis
        sections_plan = [{"title": s.get("title", ""), "instruction": s.get("instruction", ""), "emphasis": ""}
                         for s in raw_sections]

    yield {"type": "outline", "data": sections_plan}
    print(f"[Lecture] Outline refined: {len(sections_plan)} sections", file=sys.stderr)

    # =========================================================================
    # Phase 3: Writing - Generate each section
    # =========================================================================
    yield {"type": "phase", "phase": "writing",
           "message": "Writing lecture content..." if lang == "en" else "正在撰写讲义内容..."}

    lecture_sections: List[LectureSection] = []
    full_markdown = f"# {topic}\n\n"

    for i, sp in enumerate(sections_plan):
        if ollama.is_stopped():
            yield {"type": "status",
                   "message": "Generation stopped." if lang == "en" else "生成已停止。"}
            break

        title = sp.get("title", f"Section {i+1}")
        instruction = sp.get("instruction", "")
        emphasis = sp.get("emphasis", "")

        yield {"type": "section", "index": i, "title": title}
        yield {"type": "status",
               "message": f"Writing section {i+1}/{len(sections_plan)}: {title}" if lang == "en"
               else f"正在撰写第 {i+1}/{len(sections_plan)} 节：{title}"}

        # RAG retrieval for this section
        section_context, _ = retrieve_context(
            f"{title} {instruction}", kb_names, ollama, chroma, config, max_chars=2000
        )

        # Web search enrichment for this section
        if web_available and web_searcher:
            try:
                web_results = web_searcher.search(f"{topic} {title}", num_results=2)
                if web_results:
                    web_ctx = "\n".join(
                        f"\n[Web: {r.get('title', '')}]\n{r.get('snippet', '')}"
                        for r in web_results
                    )
                    section_context = (section_context or "") + "\n" + web_ctx
            except Exception:
                pass

        # Stream section content
        prompt = get_prompt("lecture_write_section", lang).format(
            title=title,
            instruction=instruction,
            emphasis=emphasis if emphasis else "N/A",
            context=section_context if section_context else "No additional context available.",
        )
        messages = [{"role": "user", "content": prompt}]
        section_text = ""

        for chunk in llm_stream_with_timeout(ollama, config, messages, temperature=0.6, timeout_seconds=120, label=f"lecture_section_{i}"):
            if ollama.is_stopped():
                break
            section_text += chunk
            yield {"type": "content", "content": chunk, "done": False}

        yield {"type": "content", "content": "", "done": False}  # Section boundary

        lecture_sections.append(LectureSection(
            section_id=f"sec_{i}",
            title=title,
            content=section_text,
            source_notes=section_context[:500] if section_context else "",
        ))
        full_markdown += f"\n## {title}\n\n{section_text}\n\n"

    # =========================================================================
    # Phase 4: Summarizing - Generate abstract
    # =========================================================================
    yield {"type": "phase", "phase": "summarizing",
           "message": "Generating summary..." if lang == "en" else "正在生成总结..."}

    notes_summary = "\n".join(
        f"- **{s.title}**: {s.content[:200]}..." for s in lecture_sections
    )
    prompt = get_prompt("lecture_summary", lang).format(notes_summary=notes_summary)
    messages = [{"role": "user", "content": prompt}]
    summary_text = ""

    for chunk in llm_stream_with_timeout(ollama, config, messages, temperature=0.5, timeout_seconds=60, label="lecture_summary"):
        if ollama.is_stopped():
            break
        summary_text += chunk
        yield {"type": "content", "content": chunk, "done": False}

    yield {"type": "content", "content": "", "done": True}

    # Prepend summary to full markdown
    if summary_text:
        full_markdown = f"# {topic}\n\n## Summary\n\n{summary_text}\n\n" + full_markdown.split("\n\n", 1)[-1] if "\n\n" in full_markdown else full_markdown

    # Save
    lecture = LectureDocument(
        lecture_id=lecture_id,
        topic=topic,
        kb_names=kb_names,
        created_at=datetime.now().isoformat(),
        sections=lecture_sections,
        summary=summary_text,
        lecture_markdown=full_markdown,
    )
    lecture.save(save_dir)
    print(f"[Lecture] Saved lecture {lecture_id} with {len(lecture_sections)} sections", file=sys.stderr)

    yield {"type": "done", "lecture_id": lecture_id}


def list_lectures(save_dir: Path) -> List[Dict]:
    """List all saved lectures."""
    lectures = []
    if not save_dir.exists():
        return lectures
    for f in sorted(save_dir.glob("lecture_*.json"), reverse=True):
        try:
            doc = LectureDocument.load(f)
            lectures.append({
                "lecture_id": doc.lecture_id,
                "topic": doc.topic,
                "kb_names": doc.kb_names,
                "section_count": len(doc.sections),
                "created_at": doc.created_at,
            })
        except Exception:
            continue
    return lectures
