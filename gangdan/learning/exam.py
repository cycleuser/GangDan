"""Exam paper generation pipeline for the learning module."""

import sys
from pathlib import Path
from datetime import datetime
from typing import Iterator, Dict, List

from gangdan.learning.models import ExamQuestion, ExamSection, ExamPaper, generate_id
from gangdan.learning.prompts import get_prompt
from gangdan.learning.rag_helper import retrieve_context, collect_kb_documents
from gangdan.learning.utils import parse_json, llm_call_with_retry, llm_stream_with_timeout, validate_question


def generate_exam(
    topic: str,
    kb_names: List[str],
    difficulty: str,
    ollama,
    chroma,
    config,
    docs_dir: Path,
    save_dir: Path,
    web_search: bool = False,
) -> Iterator[Dict]:
    """Generate an exam paper. Yields SSE-compatible dicts.

    4-Phase Pipeline:
        1. Planning   - Plan exam structure (sections, types, points)
        2. Generating - Generate questions per section
        3. Answer Key - Generate answer key with marking rubric
        4. Formatting - Format final exam paper

    Yields:
        {"type": "phase", "phase": "...", "message": "..."} - phase transitions
        {"type": "status", "message": "..."} - progress updates
        {"type": "plan", "data": {...}} - exam plan
        {"type": "section", "data": {...}} - completed section
        {"type": "content", "content": "...", "section": "...", "done": bool} - streamed content
        {"type": "done", "paper_id": "..."} - completion
        {"type": "error", "message": "..."} - errors
    """
    lang = config.language if config.language in ("zh", "en") else "en"
    paper_id = generate_id("exam_")

    # =========================================================================
    # Phase 1: Planning - Plan exam structure
    # =========================================================================
    yield {"type": "phase", "phase": "planning",
           "message": "Planning exam structure..." if lang == "en" else "正在规划试卷结构..."}

    # Retrieve KB context
    content = collect_kb_documents(kb_names, docs_dir, max_total_chars=4000)
    rag_context, _ = retrieve_context(topic, kb_names, ollama, chroma, config, max_chars=3000)
    combined_context = (content + "\n\n" + rag_context) if rag_context else content

    if not combined_context.strip():
        yield {"type": "error",
               "message": "No content found in knowledge base." if lang == "en" else "知识库中未找到内容。"}
        return

    # Web search canary
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
                # Enrich context with web results
                web_results = web_searcher.search(topic, num_results=3)
                if web_results:
                    web_ctx = "\n".join(
                        f"\n[Web: {r.get('title', '')}]\n{r.get('snippet', '')}"
                        for r in web_results
                    )
                    combined_context += "\n" + web_ctx
            else:
                yield {"type": "status",
                       "message": "Web search returned no results" if lang == "en" else "网络搜索无结果"}
        except Exception as e:
            print(f"[Exam] Web search canary failed: {e}", file=sys.stderr)

    # LLM: plan exam structure
    prompt = get_prompt("exam_plan", lang).format(
        topic=topic, difficulty=difficulty, context=combined_context[:4000]
    )
    messages = [{"role": "user", "content": prompt}]
    plan_data = llm_call_with_retry(
        ollama, config, messages, temperature=0.5,
        max_retries=2, parse_json_response=True, label="exam_plan",
    )

    if not plan_data or "sections" not in plan_data or not plan_data["sections"]:
        yield {"type": "error",
               "message": "Failed to plan exam structure." if lang == "en" else "无法规划试卷结构。"}
        return

    planned_sections = plan_data["sections"]
    total_points = plan_data.get("total_points", 100)
    duration_minutes = plan_data.get("duration_minutes", 60)

    yield {"type": "plan", "data": {
        "sections": planned_sections,
        "total_points": total_points,
        "duration_minutes": duration_minutes,
    }}
    print(f"[Exam] Planned {len(planned_sections)} sections, {total_points} points, {duration_minutes} min", file=sys.stderr)

    # =========================================================================
    # Phase 2: Generating - Generate questions per section
    # =========================================================================
    yield {"type": "phase", "phase": "generating",
           "message": "Generating questions..." if lang == "en" else "正在生成题目..."}

    exam_sections: List[ExamSection] = []
    all_questions_text = ""  # For answer key generation
    q_counter = 0

    for sec_idx, sec_plan in enumerate(planned_sections):
        if ollama.is_stopped():
            yield {"type": "status",
                   "message": "Generation stopped." if lang == "en" else "生成已停止。"}
            break

        sec_type = sec_plan.get("type", "choice")
        sec_title = sec_plan.get("title", f"Part {sec_idx + 1}")
        sec_count = min(int(sec_plan.get("count", 5)), 15)
        points_each = int(sec_plan.get("points_each", 2))
        sec_instruction = sec_plan.get("instruction", "")

        yield {"type": "status",
               "message": f"Generating {sec_type} questions ({sec_idx+1}/{len(planned_sections)})..." if lang == "en"
               else f"正在生成{sec_type}题目（{sec_idx+1}/{len(planned_sections)}）..."}

        # RAG retrieval for section
        section_context, _ = retrieve_context(
            f"{topic} {sec_instruction}", kb_names, ollama, chroma, config, max_chars=2000
        )

        # Web search enrichment
        if web_available and web_searcher:
            try:
                web_results = web_searcher.search(f"{topic} {sec_instruction}", num_results=2)
                if web_results:
                    web_ctx = "\n".join(
                        f"\n[Web: {r.get('title', '')}]\n{r.get('snippet', '')}"
                        for r in web_results
                    )
                    section_context = (section_context or "") + "\n" + web_ctx
            except Exception:
                pass

        # LLM: generate questions for this section
        prompt = get_prompt("exam_generate_section", lang).format(
            question_type=sec_type,
            count=sec_count,
            points_each=points_each,
            difficulty=difficulty,
            instruction=sec_instruction,
            context=section_context if section_context else "No additional context available.",
        )
        messages = [{"role": "user", "content": prompt}]
        questions_data = llm_call_with_retry(
            ollama, config, messages, temperature=0.7,
            max_retries=2, parse_json_response=True, label=f"exam_section_{sec_idx}",
        )

        exam_questions: List[ExamQuestion] = []
        if questions_data and "questions" in questions_data:
            for q in questions_data["questions"][:sec_count]:
                q_counter += 1
                eq = ExamQuestion(
                    question_id=f"q_{q_counter}",
                    question_type=sec_type,
                    question_text=q.get("question_text", ""),
                    options=q.get("options", {}),
                    correct_answer=q.get("correct_answer", ""),
                    explanation=q.get("explanation", ""),
                    knowledge_point=q.get("knowledge_point", ""),
                    points=points_each,
                    bloom_level=q.get("bloom_level", ""),
                )
                exam_questions.append(eq)

        sec_total = len(exam_questions) * points_each
        exam_section = ExamSection(
            section_id=f"sec_{sec_idx}",
            section_type=sec_type,
            title=sec_title,
            instructions=sec_instruction,
            questions=exam_questions,
            total_points=sec_total,
        )
        exam_sections.append(exam_section)

        # Build text for answer key
        type_labels = {"choice": "Multiple Choice", "fill_blank": "Fill in the Blank",
                       "true_false": "True/False", "written": "Short Answer"}
        all_questions_text += f"\n### {sec_title} ({type_labels.get(sec_type, sec_type)}, {points_each} pts each)\n"
        for j, eq in enumerate(exam_questions):
            all_questions_text += f"\n{j+1}. {eq.question_text}\n"
            if eq.options:
                for k, v in eq.options.items():
                    all_questions_text += f"   {k}. {v}\n"
            all_questions_text += f"   Answer: {eq.correct_answer}\n"
            all_questions_text += f"   Explanation: {eq.explanation}\n"

        yield {"type": "section", "data": {
            "section_type": sec_type,
            "title": sec_title,
            "question_count": len(exam_questions),
            "total_points": sec_total,
        }}

    if not exam_sections:
        yield {"type": "error",
               "message": "No questions generated." if lang == "en" else "未生成任何题目。"}
        return

    actual_total = sum(s.total_points for s in exam_sections)

    # =========================================================================
    # Phase 3: Answer Key - Generate answer key
    # =========================================================================
    yield {"type": "phase", "phase": "answer_key",
           "message": "Generating answer key..." if lang == "en" else "正在生成答案..."}

    prompt = get_prompt("exam_answer_key", lang).format(exam_content=all_questions_text[:6000])
    messages = [{"role": "user", "content": prompt}]
    answer_key_text = ""

    for chunk in llm_stream_with_timeout(ollama, config, messages, temperature=0.3, timeout_seconds=120, label="exam_answer_key"):
        if ollama.is_stopped():
            break
        answer_key_text += chunk
        yield {"type": "content", "content": chunk, "section": "answer_key", "done": False}

    yield {"type": "content", "content": "", "section": "answer_key", "done": True}

    # =========================================================================
    # Phase 4: Formatting - Format exam paper
    # =========================================================================
    yield {"type": "phase", "phase": "formatting",
           "message": "Formatting exam paper..." if lang == "en" else "正在格式化试卷..."}

    # Build sections summary for header
    sections_summary = ", ".join(
        f"{s.title} ({s.total_points} pts)" for s in exam_sections
    )

    prompt = get_prompt("exam_format_header", lang).format(
        topic=topic,
        total_points=actual_total,
        duration_minutes=duration_minutes,
        sections_summary=sections_summary,
    )
    messages = [{"role": "user", "content": prompt}]
    paper_text = ""

    for chunk in llm_stream_with_timeout(ollama, config, messages, temperature=0.3, timeout_seconds=60, label="exam_format_header"):
        if ollama.is_stopped():
            break
        paper_text += chunk
        yield {"type": "content", "content": chunk, "section": "paper", "done": False}

    # Append question sections to paper
    paper_text += "\n\n---\n\n"
    type_labels_zh = {"choice": "选择题", "fill_blank": "填空题",
                      "true_false": "判断题", "written": "简答题"}
    type_labels_en = {"choice": "Multiple Choice", "fill_blank": "Fill in the Blank",
                      "true_false": "True/False", "written": "Short Answer"}
    type_labels = type_labels_zh if lang == "zh" else type_labels_en

    for sec in exam_sections:
        sec_header = f"\n## {sec.title} ({type_labels.get(sec.section_type, sec.section_type)}, {sec.total_points} pts)\n\n"
        paper_text += sec_header
        yield {"type": "content", "content": sec_header, "section": "paper", "done": False}

        for j, q in enumerate(sec.questions):
            q_text = f"**{j+1}.** ({q.points} pts) {q.question_text}\n"
            if q.options:
                for k, v in q.options.items():
                    q_text += f"   {k}. {v}\n"
            q_text += "\n"
            paper_text += q_text
            yield {"type": "content", "content": q_text, "section": "paper", "done": False}

    yield {"type": "content", "content": "", "section": "paper", "done": True}

    # Save
    paper = ExamPaper(
        paper_id=paper_id,
        topic=topic,
        kb_names=kb_names,
        difficulty=difficulty,
        created_at=datetime.now().isoformat(),
        sections=exam_sections,
        answer_key_markdown=answer_key_text,
        paper_markdown=paper_text,
        total_points=actual_total,
        duration_minutes=duration_minutes,
    )
    paper.save(save_dir)
    print(f"[Exam] Saved exam {paper_id} with {sum(len(s.questions) for s in exam_sections)} questions, {actual_total} points", file=sys.stderr)

    yield {"type": "done", "paper_id": paper_id}


def list_exams(save_dir: Path) -> List[Dict]:
    """List all saved exam papers."""
    exams = []
    if not save_dir.exists():
        return exams
    for f in sorted(save_dir.glob("exam_*.json"), reverse=True):
        try:
            paper = ExamPaper.load(f)
            exams.append({
                "paper_id": paper.paper_id,
                "topic": paper.topic,
                "difficulty": paper.difficulty,
                "total_points": paper.total_points,
                "duration_minutes": paper.duration_minutes,
                "section_count": len(paper.sections),
                "question_count": sum(len(s.questions) for s in paper.sections),
                "created_at": paper.created_at,
            })
        except Exception:
            continue
    return exams
