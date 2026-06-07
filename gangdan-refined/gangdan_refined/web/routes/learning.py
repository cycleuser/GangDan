"""Learning route blueprint.

Provides all /api/learning/* endpoints expected by the frontend JS.
"""

from __future__ import annotations

import json

from flask import Blueprint, request, jsonify, Response, stream_with_context

from ...core.config import CONFIG, CHROMA_DIR

learning_bp = Blueprint("learning", __name__)


# --- Questions ---

@learning_bp.route("/questions/generate", methods=["POST"])
def questions_generate():
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
        chroma = ChromaManager(persist_dir=str(CHROMA_DIR))

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
                    yield f"data: {json.dumps(event)}\n\n"
                yield 'data: {"type": "done"}\n\n'

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


@learning_bp.route("/questions/list", methods=["GET"])
def questions_list():
    try:
        from ...learning.question_gen import list_batches
        batches = list_batches()
        return jsonify({"success": True, "batches": batches})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@learning_bp.route("/questions/<batch_id>", methods=["GET"])
def questions_get(batch_id):
    try:
        from ...learning.question_gen import get_batch
        batch = get_batch(batch_id)
        if batch is None:
            return jsonify({"success": False, "error": "Batch not found"}), 404
        return jsonify({"success": True, "batch": batch})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@learning_bp.route("/questions/<batch_id>", methods=["DELETE"])
