"""Learn agent — question generation, guided study, exams, lectures."""

from __future__ import annotations

from .base import BaseAgent, AgentInput, AgentOutput, AgentMetadata


class LearnAgent(BaseAgent):
    name = "gd-learn"
    description = "Generate questions, exams, guided study, lectures from knowledge bases"
    version = "2.0.0"

    def run(self, input: AgentInput) -> AgentOutput:
        feature = input.options.get("feature", "question")

        try:
            if feature == "question":
                return self._generate_questions(input)
            elif feature == "guide":
                return self._create_guide(input)
            elif feature == "exam":
                return self._generate_exam(input)
            elif feature == "lecture":
                return self._generate_lecture(input)
            else:
                return self._generate_questions(input)
        except Exception as e:
            return AgentOutput(success=False, error=str(e), metadata=AgentMetadata(agent=self.name, version=self.version))

    def _generate_questions(self, input: AgentInput) -> AgentOutput:
        kb_names = input.options.get("kb_names", [])
        topic = input.query or input.text or ""
        num_questions = input.options.get("num_questions", 5)
        question_type = input.options.get("question_type", "mcq")
        difficulty = input.options.get("difficulty", "medium")

        if isinstance(kb_names, str):
            kb_names = [kb_names]

        try:
            from ..learning.question_gen import generate_questions
            from ..llm.factory import create_chat_client
            from ..llm.ollama import OllamaClient
            from ..storage.chroma_manager import ChromaManager
            from ..core.config import CHROMA_DIR

            chat_client = create_chat_client()
            ollama = OllamaClient(self.config.llm.ollama_url)
            chroma = ChromaManager(persist_dir=str(CHROMA_DIR))

            questions = []
            for event in generate_questions(kb_names=kb_names, topic=topic, num_questions=num_questions, question_type=question_type, difficulty=difficulty, chat_client=chat_client, ollama=ollama, chroma=chroma, config=self.config):
                if isinstance(event, dict) and event.get("type") == "question":
                    questions.append(event)

            return AgentOutput(
                success=True,
                data={"questions": questions, "topic": topic, "num_questions": len(questions), "question_type": question_type, "difficulty": difficulty},
                metadata=AgentMetadata(agent=self.name, version=self.version),
            )
        except Exception as e:
            return AgentOutput(success=False, error=str(e), metadata=AgentMetadata(agent=self.name, version=self.version))

    def _create_guide(self, input: AgentInput) -> AgentOutput:
        kb_names = input.options.get("kb_names", [])
        if isinstance(kb_names, str):
            kb_names = [kb_names]

        try:
            from ..learning.guided import create_session
            from ..llm.ollama import OllamaClient
            from ..storage.chroma_manager import ChromaManager
            from ..core.config import CHROMA_DIR

            ollama = OllamaClient(self.config.llm.ollama_url)
            chroma = ChromaManager(persist_dir=str(CHROMA_DIR))
            session = create_session(kb_names=kb_names, ollama=ollama, chroma=chroma, config=self.config, docs_dir=str(self.config.docs_dir))
            return AgentOutput(
                success=True,
                data={"session": session if isinstance(session, dict) else str(session)},
                metadata=AgentMetadata(agent=self.name, version=self.version),
            )
        except Exception as e:
            return AgentOutput(success=False, error=str(e), metadata=AgentMetadata(agent=self.name, version=self.version))

    def _generate_exam(self, input: AgentInput) -> AgentOutput:
        kb_names = input.options.get("kb_names", [])
        num_questions = input.options.get("num_questions", 10)
        difficulty = input.options.get("difficulty", "mixed")
        if isinstance(kb_names, str):
            kb_names = [kb_names]

        try:
            from ..learning.exam import generate_exam
            exam = generate_exam(kb_names=kb_names, num_questions=num_questions, difficulty=difficulty, config=self.config)
            return AgentOutput(
                success=True,
                data={"exam": exam if isinstance(exam, dict) else str(exam)},
                metadata=AgentMetadata(agent=self.name, version=self.version),
            )
        except Exception as e:
            return AgentOutput(success=False, error=str(e), metadata=AgentMetadata(agent=self.name, version=self.version))

    def _generate_lecture(self, input: AgentInput) -> AgentOutput:
        kb_names = input.options.get("kb_names", [])
        topic = input.query or input.text or ""
        style = input.options.get("style", "academic")
        if isinstance(kb_names, str):
            kb_names = [kb_names]

        try:
            from ..learning.lecture import generate_lecture
            lecture = generate_lecture(kb_names=kb_names, topic=topic, style=style, config=self.config)
            return AgentOutput(
                success=True,
                data={"lecture": lecture if isinstance(lecture, dict) else str(lecture)},
                metadata=AgentMetadata(agent=self.name, version=self.version),
            )
        except Exception as e:
            return AgentOutput(success=False, error=str(e), metadata=AgentMetadata(agent=self.name, version=self.version))

    def add_arguments(self, parser) -> None:
        self.add_common_args(parser)
        subparsers = parser.add_subparsers(dest="feature", help="Learning feature")
        q = subparsers.add_parser("question", help="Generate questions")
        q.add_argument("topic", nargs="?", default="", help="Topic")
        q.add_argument("--kb", "-k", nargs="+", default=[], help="Knowledge base(s)")
        q.add_argument("--num", type=int, default=5, help="Number of questions")
        q.add_argument("--type", "-t", default="mcq", choices=["mcq", "short_answer", "essay", "true_false"], help="Question type")
        q.add_argument("--difficulty", "-d", default="medium", choices=["easy", "medium", "hard"], help="Difficulty")
        q.add_argument("--json", action="store_true")
        g = subparsers.add_parser("guide", help="Guided learning session")
        g.add_argument("--kb", "-k", nargs="+", default=[], help="Knowledge base(s)")
        g.add_argument("--json", action="store_true")
        e = subparsers.add_parser("exam", help="Generate exam")
        e.add_argument("topic", nargs="?", default="", help="Topic")
        e.add_argument("--kb", "-k", nargs="+", default=[], help="Knowledge base(s)")
        e.add_argument("--num", type=int, default=10, help="Number of questions")
        e.add_argument("--difficulty", "-d", default="mixed", choices=["easy", "medium", "hard", "mixed"], help="Difficulty")
        e.add_argument("--json", action="store_true")
        l = subparsers.add_parser("lecture", help="Generate lecture")
        l.add_argument("topic", nargs="?", default="", help="Topic")
        l.add_argument("--kb", "-k", nargs="+", default=[], help="Knowledge base(s)")
        l.add_argument("--style", "-s", default="academic", choices=["academic", "casual", "presentation"], help="Lecture style")
        l.add_argument("--json", action="store_true")

    def build_input(self, args) -> AgentInput:
        feature = getattr(args, "feature", "question") or "question"
        opts = {"feature": feature}
        if feature == "question":
            opts.update({"kb_names": args.kb, "num_questions": args.num, "question_type": args.type, "difficulty": args.difficulty})
        elif feature == "guide":
            opts.update({"kb_names": args.kb})
        elif feature == "exam":
            opts.update({"kb_names": args.kb, "num_questions": args.num, "difficulty": args.difficulty})
        elif feature == "lecture":
            opts.update({"kb_names": args.kb, "style": args.style})
        return AgentInput(query=getattr(args, "topic", ""), options=opts, metadata=AgentMetadata(agent=self.name, version=self.version))