"""Deep research pipeline for the learning module."""

import sys
from pathlib import Path
from datetime import datetime
from typing import Iterator, Dict, List, Tuple

from gangdan.learning.models import ResearchSubtopic, ResearchReport, Citation, generate_id
from gangdan.learning.prompts import get_prompt
from gangdan.learning.rag_helper import retrieve_context, compress_rag_notes
from gangdan.learning.utils import parse_json, llm_call_with_retry, llm_stream_with_timeout, validate_research_subtopics, jaccard_word_similarity


# Depth presets: (num_subtopics, rag_calls_per_topic)
DEPTH_PRESETS = {
    "quick": (3, 1),
    "medium": (5, 1),
    "deep": (7, 2),
    "auto": (5, 2),  # same as deep but enables autonomous iteration loop
}


def run_research(
    topic: str,
    kb_names: List[str],
    depth: str,
    ollama,
    chroma,
    config,
    save_dir: Path = None,
    web_search: bool = False,
) -> Iterator[Dict]:
    """Run the full research pipeline. Yields SSE-compatible dicts.

    Yields:
        {"type": "phase", "phase": "rephrasing|planning|researching|refining|reporting", "message": "..."}
        {"type": "status", "message": "..."}
        {"type": "subtopic", "data": {...}}
        {"type": "iteration", "current": int, "max": int, ...}
        {"type": "content", "content": "...", "done": bool}
        {"type": "done", "report_id": "..."}
        {"type": "error", "message": "..."}
    """
    lang = config.language if config.language in ("zh", "en") else "en"
    num_subtopics, rag_calls = DEPTH_PRESETS.get(depth, DEPTH_PRESETS["medium"])
    report_id = generate_id("research_")

    # =========================================================================
    # Phase 0: Rephrase Topic (DeepTutor RephraseAgent pattern)
    # =========================================================================
    yield {"type": "phase", "phase": "rephrasing",
           "message": "Optimizing research topic..." if lang == "en" else "正在优化研究主题..."}

    rephrased = _rephrase_topic(topic, lang, ollama, config)
    if rephrased and rephrased != topic and len(rephrased) < 300:
        yield {"type": "status",
               "message": f"Rephrased: {rephrased}" if lang == "en"
               else f"优化后的主题：{rephrased}"}
        topic = rephrased
    else:
        yield {"type": "status",
               "message": "Topic is clear, proceeding..." if lang == "en"
               else "主题已足够清晰，继续..."}

    # =========================================================================
    # Phase 1: Planning
    # =========================================================================
    yield {"type": "phase", "phase": "planning",
           "message": "Planning research..." if lang == "en" else "正在规划研究..."}

    yield {"type": "status",
           "message": f"Decomposing topic into {num_subtopics} subtopics..." if lang == "en"
           else f"正在将主题分解为 {num_subtopics} 个子主题..."}

    subtopics = _decompose_topic(topic, num_subtopics, lang, ollama, config)
    if not subtopics:
        # Fallback: create generic subtopics
        subtopics = [ResearchSubtopic(title=f"Aspect {i+1} of {topic}", overview="") for i in range(num_subtopics)]

    for st in subtopics:
        st.status = "PENDING"
        yield {"type": "subtopic", "data": {"title": st.title, "overview": st.overview, "status": "PENDING"}}

    print(f"[Research] Planned {len(subtopics)} subtopics", file=sys.stderr)

    # =========================================================================
    # Phase 2: Researching (Analysis Loop - DeepTutor two-loop pattern)
    # =========================================================================
    yield {"type": "phase", "phase": "researching",
           "message": "Researching subtopics..." if lang == "en" else "正在研究各子主题..."}

    # Citation tracking
    citation_counter = [0]
    all_citations = []
    source_to_citation = {}  # maps source_file -> citation_id

    def get_citation_id(source_file, coll_name="", source_type="kb", url=""):
        """Assign a citation ID to a source, deduplicating."""
        if source_file in source_to_citation:
            return source_to_citation[source_file]
        citation_counter[0] += 1
        cid = f"[{citation_counter[0]}]"
        source_to_citation[source_file] = cid
        all_citations.append(Citation(
            citation_id=cid, source_file=source_file, collection_name=coll_name,
            source_type=source_type, url=url,
        ))
        return cid

    # Web search: canary test (check connectivity once before subtopic loop)
    web_available = False
    web_searcher = None
    if web_search:
        try:
            from gangdan.core.web_searcher import WebSearcher
            web_searcher = WebSearcher()
            canary_results = web_searcher.search(topic, num_results=1)
            if canary_results:
                web_available = True
                yield {"type": "status",
                       "message": "Web search available" if lang == "en" else "网络搜索可用"}
            else:
                yield {"type": "status",
                       "message": "Web search returned no results, using KB only" if lang == "en"
                       else "网络搜索无结果，仅使用知识库"}
        except Exception as e:
            print(f"[Research] Web search canary failed: {e}", file=sys.stderr)
            yield {"type": "status",
                   "message": "Web search unavailable, using KB only" if lang == "en"
                   else "网络搜索不可用，仅使用知识库"}

    # Iteration loop (autonomous research pattern from AutoResearch)
    max_iterations = MAX_AUTO_ITERATIONS if depth == "auto" else 1
    iteration = 0

    while iteration < max_iterations:
        if ollama.is_stopped():
            yield {"type": "status", "message": "Research stopped." if lang == "en" else "研究已停止。"}
            break

        if iteration > 0:
            yield {"type": "phase", "phase": "refining",
                   "message": f"Refining research (iteration {iteration + 1}/{max_iterations})..." if lang == "en"
                   else f"正在深化研究（迭代 {iteration + 1}/{max_iterations}）..."}

        # Determine which subtopics to research this iteration
        if iteration == 0:
            subtopics_to_research = subtopics
        else:
            # Re-research weak subtopics + any new ones added by expansion
            subtopics_to_research = [st for st in subtopics if st.status in ("PENDING", "WEAK")]

        for i, st in enumerate(subtopics_to_research):
            if ollama.is_stopped():
                yield {"type": "status", "message": "Research stopped." if lang == "en" else "研究已停止。"}
                break

            # State: -> RESEARCHING
            old_notes_len = len(st.notes) if st.notes else 0
            st.status = "RESEARCHING"
            yield {"type": "subtopic", "data": {"title": st.title, "overview": st.overview,
                                                 "status": "RESEARCHING", "iteration": iteration}}
            yield {"type": "status",
                   "message": f"Researching [{i+1}/{len(subtopics_to_research)}]: {st.title}" if lang == "en"
                   else f"正在研究 [{i+1}/{len(subtopics_to_research)}]：{st.title}"}

            # Multi-query RAG retrieval
            all_context = ""
            all_sources = set()

            # Use follow-up queries if available (from expansion), otherwise default queries
            if hasattr(st, '_follow_up_query') and st._follow_up_query:
                queries = [st._follow_up_query, f"{st.title} {st.overview}"]
            else:
                queries = [
                    f"{st.title} {st.overview}",
                    f"{st.title} key concepts definition",
                ]
                if rag_calls >= 2:
                    queries.append(f"{topic} {st.title} details examples")

            for query in queries:
                ctx, srcs = retrieve_context(query, kb_names, ollama, chroma, config, max_chars=2000)
                if ctx:
                    all_context += ctx + "\n"
                    all_sources.update(srcs)

            # Web search integration (if available)
            web_sources_count = 0
            if web_available and web_searcher:
                web_ctx, web_results = _web_search_subtopic(st.title, topic, web_searcher)
                if web_ctx:
                    all_context += web_ctx + "\n"
                    web_sources_count = len(web_results)
                    for wr in web_results:
                        get_citation_id(wr["title"], coll_name="web",
                                        source_type="web", url=wr.get("url", ""))

            # Build citation IDs for KB sources
            for src in all_sources:
                get_citation_id(src)

            try:
                # Summarize findings with note compression
                if all_context.strip():
                    compressed_context = compress_rag_notes(all_context, st.title, ollama, config)
                    notes = _summarize_subtopic(st.title, st.overview, compressed_context, lang, ollama, config)
                else:
                    notes = f"No relevant content found for: {st.title}"

                # For re-research iterations, append to existing notes
                if iteration > 0 and st.notes and notes:
                    st.notes = st.notes + "\n\n---\n\n" + notes
                else:
                    st.notes = notes

                st.sources = sorted(list(all_sources))
                st.citation_id = ", ".join(source_to_citation.get(s, "") for s in st.sources if s in source_to_citation)

                # State: RESEARCHING -> COMPLETED
                st.status = "COMPLETED"
                source_detail = f"{len(all_sources)} KB"
                if web_sources_count > 0:
                    source_detail += f", {web_sources_count} web"
                yield {"type": "subtopic", "data": {"title": st.title, "overview": st.overview,
                                                     "status": "COMPLETED", "sources": st.sources,
                                                     "source_detail": source_detail,
                                                     "iteration": iteration}}
            except Exception as e:
                st.status = "FAILED"
                st.notes = st.notes or "" + f"\nResearch failed: {str(e)[:200]}"
                print(f"[Research] Subtopic '{st.title}' failed: {e}", file=sys.stderr)
                yield {"type": "subtopic", "data": {"title": st.title, "overview": st.overview,
                                                     "status": "FAILED", "sources": [],
                                                     "iteration": iteration}}

        completed = [st for st in subtopics if st.status == "COMPLETED"]
        failed = [st for st in subtopics if st.status == "FAILED"]
        print(f"[Research] Iteration {iteration}: Completed: {len(completed)}, Failed: {len(failed)}", file=sys.stderr)

        # Autonomous loop: evaluate and possibly expand
        if depth == "auto" and iteration < max_iterations - 1 and not ollama.is_stopped():
            yield {"type": "status",
                   "message": "Evaluating findings..." if lang == "en" else "正在评估研究结果..."}

            evaluation = _evaluate_findings(completed, topic, lang, ollama, config)
            yield {"type": "iteration", "current": iteration + 1, "max": max_iterations,
                   "sufficient": evaluation.get("sufficient", True),
                   "weak_count": len(evaluation.get("weak_subtopics", []))}

            if evaluation.get("sufficient", True):
                yield {"type": "status",
                       "message": "Findings sufficient, proceeding to report" if lang == "en"
                       else "研究结果充分，开始生成报告"}
                break

            # Expand research
            weak_titles = evaluation.get("weak_subtopics", [])
            yield {"type": "status",
                   "message": f"Expanding research for {len(weak_titles)} weak subtopics..." if lang == "en"
                   else f"正在扩展 {len(weak_titles)} 个薄弱子主题的研究..."}

            expansion = _expand_research(weak_titles, topic, lang, ollama, config)

            # Mark weak subtopics for re-research
            for st in subtopics:
                if st.title in weak_titles and st.status == "COMPLETED":
                    st.status = "WEAK"
                    # Attach follow-up query if available
                    for fq in expansion.get("follow_up_queries", []):
                        if fq.get("subtopic") == st.title:
                            st._follow_up_query = fq.get("query", "")
                            break

            # Add new subtopics from expansion
            for new_st in expansion.get("new_subtopics", [])[:2]:  # cap at 2 new
                new_sub = ResearchSubtopic(
                    title=new_st.get("title", ""), overview=new_st.get("overview", ""),
                    status="PENDING",
                )
                new_sub.iteration = iteration + 1
                subtopics.append(new_sub)
                yield {"type": "subtopic", "data": {"title": new_sub.title, "overview": new_sub.overview,
                                                     "status": "PENDING", "iteration": iteration + 1}}
        else:
            break

        iteration += 1

    completed = [st for st in subtopics if st.status == "COMPLETED"]
    failed = [st for st in subtopics if st.status == "FAILED"]
    print(f"[Research] Final: Completed: {len(completed)}, Failed: {len(failed)}", file=sys.stderr)

    # =========================================================================
    # Phase 3: Reporting (Report Loop - only uses COMPLETED subtopics)
    # =========================================================================
    yield {"type": "phase", "phase": "reporting",
           "message": "Generating report..." if lang == "en" else "正在生成报告..."}

    if ollama.is_stopped():
        return

    # Generate outline from COMPLETED subtopics only
    yield {"type": "status",
           "message": "Creating report outline..." if lang == "en" else "正在创建报告大纲..."}

    notes_summary = ""
    for st in completed:
        notes_summary += f"\n### {st.title}\n{st.notes[:500]}\n"

    outline = _generate_outline(topic, notes_summary, lang, ollama, config)
    if not outline:
        outline = [{"title": "Introduction", "instruction": f"Overview of {topic}"}]
        for st in completed:
            outline.append({"title": st.title, "instruction": f"Discuss findings about {st.title}"})
        outline.append({"title": "Conclusion", "instruction": "Summary and key takeaways"})

    # Write report sections
    full_report = f"# {topic}\n\n"
    yield {"type": "content", "content": f"# {topic}\n\n", "done": False}

    for j, section in enumerate(outline):
        if ollama.is_stopped():
            break

        yield {"type": "status",
               "message": f"Writing section [{j+1}/{len(outline)}]: {section['title']}" if lang == "en"
               else f"正在撰写章节 [{j+1}/{len(outline)}]：{section['title']}"}

        # Find relevant notes using Jaccard similarity (only from COMPLETED subtopics)
        section_notes = ""
        scored = [(st, jaccard_word_similarity(section["title"], st.title)) for st in completed]
        scored.sort(key=lambda x: x[1], reverse=True)
        for st, score in scored[:2]:
            if score > 0.1 or not section_notes:
                section_notes += st.notes + "\n"
        if not section_notes:
            section_notes = notes_summary[:1500]

        section_header = f"## {section['title']}\n\n"
        yield {"type": "content", "content": section_header, "done": False}
        full_report += section_header

        # Stream section content
        for chunk in _write_section_stream(
            section["title"], section.get("instruction", ""), section_notes, lang, ollama, config
        ):
            if ollama.is_stopped():
                break
            full_report += chunk
            yield {"type": "content", "content": chunk, "done": False}

        full_report += "\n\n"
        yield {"type": "content", "content": "\n\n", "done": False}

    # Add Limitations section for FAILED subtopics
    if failed:
        limitations_header = "## Limitations\n\n" if lang == "en" else "## 局限性\n\n"
        limitations_body = ("The following subtopics could not be fully researched:\n\n" if lang == "en"
                          else "以下子主题未能完整研究：\n\n")
        for st in failed:
            limitations_body += f"- **{st.title}**: {st.notes}\n"
        limitations_body += "\n"
        full_report += limitations_header + limitations_body
        yield {"type": "content", "content": limitations_header + limitations_body, "done": False}

    # Add References section with structured citations
    if all_citations:
        refs_header = "## References\n\n" if lang == "en" else "## 参考来源\n\n"
        refs_body = ""
        for cit in all_citations:
            if cit.source_type == "web":
                refs_body += f"- {cit.citation_id} \U0001F310 {cit.source_file}"
                if cit.url:
                    refs_body += f" ({cit.url})"
            else:
                refs_body += f"- {cit.citation_id} \U0001F4DA {cit.source_file}"
                if cit.collection_name:
                    refs_body += f" ({cit.collection_name})"
            refs_body += "\n"
        refs_body += "\n"
        full_report += refs_header + refs_body
        yield {"type": "content", "content": refs_header + refs_body, "done": False}

    yield {"type": "content", "content": "", "done": True}

    # Save report
    if save_dir:
        report = ResearchReport(
            report_id=report_id,
            topic=topic,
            kb_names=kb_names,
            depth=depth,
            created_at=datetime.now().isoformat(),
            subtopics=subtopics,
            citations=all_citations,
            report_markdown=full_report,
        )
        report.save(save_dir)
        print(f"[Research] Saved report {report_id}", file=sys.stderr)

    yield {"type": "done", "report_id": report_id}


