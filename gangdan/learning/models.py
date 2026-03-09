"""Data models for the learning module."""

import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field, asdict


# =============================================================================
# Question Generator Models
# =============================================================================

@dataclass
class GeneratedQuestion:
    question_id: str
    question_type: str  # "choice", "fill_blank", "written", "true_false"
    question_text: str
    options: Dict[str, str] = field(default_factory=dict)  # MCQ: {"A": "...", ...}
    correct_answer: str = ""
    explanation: str = ""
    knowledge_point: str = ""
    bloom_level: str = ""  # remember/understand/apply/analyze/evaluate/create
    difficulty_score: int = 0  # 1-5 numeric difficulty


@dataclass
class QuestionBatch:
    batch_id: str
    kb_names: List[str]
    topic: str
    difficulty: str
    question_type: str
    created_at: str
    questions: List[GeneratedQuestion] = field(default_factory=list)

    def save(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        filepath = directory / f"{self.batch_id}.json"
        filepath.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, filepath: Path) -> "QuestionBatch":
        data = json.loads(filepath.read_text(encoding="utf-8"))
        questions = [GeneratedQuestion(**q) for q in data.pop("questions", [])]
        return cls(**data, questions=questions)


# =============================================================================
# Guided Learning Models
# =============================================================================

@dataclass
class KnowledgePoint:
    title: str
    description: str
    key_concepts: List[str] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)  # titles of prerequisite KPs


@dataclass
class LearningSession:
    session_id: str
    kb_names: List[str]
    created_at: str
    knowledge_points: List[KnowledgePoint] = field(default_factory=list)
    current_index: int = 0
    status: str = "initialized"  # "initialized", "learning", "completed"
    chat_histories: Dict[str, list] = field(default_factory=dict)  # str(index) -> messages
    lesson_contents: Dict[str, str] = field(default_factory=dict)  # str(index) -> markdown
    summary: str = ""
    quiz_results: Dict[str, dict] = field(default_factory=dict)  # str(index) -> {passed, score, attempts}
    consolidated_memories: Dict[str, str] = field(default_factory=dict)  # str(index) -> compressed summary
    analytics: Dict[str, Any] = field(default_factory=dict)  # {questions_asked, points_completed, ...}

    def save(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        filepath = directory / f"session_{self.session_id}.json"
        filepath.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, filepath: Path) -> "LearningSession":
        data = json.loads(filepath.read_text(encoding="utf-8"))
        kps = [KnowledgePoint(**kp) for kp in data.pop("knowledge_points", [])]
        return cls(**data, knowledge_points=kps)

    @property
    def current_point(self) -> Optional[KnowledgePoint]:
        if 0 <= self.current_index < len(self.knowledge_points):
            return self.knowledge_points[self.current_index]
        return None

    @property
    def progress_pct(self) -> int:
        if not self.knowledge_points:
            return 0
        return int((self.current_index / len(self.knowledge_points)) * 100)


# =============================================================================
# Deep Research Models
# =============================================================================

@dataclass
class ResearchSubtopic:
    title: str
    overview: str = ""
    notes: str = ""
    sources: List[str] = field(default_factory=list)
    status: str = "PENDING"  # PENDING -> RESEARCHING -> COMPLETED | FAILED | WEAK
    citation_id: str = ""  # unique citation reference e.g. "[1]"
    iteration: int = 0  # which iteration produced/expanded this subtopic


@dataclass
class Citation:
    """Structured citation for research reports."""
    citation_id: str  # e.g. "[1]"
    source_file: str
    collection_name: str
    excerpt: str = ""
    source_type: str = "kb"  # "kb" or "web"
    url: str = ""  # URL for web citations


@dataclass
class ResearchReport:
    report_id: str
    topic: str
    kb_names: List[str]
    depth: str  # "quick", "medium", "deep", "auto"
    created_at: str
    subtopics: List[ResearchSubtopic] = field(default_factory=list)
    citations: List[Citation] = field(default_factory=list)
    report_markdown: str = ""

    def save(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        # Save JSON metadata
        filepath = directory / f"{self.report_id}.json"
        filepath.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        # Save markdown report
        if self.report_markdown:
            md_path = directory / f"{self.report_id}.md"
            md_path.write_text(self.report_markdown, encoding="utf-8")

    @classmethod
    def load(cls, filepath: Path) -> "ResearchReport":
        data = json.loads(filepath.read_text(encoding="utf-8"))
        subtopics = [ResearchSubtopic(**s) for s in data.pop("subtopics", [])]
        citations = [Citation(**c) for c in data.pop("citations", [])]
        return cls(**data, subtopics=subtopics, citations=citations)


def generate_id(prefix: str = "") -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_uuid = uuid.uuid4().hex[:6]
    return f"{prefix}{ts}_{short_uuid}" if prefix else f"{ts}_{short_uuid}"


# =============================================================================
# Lecture & Handout Models
# =============================================================================

@dataclass
class LectureSection:
    section_id: str
    title: str
    content: str = ""  # markdown content
    source_notes: str = ""  # RAG notes used to write this section


@dataclass
class LectureDocument:
    lecture_id: str
    topic: str
    kb_names: List[str]
    created_at: str
    sections: List[LectureSection] = field(default_factory=list)
    summary: str = ""
    lecture_markdown: str = ""  # full assembled document

    def save(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        filepath = directory / f"{self.lecture_id}.json"
        filepath.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        if self.lecture_markdown:
            md_path = directory / f"{self.lecture_id}.md"
            md_path.write_text(self.lecture_markdown, encoding="utf-8")

    @classmethod
    def load(cls, filepath: Path) -> "LectureDocument":
        data = json.loads(filepath.read_text(encoding="utf-8"))
        sections = [LectureSection(**s) for s in data.pop("sections", [])]
        return cls(**data, sections=sections)


# =============================================================================
# Exam Paper Models
# =============================================================================

@dataclass
class ExamQuestion:
    question_id: str
    question_type: str  # "choice", "written", "fill_blank", "true_false"
    question_text: str
    options: Dict[str, str] = field(default_factory=dict)
    correct_answer: str = ""
    explanation: str = ""
    knowledge_point: str = ""
    points: int = 0
    bloom_level: str = ""


@dataclass
class ExamSection:
    section_id: str
    section_type: str  # "choice", "fill_blank", "true_false", "written"
    title: str
    instructions: str = ""
    questions: List[ExamQuestion] = field(default_factory=list)
    total_points: int = 0


@dataclass
class ExamPaper:
    paper_id: str
    topic: str
    kb_names: List[str]
    difficulty: str
    created_at: str
    sections: List[ExamSection] = field(default_factory=list)
    answer_key_markdown: str = ""
    paper_markdown: str = ""
    total_points: int = 0
    duration_minutes: int = 60

    def save(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        filepath = directory / f"{self.paper_id}.json"
        filepath.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        if self.paper_markdown:
            md_path = directory / f"{self.paper_id}_paper.md"
            md_path.write_text(self.paper_markdown, encoding="utf-8")
        if self.answer_key_markdown:
            ak_path = directory / f"{self.paper_id}_answers.md"
            ak_path.write_text(self.answer_key_markdown, encoding="utf-8")

    @classmethod
    def load(cls, filepath: Path) -> "ExamPaper":
        data = json.loads(filepath.read_text(encoding="utf-8"))
        sections = []
        for s in data.pop("sections", []):
            questions = [ExamQuestion(**q) for q in s.pop("questions", [])]
            sections.append(ExamSection(**s, questions=questions))
        return cls(**data, sections=sections)
