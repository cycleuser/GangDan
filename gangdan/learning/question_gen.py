"""Question generation pipeline for the learning module."""

import sys
from typing import Iterator, Dict, List

from gangdan.learning.models import GeneratedQuestion, QuestionBatch, generate_id
from gangdan.learning.prompts import get_prompt
from gangdan.learning.rag_helper import retrieve_context
from gangdan.learning.utils import parse_json, llm_call_with_retry, validate_question, jaccard_word_similarity

# Bloom's taxonomy mapping: difficulty -> preferred cognitive levels
BLOOM_DIFFICULTY_MAP = {
    "easy": ["remember", "understand"],
    "medium": ["apply", "analyze"],
    "hard": ["evaluate", "create"],
}
BLOOM_DEFAULT = "understand"


def generate_questions(
    kb_names: List[str],
    topic: str,
    num_questions: int,
    question_type: str,
    difficulty: str,
    ollama,
    chroma,
    config,
    save_dir=None,
    web_search: bool = False,
) -> Iterator[Dict]:
    """Generate questions from KB content. Yields SSE-compatible dicts.

    Yields:
        {"type": "status", "message": "..."} - progress updates
        {"type": "question", "data": {...}}   - generated questions
        {"type": "done", "batch_id": "..."}   - completion
        {"type": "error", "message": "..."}   - errors
    """
    lang = config.language if config.language in ("zh", "en") else "en"
    batch_id = generate_id("qbatch_")

    # Step 1: Retrieve context from KB
    yield {"type": "status", "message": "Retrieving knowledge base content..." if lang == "en" else "正在检索知识库内容..."}

    context, sources = retrieve_context(topic, kb_names, ollama, chroma, config, max_chars=2500)
    if not context:
        yield {"type": "error", "message": "No relevant content found in knowledge base." if lang == "en" else "知识库中未找到相关内容。"}
        return

    print(f"[QuestionGen] Retrieved context: {len(context)} chars, {len(sources)} sources", file=sys.stderr)

    # Step 1.5: Web search enrichment (canary test + context merge)
    if web_search:
        try:
            from gangdan.core.web_searcher import WebSearcher
            web_searcher = WebSearcher()
            canary_results = web_searcher.search(topic, num_results=1)
            if canary_results:
                yield {"type": "status",
                       "message": "Web search available, enriching context..." if lang == "en"
                       else "网络搜索可用，正在丰富上下文..."}
                web_results = web_searcher.search(topic, num_results=3)
                if web_results:
                    web_context = "\n".join(
                        f"\n[Web: {r.get('title', '')}]\n{r.get('snippet', '')}"
                        for r in web_results
                    )
                    context += "\n" + web_context
                    print(f"[QuestionGen] Web search added {len(web_context)} chars", file=sys.stderr)
            else:
                yield {"type": "status",
                       "message": "Web search returned no results, using KB only" if lang == "en"
                       else "网络搜索无结果，仅使用知识库"}
        except Exception as e:
            print(f"[QuestionGen] Web search canary failed: {e}", file=sys.stderr)
            yield {"type": "status",
                   "message": "Web search unavailable, using KB only" if lang == "en"
                   else "网络搜索不可用，仅使用知识库"}

    # Step 2: Plan question focuses with Bloom's taxonomy
    yield {"type": "status", "message": "Planning question angles..." if lang == "en" else "正在规划出题角度..."}

    focuses_with_bloom = _plan_focuses_v2(topic, context, num_questions, question_type, difficulty, lang, ollama, config)
    if not focuses_with_bloom:
        # Fallback to simple planning
        focuses_simple = _plan_focuses(topic, context, num_questions, question_type, lang, ollama, config)
        if focuses_simple:
            preferred = BLOOM_DIFFICULTY_MAP.get(difficulty, [BLOOM_DEFAULT])
            focuses_with_bloom = [{"angle": f, "bloom_level": preferred[i % len(preferred)]} for i, f in enumerate(focuses_simple)]
        else:
            focuses_with_bloom = [{"angle": f"Aspect {i+1} of {topic}", "bloom_level": BLOOM_DEFAULT} for i in range(num_questions)]

    # Diversity check: remove duplicate angles using Jaccard similarity
    focuses_with_bloom = _deduplicate_focuses(focuses_with_bloom, topic, lang, ollama, config)

    print(f"[QuestionGen] Planned {len(focuses_with_bloom)} focuses with Bloom's levels", file=sys.stderr)

    # Step 3: Generate questions
    questions = []
    for i, focus_info in enumerate(focuses_with_bloom[:num_questions]):
        if ollama.is_stopped():
            yield {"type": "status", "message": "Generation stopped." if lang == "en" else "生成已停止。"}
            break

        focus = focus_info.get("angle", focus_info) if isinstance(focus_info, dict) else str(focus_info)
        bloom = focus_info.get("bloom_level", BLOOM_DEFAULT) if isinstance(focus_info, dict) else BLOOM_DEFAULT

        yield {
            "type": "status",
            "message": f"Generating question {i+1}/{num_questions}..." if lang == "en" else f"正在生成第 {i+1}/{num_questions} 题...",
        }

        question = _generate_single_question(
            focus, context, question_type, difficulty, bloom, lang, ollama, config, f"q_{i+1}"
        )
        if question:
            questions.append(question)
            yield {"type": "question", "data": {
                "question_id": question.question_id,
                "question_type": question.question_type,
                "question_text": question.question_text,
                "options": question.options,
                "correct_answer": question.correct_answer,
                "explanation": question.explanation,
                "knowledge_point": question.knowledge_point,
                "bloom_level": question.bloom_level,
            }}

    # Save batch
    if questions and save_dir:
        from datetime import datetime
        batch = QuestionBatch(
            batch_id=batch_id,
            kb_names=kb_names,
            topic=topic,
            difficulty=difficulty,
            question_type=question_type,
            created_at=datetime.now().isoformat(),
            questions=questions,
        )
        batch.save(save_dir)
        print(f"[QuestionGen] Saved batch {batch_id} with {len(questions)} questions", file=sys.stderr)

    yield {"type": "done", "batch_id": batch_id, "count": len(questions)}