def _rephrase_topic(topic, lang, ollama, config) -> str:
    """Rephrase/optimize a research topic for clarity (DeepTutor RephraseAgent pattern)."""
    prompt_template = get_prompt("research_rephrase", lang)
    prompt = prompt_template.format(topic=topic)

    messages = [{"role": "user", "content": prompt}]
    result = llm_call_with_retry(
        ollama, config, messages, temperature=0.3,
        max_retries=1, parse_json_response=False, label="research_rephrase",
    )
    if result and result.strip():
        # Clean up: remove quotes, leading/trailing whitespace
        cleaned = result.strip().strip('"\'')
        if cleaned and len(cleaned) < 300:
            return cleaned
    return ""


def _web_search_subtopic(subtopic_title: str, topic: str, web_searcher) -> Tuple[str, List[Dict]]:
    """Search the web for a subtopic and return formatted context + raw results."""
    try:
        results = web_searcher.search(f"{topic} {subtopic_title}", num_results=3)
        if not results:
            return "", []
        context = ""
        for r in results:
            snippet = f"\n[Web: {r.get('title', 'untitled')}]\n{r.get('snippet', '')}\n"
            context += snippet
        return context, results
    except Exception as e:
        print(f"[Research] Web search error for '{subtopic_title}': {e}", file=sys.stderr)
        return "", []


