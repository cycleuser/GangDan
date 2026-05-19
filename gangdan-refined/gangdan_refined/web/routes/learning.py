"""Learning route blueprint."""

from __future__ import annotations

from flask import Blueprint, request, jsonify, Response, stream_with_context

from ...core.config import CONFIG

learning_bp = Blueprint("learning", __name__)


@learning_bp.route("/question", methods=["POST"])
def learning_question():
    """Generate questions from knowledge base content."""
    data = request.get_json(silent=True) or {}
    kb_names = data.get("kb_names", [])
    topic = data.get("topic", "")
    num_questions = data.get("num_questions", 5)
    question_type = data.get("question_type", "mcq")
    difficulty = data.get("difficulty", "medium")
    stream = data.get("stream", False)

    try:
        from ...llm.factory import create_chat_client
        from ...llm.ollama import OllamaClient
        from ...storage.chroma_manager import ChromaManager

        chat_client = create_chat_client()
        ollama = OllamaClient(CONFIG.llm.ollama_url)
        chroma = ChromaManager()

        if stream:
            from ...learning.question_gen import generate_questions

            def gen():
                for event in generate_questions(
                    kb_names=kb_names,
                    topic=topic,
                    num_questions=num_questions,
                    question_type=question_type,
                    difficulty=difficulty,
                    chat_client=chat_client,
                    ollama=ollama,
                    chroma=chroma,
                    config=CONFIG,
                ):
                    import json
                    yield f"data: {json.dumps(event)}\n\n"
                yield "data: {\"type\": \"done\"}\n\n"

            return Response(gen(), mimetype="text/event-stream")

        from ...learning.question_gen import generate_questions
        results = []
        for event in generate_questions(
            kb_names=kb_names,
            topic=topic,
            num_questions=num_questions,
            question_type=question_type,
            difficulty=difficulty,
            chat_client=chat_client,
            ollama=ollama,
            chroma=chroma,
            config=CONFIG,
        ):
            if event.get("type") == "question":
                results.append(event)

        return jsonify({"success": True, "questions": results})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@learning_bp.route("/guide/create", methods=["POST"])
def learning_guide_create():
    """Create a guided learning session."""
    data = request.get_json(silent=True) or {}
    kb_names = data.get("kb_names", [])

    try:
        from ...llm.ollama import OllamaClient
        from ...storage.chroma_manager import ChromaManager

        ollama = OllamaClient(CONFIG.llm.ollama_url)
        chroma = ChromaManager()

        from ...learning.guided import create_session
        session = create_session(
            kb_names=kb_names,
            ollama=ollama,
            chroma=chroma,
            config=CONFIG,
            docs_dir=CONFIG.docs_dir if hasattr(CONFIG, 'docs_dir') else None,
        )
        return jsonify({"success": True, "session": session})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@learning_bp.route("/research", methods=["POST"])
def learning_research():
    """Start a deep research session."""
    data = request.get_json(silent=True) or {}
    topic = data.get("topic", "")
    kb_names = data.get("kb_names", [])
    depth = data.get("depth", "medium")
    output_size = data.get("output_size", "medium")

    if not topic:
        return jsonify({"success": False, "error": "Topic is required"}), 400

    try:
        from ...llm.ollama import OllamaClient
        from ...storage.chroma_manager import ChromaManager

        ollama = OllamaClient(CONFIG.llm.ollama_url)
        chroma = ChromaManager()

        from ...learning.research import run_research

        def gen():
            import json
            for event in run_research(
                topic=topic,
                kb_names=kb_names,
                depth=depth,
                ollama=ollama,
                chroma=chroma,
                config=CONFIG,
            ):
                yield f"data: {json.dumps(event)}\n\n"
            yield "data: {\"type\": \"done\"}\n\n"

        return Response(gen(), mimetype="text/event-stream")

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500