def _plan_focuses(topic, context, num_questions, question_type, lang, ollama, config) -> List[str]:
    """Use LLM to plan different question focus angles (simple, no Bloom's)."""
    prompt_template = get_prompt("question_plan", lang)
    prompt = prompt_template.format(
        topic=topic,
        num_questions=num_questions,
        question_type=question_type,
        context=context[:2000],
    )

    messages = [{"role": "user", "content": prompt}]
    data = llm_call_with_retry(
        ollama, config, messages, temperature=0.5,
        max_retries=2, parse_json_response=True, label="question_plan",
    )
    if data and "focuses" in data:
        return data["focuses"][:num_questions]
    return []


def _plan_focuses_v2(topic, context, num_questions, question_type, difficulty, lang, ollama, config) -> List[Dict]:
    """Plan question focuses with Bloom's taxonomy cognitive levels.

    Returns list of {"angle": "...", "bloom_level": "..."} dicts.
    """
    prompt_template = get_prompt("question_plan_v2", lang)
    prompt = prompt_template.format(
        topic=topic,
        num_questions=num_questions,
        question_type=question_type,
        difficulty=difficulty,
        context=context[:2000],
    )

    messages = [{"role": "user", "content": prompt}]
    data = llm_call_with_retry(
        ollama, config, messages, temperature=0.5,
        max_retries=2, parse_json_response=True, label="question_plan_v2",
    )

    if data and "focuses" in data and isinstance(data["focuses"], list):
        results = []
        preferred_blooms = BLOOM_DIFFICULTY_MAP.get(difficulty, [BLOOM_DEFAULT])
        for i, f in enumerate(data["focuses"][:num_questions]):
            if isinstance(f, dict) and "angle" in f:
                bloom = f.get("bloom_level", preferred_blooms[i % len(preferred_blooms)])
                results.append({"angle": f["angle"], "bloom_level": bloom})
            elif isinstance(f, str):
                results.append({"angle": f, "bloom_level": preferred_blooms[i % len(preferred_blooms)]})
        return results
    return []