# Autonomous research loop constants
MAX_AUTO_ITERATIONS = 3
MIN_NOTES_LENGTH = 200


def _evaluate_findings(completed_subtopics: List[ResearchSubtopic], topic: str, lang: str, ollama, config) -> Dict:
    """Evaluate whether research findings are sufficient (AutoResearch pattern).

    Uses a rule-based fast path before falling back to LLM evaluation.
    """
    # Rule-based fast path: if all subtopics have decent notes and sources, skip LLM
    all_sufficient = all(
        len(st.notes or "") >= MIN_NOTES_LENGTH and len(st.sources or []) >= 2
        for st in completed_subtopics
    )
    if all_sufficient:
        print("[Research] All subtopics pass rule-based sufficiency check", file=sys.stderr)
        return {"sufficient": True, "weak_subtopics": [], "reasoning": "All subtopics have adequate findings."}

    # LLM evaluation
    prompt_template = get_prompt("research_evaluate_findings", lang)
    notes_summary = ""
    for st in completed_subtopics:
        notes_len = len(st.notes or "")
        src_count = len(st.sources or [])
        notes_summary += f"- {st.title}: {notes_len} chars, {src_count} sources\n"
        if st.notes:
            notes_summary += f"  Preview: {st.notes[:150]}...\n"

    prompt = prompt_template.format(topic=topic, notes_summary=notes_summary)
    messages = [{"role": "user", "content": prompt}]

    data = llm_call_with_retry(
        ollama, config, messages, temperature=0.3,
        max_retries=1, parse_json_response=True, label="research_evaluate",
    )

    if data and isinstance(data, dict):
        return {
            "sufficient": data.get("sufficient", True),
            "weak_subtopics": data.get("weak_subtopics", []),
            "reasoning": data.get("reasoning", ""),
        }

    # Fallback: stop the loop on parse failure
    print("[Research] Evaluation parse failed, assuming sufficient", file=sys.stderr)
    return {"sufficient": True, "weak_subtopics": [], "reasoning": "Evaluation parse failed."}


