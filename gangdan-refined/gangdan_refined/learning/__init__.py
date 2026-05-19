"""Learning module for GangDan Refined.

Self-contained module providing:
- Question generation (MCQ, short answer, essay)
- Guided learning sessions
- Exam generation
- Deep research reports
- Lecture/presentation generation

All functions accept LLM/vector DB clients as parameters (no global state).
"""

from .models import (
    GeneratedQuestion,
    QuestionBatch,
    KnowledgePoint,
    LearningSession,
    ExamQuestion,
    ExamSection,
    ExamPaper,
    ResearchSubtopic,
    ResearchReport,
    Citation,
    LectureSection,
    LectureDocument,
    generate_id,
)
from .question_gen import generate_questions
from .guided import create_session, generate_lesson, chat_in_session, next_point, generate_summary
from .exam import generate_exam
from .research import run_research, list_reports
from .lecture import generate_lecture

__all__ = [
    "GeneratedQuestion",
    "QuestionBatch",
    "KnowledgePoint",
    "LearningSession",
    "ExamQuestion",
    "ExamSection",
    "ExamPaper",
    "ResearchSubtopic",
    "ResearchReport",
    "Citation",
    "LectureSection",
    "LectureDocument",
    "generate_id",
    "generate_questions",
    "create_session",
    "generate_lesson",
    "chat_in_session",
    "next_point",
    "generate_summary",
    "generate_exam",
    "run_research",
    "list_reports",
    "generate_lecture",
]