def _deduplicate_focuses(focuses: List[Dict], topic: str, lang: str, ollama, config) -> List[Dict]:
    """Remove duplicate angles using Jaccard word-token similarity.

    If any pair shares >70% tokens, the duplicate is dropped.
    """
    if len(focuses) <= 1:
        return focuses

    unique = [focuses[0]]
    for f in focuses[1:]:
        angle = f.get("angle", "") if isinstance(f, dict) else str(f)
        is_dup = False
        for u in unique:
            u_angle = u.get("angle", "") if isinstance(u, dict) else str(u)
            if jaccard_word_similarity(angle, u_angle) > 0.7:
                is_dup = True
                print(f"[QuestionGen] Duplicate focus dropped: '{angle}' too similar to '{u_angle}'", file=sys.stderr)
                break
        if not is_dup:
            unique.append(f)

    return unique


def _generate_single_question(focus, context, question_type, difficulty, bloom_level, lang, ollama, config, qid) -> GeneratedQuestion:
    """Generate a single question via LLM with quality gate validation.

    If the first attempt produces invalid output (e.g., missing fields for
    choice questions), retries once with a more explicit prompt.
    """
    prompt_key = {
        "choice": "question_generate_choice",
        "written": "question_generate_written",
        "fill_blank": "question_generate_fill_blank",
        "true_false": "question_generate_true_false",
    }.get(question_type, "question_generate_written")

    prompt_template = get_prompt(prompt_key, lang)
    prompt = prompt_template.format(
        focus=focus,
        context=context[:2000],
        difficulty=difficulty,
    )

    # Add Bloom's level instruction
    bloom_hint = f"\nCognitive level: {bloom_level}. " if bloom_level else ""
    if bloom_hint:
        prompt += bloom_hint

    messages = [{"role": "user", "content": prompt}]

    # Difficulty to numeric score mapping
    difficulty_scores = {"easy": 1, "medium": 3, "hard": 5}
    d_score = difficulty_scores.get(difficulty, 2)

    # Attempt with quality gate: generate -> validate -> retry if invalid
    for attempt in range(2):
        data = llm_call_with_retry(
            ollama, config, messages, temperature=0.7,
            max_retries=1 if attempt == 0 else 0,
            parse_json_response=True, label=f"question_generate_{qid}",
        )
        if not data:
            if attempt == 0:
                continue
            print(f"[QuestionGen] Failed to parse JSON for question {qid}", file=sys.stderr)
            return None

        # Quality gate: validate structure
        is_valid, reason = validate_question(data, question_type)
        if is_valid:
            return GeneratedQuestion(
                question_id=qid,
                question_type=question_type,
                question_text=data.get("question_text", ""),
                options=data.get("options", {}),
                correct_answer=data.get("correct_answer", ""),
                explanation=data.get("explanation", ""),
                knowledge_point=data.get("knowledge_point", ""),
                bloom_level=bloom_level or BLOOM_DEFAULT,
                difficulty_score=d_score,
            )

        # Invalid -- retry with explicit instruction on first failure
        if attempt == 0:
            print(f"[QuestionGen] Quality gate failed for {qid}: {reason}. Retrying.", file=sys.stderr)
            fix_hint = " Make sure to include ALL required fields with non-empty values."
            if question_type == "choice":
                fix_hint += " Include exactly 4 options (A, B, C, D) and set correct_answer to one of the option letters."
            messages = [{"role": "user", "content": prompt + fix_hint}]
        else:
            # Accept imperfect output on last attempt rather than returning nothing
            print(f"[QuestionGen] Quality gate still failed for {qid}: {reason}. Accepting anyway.", file=sys.stderr)
            return GeneratedQuestion(
                question_id=qid,
                question_type=question_type,
                question_text=data.get("question_text", ""),
                options=data.get("options", {}),
                correct_answer=data.get("correct_answer", ""),
                explanation=data.get("explanation", ""),
                knowledge_point=data.get("knowledge_point", ""),
                bloom_level=bloom_level or BLOOM_DEFAULT,
                difficulty_score=d_score,
            )

    return None