def _expand_research(weak_titles: List[str], topic: str, lang: str, ollama, config) -> Dict:
    """Generate follow-up queries and optional new subtopics for weak areas."""
    prompt_template = get_prompt("research_expand_queries", lang)
    weak_list = "\n".join(f"- {t}" for t in weak_titles)
    prompt = prompt_template.format(topic=topic, weak_subtopics=weak_list)

    messages = [{"role": "user", "content": prompt}]
    data = llm_call_with_retry(
        ollama, config, messages, temperature=0.5,
        max_retries=1, parse_json_response=True, label="research_expand",
    )

    if data and isinstance(data, dict):
        return {
            "follow_up_queries": data.get("follow_up_queries", []),
            "new_subtopics": data.get("new_subtopics", []),
        }

    return {"follow_up_queries": [], "new_subtopics": []}


def _decompose_topic(topic, num_subtopics, lang, ollama, config) -> List[ResearchSubtopic]:
    """Decompose research topic into subtopics with quality gate validation."""
    prompt_template = get_prompt("research_decompose", lang)
    prompt = prompt_template.format(topic=topic, num_subtopics=num_subtopics)

    messages = [{"role": "user", "content": prompt}]
    data = llm_call_with_retry(
        ollama, config, messages, temperature=0.5,
        max_retries=2, parse_json_response=True, label="research_decompose",
    )

    # Quality gate: validate subtopics structure
    if data:
        is_valid, reason = validate_research_subtopics(data, num_subtopics)
        if not is_valid:
            print(f"[Research] Subtopic validation failed: {reason}. Retrying once.", file=sys.stderr)
            retry_messages = [{"role": "user", "content": prompt + "\n\nIMPORTANT: Return valid JSON with a 'subtopics' array of at least 2 items. Each must have 'title' and 'overview'."}]
            data = llm_call_with_retry(
                ollama, config, retry_messages, temperature=0.5,
                max_retries=1, parse_json_response=True, label="research_decompose_retry",
            )

    if data and "subtopics" in data:
        return [
            ResearchSubtopic(title=s.get("title", ""), overview=s.get("overview", ""))
            for s in data["subtopics"][:num_subtopics]
        ]
    return []


