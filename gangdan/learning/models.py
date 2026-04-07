"""Data models for the learning module."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class GeneratedQuestion:
    """A single generated question with metadata."""

    question_id: str
    question_type: str  # "choice", "fill_blank", "written", "true_false"
    question_text: str
    options: Dict[str, str] = field(default_factory=dict)
    correct_answer: str = ""
    explanation: str = ""
    knowledge_point: str = ""
    bloom_level: str = ""
    difficulty_score: int = 0


@dataclass
class QuestionBatch:
    """Batch of generated questions."""

    batch_id: str
    kb_names: List[str]
    topic: str
    difficulty: str
    question_type: str
    created_at: str
    questions: List[GeneratedQuestion] = field(default_factory=list)

    def save(self, directory: Path) -> None:
        """Save batch to JSON file."""
        directory.mkdir(parents=True, exist_ok=True)
        filepath = directory / f"{self.batch_id}.json"
        filepath.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, filepath: Path) -> QuestionBatch:
        """Load batch from JSON file."""
        data = json.loads(filepath.read_text(encoding="utf-8"))
        questions = [GeneratedQuestion(**q) for q in data.pop("questions", [])]
        return cls(**data, questions=questions)


@dataclass
class KnowledgePoint:
    """A single knowledge point for guided learning."""

    title: str
    description: str
    key_concepts: List[str] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)


@dataclass
class LearningSession:
    """Guided learning session with progress tracking."""

    session_id: str
    kb_names: List[str]
    created_at: str
    knowledge_points: List[KnowledgePoint] = field(default_factory=list)
    current_index: int = 0
    status: str = "initialized"
    chat_histories: Dict[str, list] = field(default_factory=dict)
    lesson_contents: Dict[str, str] = field(default_factory=dict)
    summary: str = ""
    quiz_results: Dict[str, dict] = field(default_factory=dict)
    consolidated_memories: Dict[str, str] = field(default_factory=dict)
    analytics: Dict[str, Any] = field(default_factory=dict)

    def save(self, directory: Path) -> None:
        """Save session to JSON file."""
        directory.mkdir(parents=True, exist_ok=True)
        filepath = directory / f"session_{self.session_id}.json"
        filepath.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, filepath: Path) -> LearningSession:
        """Load session from JSON file."""
        data = json.loads(filepath.read_text(encoding="utf-8"))
        kps = [KnowledgePoint(**kp) for kp in data.pop("knowledge_points", [])]
        return cls(**data, knowledge_points=kps)

    @property
    def current_point(self) -> Optional[KnowledgePoint]:
        """Get current knowledge point."""
        if 0 <= self.current_index < len(self.knowledge_points):
            return self.knowledge_points[self.current_index]
        return None

    @property
    def progress_pct(self) -> int:
        """Get progress percentage."""
        if not self.knowledge_points:
            return 0
        return int((self.current_index / len(self.knowledge_points)) * 100)


@dataclass
class Citation:
    """Structured citation for research reports."""

    citation_id: str
    source_file: str
    collection_name: str
    excerpt: str = ""
    source_type: str = "kb"
    url: str = ""


@dataclass
class ResearchSubtopic:
    """A subtopic in a research report."""

    title: str
    overview: str = ""
    notes: str = ""
    sources: List[str] = field(default_factory=list)
    status: str = "PENDING"
    citation_id: str = ""
    iteration: int = 0


@dataclass
class ResearchReport:
    """Multi-phase research report."""

    report_id: str
    topic: str
    kb_names: List[str]
    depth: str
    created_at: str
    subtopics: List[ResearchSubtopic] = field(default_factory=list)
    citations: List[Citation] = field(default_factory=list)
    report_markdown: str = ""

    def save(self, directory: Path) -> None:
        """Save report to JSON and Markdown files."""
        directory.mkdir(parents=True, exist_ok=True)

        filepath = directory / f"{self.report_id}.json"
        filepath.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        if self.report_markdown:
            md_path = directory / f"{self.report_id}.md"
            md_path.write_text(self.report_markdown, encoding="utf-8")

    @classmethod
    def load(cls, filepath: Path) -> ResearchReport:
        """Load report from JSON file."""
        data = json.loads(filepath.read_text(encoding="utf-8"))
        subtopics = [ResearchSubtopic(**s) for s in data.pop("subtopics", [])]
        citations = [Citation(**c) for c in data.pop("citations", [])]
        return cls(**data, subtopics=subtopics, citations=citations)


@dataclass
class LectureSection:
    """Section in a lecture document."""

    section_id: str
    title: str
    content: str = ""
    source_notes: str = ""


@dataclass
class LectureDocument:
    """Complete lecture document."""

    lecture_id: str
    topic: str
    kb_names: List[str]
    created_at: str
    sections: List[LectureSection] = field(default_factory=list)
    summary: str = ""
    lecture_markdown: str = ""

    def save(self, directory: Path) -> None:
        """Save lecture to JSON and Markdown files."""
        directory.mkdir(parents=True, exist_ok=True)

        filepath = directory / f"{self.lecture_id}.json"
        filepath.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        if self.lecture_markdown:
            md_path = directory / f"{self.lecture_id}.md"
            md_path.write_text(self.lecture_markdown, encoding="utf-8")

    @classmethod
    def load(cls, filepath: Path) -> LectureDocument:
        """Load lecture from JSON file."""
        data = json.loads(filepath.read_text(encoding="utf-8"))
        sections = [LectureSection(**s) for s in data.pop("sections", [])]
        return cls(**data, sections=sections)


@dataclass
class ExamQuestion:
    """Question in an exam paper."""

    question_id: str
    question_type: str
    question_text: str
    options: Dict[str, str] = field(default_factory=dict)
    correct_answer: str = ""
    explanation: str = ""
    knowledge_point: str = ""
    points: int = 0
    bloom_level: str = ""


@dataclass
class ExamSection:
    """Section in an exam paper."""

    section_id: str
    section_type: str
    title: str
    instructions: str = ""
    questions: List[ExamQuestion] = field(default_factory=list)
    total_points: int = 0


@dataclass
class ExamPaper:
    """Complete exam paper."""

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

    def save(self, directory: Path) -> None:
        """Save exam paper to JSON and Markdown files."""
        directory.mkdir(parents=True, exist_ok=True)

        filepath = directory / f"{self.paper_id}.json"
        filepath.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        if self.paper_markdown:
            md_path = directory / f"{self.paper_id}_paper.md"
            md_path.write_text(self.paper_markdown, encoding="utf-8")

        if self.answer_key_markdown:
            ak_path = directory / f"{self.paper_id}_answers.md"
            ak_path.write_text(self.answer_key_markdown, encoding="utf-8")

    @classmethod
    def load(cls, filepath: Path) -> ExamPaper:
        """Load exam paper from JSON file."""
        data = json.loads(filepath.read_text(encoding="utf-8"))
        sections = []
        for s in data.pop("sections", []):
            questions = [ExamQuestion(**q) for q in s.pop("questions", [])]
            sections.append(ExamSection(**s, questions=questions))
        return cls(**data, sections=sections)


def generate_id(prefix: str = "") -> str:
    """Generate a unique ID with timestamp and UUID."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_uuid = uuid.uuid4().hex[:6]
    return f"{prefix}{ts}_{short_uuid}" if prefix else f"{ts}_{short_uuid}"
