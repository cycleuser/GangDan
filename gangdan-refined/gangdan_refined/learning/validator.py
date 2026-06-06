"""Output validation and quality assurance for learning module outputs.

Validates research reports, question batches, and exam papers for
structural integrity, content quality, and format correctness.
When validation fails, generates repair prompts for auto-correction.

Design inspired by smallcode's validate-and-repair pattern.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Minimum thresholds
MIN_SECTION_COUNT = 2
MIN_CITATION_COUNT = 1
MIN_QUESTION_COUNT = 3
MIN_SECTION_LENGTH = 100  # chars
MIN_ANSWER_LENGTH = 1
MAX_DUPLICATE_SIMILARITY = 0.85  # Jaccard threshold for dedup


def validate_research_report(report: dict) -> Dict[str, Any]:
    """Validate a research report for quality issues.

    Parameters
    ----------
    report : dict
        Research report object (from ResearchReport).

    Returns
    -------
    dict
        Validation result with keys:
        - valid (bool): Whether the report passes validation
        - issues (List[str]): Specific issues found
        - scores (dict): Dimension scores (0.0-1.0)
        - repair_hints (List[str]): Suggestions for LLM repair
    """
    issues: List[str] = []
    repair_hints: List[str] = []
    scores: Dict[str, float] = {
        "structure": 1.0,
        "content_depth": 1.0,
        "citation_completeness": 1.0,
        "format": 1.0,
    }

    report_text = report.get("report_markdown", "")
    subtopics = report.get("subtopics", [])
    citations = report.get("citations", [])
    topic = report.get("topic", "")

    # --- Structure check ---
    if not report_text or len(report_text) < 200:
        issues.append("Report text is too short or empty (< 200 chars)")
        scores["structure"] = 0.0
        repair_hints.append("Generate a complete report with at least 3 sections")

    section_count = report_text.count("\n## ")
    if section_count < MIN_SECTION_COUNT:
        issues.append(f"Too few sections: {section_count} (minimum {MIN_SECTION_COUNT})")
        scores["structure"] = min(scores["structure"], 0.5)
        repair_hints.append(f"Add more sections. Include Introduction, at least {MIN_SECTION_COUNT - section_count} body sections, and a Conclusion")

    # --- Content depth check ---
    if subtopics:
        completed = [st for st in subtopics if st.get("status") in ("COMPLETED", "completed")]
        if len(completed) < 2:
            issues.append(f"Only {len(completed)} subtopics completed")
            scores["content_depth"] = 0.3
            repair_hints.append("Research more subtopics. Each should have at least 200 chars of notes")

        weak_notes = [st for st in subtopics if len(st.get("notes") or "") < MIN_SECTION_LENGTH]
        if weak_notes:
            names = [st.get("title", "unknown") for st in weak_notes[:3]]
            issues.append(f"Shallow notes in subtopics: {names}")
            scores["content_depth"] = min(scores["content_depth"], 0.5)
            repair_hints.append(f"Deepen analysis for: {', '.join(names)}")

    # --- Citation completeness check ---
    if not citations or len(citations) < MIN_CITATION_COUNT:
        issues.append("No citations in report")
        scores["citation_completeness"] = 0.0
        repair_hints.append("Add citations. Every factual claim should reference a source from the knowledge base")

    # Check citation matching: are [N] references actually listed?
    import re
    cited_nums = set(int(m) for m in re.findall(r"\[(\d+)\]", report_text))
    citation_nums = set()
    for c in citations:
        cid = c.get("citation_id", "")
        num_match = re.search(r"\[?(\d+)\]?", cid)
        if num_match:
            citation_nums.add(int(num_match.group(1)))

    orphaned = cited_nums - citation_nums
    if orphaned:
        issues.append(f"Orphaned citations (referenced but not defined): {sorted(orphaned)}")
        scores["citation_completeness"] = min(scores["citation_completeness"], 0.6)
        repair_hints.append(f"Define or remove citations: {sorted(orphaned)}")

    unused = citation_nums - cited_nums
    if unused and len(citation_nums) > 0:
        issues.append(f"Unused citations (defined but not referenced): {sorted(unused)}")
        scores["citation_completeness"] = min(scores["citation_completeness"], 0.7)
        repair_hints.append(f"Reference or remove citations: {sorted(unused)}")

    # --- Format check ---
    if report_text:
        # Check for broken markdown
        if report_text.count("```") % 2 != 0:
            issues.append("Unclosed code block")
            scores["format"] = 0.8
            repair_hints.append("Close all ``` code blocks")

        # Check heading hierarchy
        if topic and f"# {topic}" not in report_text and f"# " not in report_text:
            issues.append("Missing level-1 heading with topic")
            scores["format"] = 0.9
            repair_hints.append(f"Add '# {topic}' as the first heading")

    # --- Overall assessment ---
    overall_score = sum(scores.values()) / max(len(scores), 1)
    valid = len(issues) == 0

    return {
        "valid": valid,
        "issues": issues,
        "scores": scores,
        "overall_score": round(overall_score, 2),
        "repair_hints": repair_hints,
    }


def validate_question_batch(questions: List[dict], difficulty: str = "medium") -> Dict[str, Any]:
    """Validate a batch of generated questions.

    Parameters
    ----------
    questions : List[dict]
        List of GeneratedQuestion objects as dicts.
    difficulty : str
        Intended difficulty level.

    Returns
    -------
    dict
        Validation result.
    """
    issues: List[str] = []
    repair_hints: List[str] = []
    scores = {
        "count": 1.0,
        "type_diversity": 1.0,
        "bloom_distribution": 1.0,
        "dedup": 1.0,
        "format": 1.0,
    }

    if not questions or len(questions) < MIN_QUESTION_COUNT:
        issues.append(f"Too few questions: {len(questions)} (minimum {MIN_QUESTION_COUNT})")
        scores["count"] = 0.3
        repair_hints.append(f"Generate at least {MIN_QUESTION_COUNT} questions")
        return _build_result(issues, repair_hints, scores)

    # Type diversity check
    types = [q.get("question_type", "") for q in questions]
    unique_types = set(types)
    if len(unique_types) < 2 and len(questions) >= 3:
        issues.append(f"Low type diversity: only {unique_types}")
        scores["type_diversity"] = 0.5
        repair_hints.append("Vary question types (choice, fill_blank, written, true_false)")

    # Bloom taxonomy distribution
    bloom_levels = [q.get("bloom_level", "") for q in questions]
    unique_bloom = set(bloom_levels)
    if len(unique_bloom) < 2 and len(questions) >= 3:
        issues.append(f"Low Bloom level diversity: only {unique_bloom}")
        scores["bloom_distribution"] = 0.5
        repair_hints.append("Use multiple Bloom levels (remember, understand, apply, analyze, evaluate)")

    # Dedup check via Jaccard similarity
    texts = [q.get("question_text", "") for q in questions]
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            if texts[i] and texts[j]:
                sim = _jaccard_similarity(texts[i], texts[j])
                if sim > MAX_DUPLICATE_SIMILARITY:
                    issues.append(f"Near-duplicate questions at indices {i} and {j} (similarity: {sim:.2f})")
                    scores["dedup"] = 0.7
                    repair_hints.append(f"Replace or rewrite duplicate question at index {j}")
                    break

    # Format check: each question should have answer and explanation
    for i, q in enumerate(questions):
        if not q.get("correct_answer"):
            issues.append(f"Question {i}: missing correct_answer")
            scores["format"] = min(scores["format"], 0.7)
            repair_hints.append(f"Add correct_answer for question {i}")

        if not q.get("knowledge_point"):
            issues.append(f"Question {i}: missing knowledge_point")
            scores["format"] = min(scores["format"], 0.8)

    return _build_result(issues, repair_hints, scores)


def validate_exam_paper(exam: dict) -> Dict[str, Any]:
    """Validate an exam paper for structural completeness.

    Parameters
    ----------
    exam : dict
        ExamPaper object as dict.

    Returns
    -------
    dict
        Validation result.
    """
    issues: List[str] = []
    repair_hints: List[str] = []
    scores = {"structure": 1.0, "question_quality": 1.0, "answer_key": 1.0, "format": 1.0}

    sections = exam.get("sections", [])
    if not sections:
        issues.append("No sections in exam paper")
        scores["structure"] = 0.0
        repair_hints.append("Add at least one section with questions")
        return _build_result(issues, repair_hints, scores)

    total_questions = sum(len(s.get("questions", [])) for s in sections)
    if total_questions < MIN_QUESTION_COUNT:
        issues.append(f"Too few questions: {total_questions}")
        scores["question_quality"] = 0.3
        repair_hints.append(f"Add more questions (minimum {MIN_QUESTION_COUNT})")

    # Section-level checks
    for i, section in enumerate(sections):
        if not section.get("title"):
            issues.append(f"Section {i}: missing title")
            scores["structure"] = min(scores["structure"], 0.7)
        if not section.get("instructions"):
            repair_hints.append(f"Add instructions for section {i}")

    # Answer key check
    if not exam.get("answer_key_markdown"):
        issues.append("Missing answer key")
        scores["answer_key"] = 0.0
        repair_hints.append("Generate an answer key with correct answers and explanations")

    # Total points check
    total_points = exam.get("total_points", 0)
    if total_points == 0:
        issues.append("Total points is 0")
        scores["format"] = 0.5
        repair_hints.append("Assign point values to each question and calculate total_points")

    # Duration check
    if not exam.get("duration_minutes") or exam.get("duration_minutes", 0) <= 0:
        issues.append("Missing or invalid exam duration")
        scores["format"] = min(scores["format"], 0.8)
        repair_hints.append("Set a reasonable duration_minutes (e.g., 60)")

    return _build_result(issues, repair_hints, scores)


def build_repair_prompt(original_prompt: str, issues: List[str], repair_hints: List[str]) -> str:
    """Build a repair prompt that instructs the LLM to fix specific issues.

    Parameters
    ----------
    original_prompt : str
        The original generation prompt.
    issues : List[str]
        Specific issues found by validation.
    repair_hints : List[str]
        Suggestions for fixing the issues.

    Returns
    -------
    str
        A combined repair prompt.
    """
    if not issues:
        return original_prompt

    issues_text = "\n".join(f"- {i}" for i in issues)
    hints_text = "\n".join(f"- {h}" for h in repair_hints)

    return (
        f"{original_prompt}\n\n"
        f"## QUALITY ISSUES DETECTED\n\n"
        f"The previous output had these problems:\n{issues_text}\n\n"
        f"Please regenerate, addressing ALL issues above:\n{hints_text}\n\n"
        f"Return ONLY valid JSON. Ensure all required fields are present and correct."
    )


def _jaccard_similarity(text1: str, text2: str) -> float:
    """Compute Jaccard similarity between two texts."""
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union)


def _build_result(
    issues: List[str],
    repair_hints: List[str],
    scores: Dict[str, float],
) -> Dict[str, Any]:
    """Build a validation result dict."""
    overall = sum(scores.values()) / max(len(scores), 1)
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "scores": scores,
        "overall_score": round(overall, 2),
        "repair_hints": repair_hints,
    }