def questions_delete(batch_id):
    try:
        from ...learning.question_gen import delete_batch
        delete_batch(batch_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Guide ---

@learning_bp.route("/guide/create", methods=["POST"])
def guide_create():
    data = request.get_json(silent=True) or {}
    kb_names = data.get("kb_names", [])
    try:
        from ...llm.ollama import OllamaClient
        from ...storage.chroma_manager import ChromaManager
        ollama = OllamaClient(CONFIG.llm.ollama_url)
        chroma = ChromaManager(persist_dir=str(CHROMA_DIR))
        from ...learning.guided import create_session
        session = create_session(
            kb_names=kb_names,
            ollama=ollama,
            chroma=chroma,
            config=CONFIG,
            docs_dir=str(CONFIG.docs_dir) if hasattr(CONFIG, "docs_dir") else None,
        )
        return jsonify({"success": True, "session": session})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@learning_bp.route("/guide/start/<session_id>", methods=["POST"])
def guide_start(session_id):
    try:
        from ...learning.guided import start_lesson
        result = start_lesson(session_id)
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@learning_bp.route("/guide/next/<session_id>", methods=["POST"])
def guide_next(session_id):
    data = request.get_json(silent=True) or {}
    answer = data.get("answer", "")
    try:
        from ...learning.guided import next_step
        result = next_step(session_id, answer=answer)
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@learning_bp.route("/guide/chat/<session_id>", methods=["POST"])
def guide_chat(session_id):
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")
    try:
        from ...learning.guided import chat_in_session
        result = chat_in_session(session_id, message)
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@learning_bp.route("/guide/summary/<session_id>", methods=["GET"])
def guide_summary(session_id):
    try:
        from ...learning.guided import get_summary
        result = get_summary(session_id)
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@learning_bp.route("/guide/sessions", methods=["GET"])
def guide_sessions():
    try:
        from ...learning.guided import list_sessions
        from ...core.config import DATA_DIR
        from pathlib import Path
        sessions = list_sessions(save_dir=Path(DATA_DIR) / "learning" / "guide")
        return jsonify({"success": True, "sessions": sessions})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@learning_bp.route("/guide/session/<session_id>", methods=["GET"])
def guide_session(session_id):
    try:
        from ...learning.guided import get_session
        session = get_session(session_id)
        if session is None:
            return jsonify({"success": False, "error": "Session not found"}), 404
        return jsonify({"success": True, "session": session})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Exam ---

@learning_bp.route("/exam/generate", methods=["POST"])
def exam_generate():
    data = request.get_json(silent=True) or {}
    kb_names = data.get("kb_names", [])
    num_questions = data.get("num_questions", 10)
    question_types = data.get("question_types", ["mcq", "short_answer"])
    difficulty = data.get("difficulty", "mixed")
    try:
        from ...learning.exam import generate_exam
        exam = generate_exam(
            kb_names=kb_names,
            num_questions=num_questions,
            question_types=question_types,
            difficulty=difficulty,
            config=CONFIG,
        )
        return jsonify({"success": True, "exam": exam})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@learning_bp.route("/exam/list", methods=["GET"])
def exam_list():
    try:
        from ...learning.exam import list_exams
        from ...core.config import DATA_DIR
        from pathlib import Path
        exams = list_exams(save_dir=Path(DATA_DIR) / "learning" / "exam")
        return jsonify({"success": True, "exams": exams})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@learning_bp.route("/exam/<paper_id>", methods=["GET"])
def exam_get(paper_id):
    try:
        from ...learning.exam import get_exam
        exam = get_exam(paper_id)
        if exam is None:
            return jsonify({"success": False, "error": "Exam not found"}), 404
        return jsonify({"success": True, "exam": exam})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@learning_bp.route("/exam/<paper_id>", methods=["DELETE"])
def exam_delete(paper_id):
    try:
        from ...learning.exam import delete_exam
        delete_exam(paper_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Lecture ---

@learning_bp.route("/lecture/generate", methods=["POST"])
def lecture_generate():
    data = request.get_json(silent=True) or {}
    kb_names = data.get("kb_names", [])
    topic = data.get("topic", "")
    style = data.get("style", "academic")
    try:
        from ...learning.lecture import generate_lecture
        lecture = generate_lecture(kb_names=kb_names, topic=topic, style=style, config=CONFIG)
        return jsonify({"success": True, "lecture": lecture})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@learning_bp.route("/lecture/list", methods=["GET"])
def lecture_list():
    try:
        from ...learning.lecture import list_lectures
        from ...core.config import DATA_DIR
        from pathlib import Path
        lectures = list_lectures(save_dir=Path(DATA_DIR) / "learning" / "lecture")
        return jsonify({"success": True, "lectures": lectures})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@learning_bp.route("/lecture/<lecture_id>", methods=["GET"])
def lecture_get(lecture_id):
    try:
        from ...learning.lecture import get_lecture
        lecture = get_lecture(lecture_id)
        if lecture is None:
            return jsonify({"success": False, "error": "Lecture not found"}), 404
        return jsonify({"success": True, "lecture": lecture})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@learning_bp.route("/lecture/<lecture_id>", methods=["DELETE"])
def lecture_delete(lecture_id):
    try:
        from ...learning.lecture import delete_lecture
        delete_lecture(lecture_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Research (learning) ---

@learning_bp.route("/research/run", methods=["POST"])
def learning_research_run():
    data = request.get_json(silent=True) or {}
    topic = data.get("topic", "")
    kb_names = data.get("kb_names", [])
    depth = data.get("depth", "medium")
    output_size = data.get("output_size", "medium")
    web_search = data.get("web_search", False)
    fetch_sources = data.get("fetch_sources", False)
    skill = data.get("skill", "")

    if not topic:
        return jsonify({"success": False, "error": "Topic is required"}), 400

    try:
        from ...llm.ollama import OllamaClient
        from ...storage.chroma_manager import ChromaManager
        from pathlib import Path
        ollama = OllamaClient(CONFIG.llm.ollama_url)
        chroma = ChromaManager(persist_dir=str(CHROMA_DIR))
        from ...learning.research import run_research

        save_dir = Path(DATA_DIR) / "learning" / "research"
        save_dir.mkdir(parents=True, exist_ok=True)

        def gen():
            for event in run_research(
                topic=topic,
                kb_names=kb_names,
                depth=depth,
                ollama=ollama,
                chroma=chroma,
                config=CONFIG,
                save_dir=save_dir,
                web_search=web_search,
                output_size=output_size,
            ):
                yield f"data: {json.dumps(event)}\n\n"
            yield 'data: {"type": "done"}\n\n'

        return Response(gen(), mimetype="text/event-stream")
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@learning_bp.route("/research/reports", methods=["GET"])
def learning_research_reports():
    try:
        from ...learning.research import list_reports
        from ...core.config import DATA_DIR
        from pathlib import Path
        reports = list_reports(save_dir=Path(DATA_DIR) / "learning" / "research")
        return jsonify({"success": True, "reports": reports})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@learning_bp.route("/research/report/<report_id>", methods=["GET"])
def learning_research_report_get(report_id):
    try:
        from ...learning.research import get_report
        report = get_report(report_id)
        if report is None:
            return jsonify({"success": False, "error": "Report not found"}), 404
        return jsonify({"success": True, "report": report})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@learning_bp.route("/research/report/<report_id>", methods=["DELETE"])
def learning_research_report_delete(report_id):
    try:
        from ...learning.research import delete_report
        delete_report(report_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- KB List (for learning context) ---

@learning_bp.route("/kb/list", methods=["GET"])
def learning_kb_list():
    try:
        from ...storage.kb_manager import CustomKBManager
        mgr = CustomKBManager()
        kbs = mgr.list_kbs()
        return jsonify({"success": True, "kbs": [kb.to_dict() for kb in kbs]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500