def _summarize_subtopic(subtopic, overview, rag_content, lang, ollama, config) -> str:
    """Summarize RAG results for a subtopic."""
    prompt_template = get_prompt("research_summarize", lang)
    prompt = prompt_template.format(
        subtopic=subtopic,
        overview=overview,
        rag_content=rag_content[:2500],
    )

    messages = [{"role": "user", "content": prompt}]
    result = llm_call_with_retry(
        ollama, config, messages, temperature=0.4,
        max_retries=1, parse_json_response=False, label="research_summarize",
    )
    return result or ""


def _generate_outline(topic, notes_summary, lang, ollama, config) -> List[Dict]:
    """Generate report outline."""
    prompt_template = get_prompt("research_outline", lang)
    prompt = prompt_template.format(topic=topic, notes_summary=notes_summary[:3000])

    messages = [{"role": "user", "content": prompt}]
    data = llm_call_with_retry(
        ollama, config, messages, temperature=0.4,
        max_retries=2, parse_json_response=True, label="research_outline",
    )
    if data and "sections" in data:
        return data["sections"]
    return []


def _write_section_stream(section_title, instruction, notes, lang, ollama, config) -> Iterator[str]:
    """Stream a report section."""
    prompt_template = get_prompt("research_write_section", lang)
    prompt = prompt_template.format(
        section_title=section_title,
        instruction=instruction,
        notes=notes[:2500],
    )

    messages = [{"role": "user", "content": prompt}]
    for chunk in llm_stream_with_timeout(ollama, config, messages, temperature=0.6, timeout_seconds=120, label="research_section"):
        if ollama.is_stopped():
            break
        yield chunk


def list_reports(save_dir: Path) -> List[Dict]:
    """List all saved research reports."""
    reports = []
    if not save_dir.exists():
        return reports
    for f in sorted(save_dir.glob("research_*.json"), reverse=True):
        try:
            report = ResearchReport.load(f)
            reports.append({
                "report_id": report.report_id,
                "topic": report.topic,
                "kb_names": report.kb_names,
                "depth": report.depth,
                "created_at": report.created_at,
                "subtopic_count": len(report.subtopics),
            })
        except Exception:
            continue
    return reports

