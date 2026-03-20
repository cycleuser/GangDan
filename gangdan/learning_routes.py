"""Flask Blueprint for learning module routes."""

import json
import sys
from pathlib import Path

from flask import Blueprint, request, jsonify, Response, stream_with_context

from gangdan.learning.utils import safe_sse_generator

learning_bp = Blueprint('learning', __name__)


def _get_app_globals():
    """Get global singletons from app module. Called at request time to avoid circular imports."""
    from gangdan.app import OLLAMA, CHROMA, CONFIG, DOCS_DIR, DATA_DIR, LANGUAGES, TRANSLATIONS, t
    return OLLAMA, CHROMA, CONFIG, DOCS_DIR, DATA_DIR, LANGUAGES, TRANSLATIONS, t


def _learning_dir(subdir: str) -> Path:
    """Get learning data subdirectory."""
    _, _, _, _, DATA_DIR, _, _, _ = _get_app_globals()
    d = DATA_DIR / "learning" / subdir
    d.mkdir(parents=True, exist_ok=True)
    return d


# =============================================================================
# Question Generator API
# =============================================================================

@learning_bp.route('/api/learning/questions/generate', methods=['POST'])
def api_generate_questions():
    OLLAMA, CHROMA, CONFIG, DOCS_DIR, DATA_DIR, LANGUAGES, TRANSLATIONS, t = _get_app_globals()
    data = request.json
    kb_names = data.get('kb_names', [])
    topic = data.get('topic', '')
    num_questions = min(int(data.get('num_questions', 3)), 10)
    question_type = data.get('question_type', 'choice')
    difficulty = data.get('difficulty', 'medium')
    web_search = data.get('web_search', False)

    if not kb_names:
        return jsonify({"error": t("no_kb_selected")})
    if not CONFIG.chat_model:
        return jsonify({"error": t("no_chat_model")})
    if not topic.strip():
        return jsonify({"error": "Topic is required"})

    from gangdan.learning.question_gen import generate_questions
    save_dir = _learning_dir("questions")

    @safe_sse_generator
    def generate():
        OLLAMA.reset_stop()
        for event in generate_questions(
            kb_names, topic, num_questions, question_type, difficulty,
            OLLAMA, CHROMA, CONFIG, save_dir=save_dir, web_search=web_search,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@learning_bp.route('/api/learning/questions/list')
def api_list_question_batches():
    save_dir = _learning_dir("questions")
    batches = []
    for f in sorted(save_dir.glob("qbatch_*.json"), reverse=True):
        try:
            from gangdan.learning.models import QuestionBatch
            batch = QuestionBatch.load(f)
            batches.append({
                "batch_id": batch.batch_id,
                "topic": batch.topic,
                "difficulty": batch.difficulty,
                "question_type": batch.question_type,
                "count": len(batch.questions),
                "created_at": batch.created_at,
            })
        except Exception:
            continue
    return jsonify({"batches": batches})


@learning_bp.route('/api/learning/questions/<batch_id>')
def api_get_question_batch(batch_id):
    save_dir = _learning_dir("questions")
    filepath = save_dir / f"{batch_id}.json"
    if not filepath.exists():
        return jsonify({"error": "Batch not found"}), 404
    from gangdan.learning.models import QuestionBatch
    from dataclasses import asdict
    batch = QuestionBatch.load(filepath)
    return jsonify(asdict(batch))


@learning_bp.route('/api/learning/questions/<batch_id>', methods=['DELETE'])
def api_delete_question_batch(batch_id):
    save_dir = _learning_dir("questions")
    filepath = save_dir / f"{batch_id}.json"
    if filepath.exists():
        filepath.unlink()
        return jsonify({"success": True})
    return jsonify({"error": "Batch not found"}), 404


# =============================================================================
# Guided Learning API
# =============================================================================

@learning_bp.route('/api/learning/guide/create', methods=['POST'])
def api_guide_create():
    OLLAMA, CHROMA, CONFIG, DOCS_DIR, DATA_DIR, LANGUAGES, TRANSLATIONS, t = _get_app_globals()
    data = request.json
    kb_names = data.get('kb_names', [])
    web_search = data.get('web_search', False)

    if not kb_names:
        return jsonify({"error": t("no_kb_selected")})
    if not CONFIG.chat_model:
        return jsonify({"error": t("no_chat_model")})

    from gangdan.learning.guided import create_session
    save_dir = _learning_dir("guide")
    result = create_session(kb_names, OLLAMA, CHROMA, CONFIG, DOCS_DIR, save_dir, web_search=web_search)
    return jsonify(result)


@learning_bp.route('/api/learning/guide/start/<session_id>', methods=['POST'])
def api_guide_start(session_id):
    OLLAMA, CHROMA, CONFIG, DOCS_DIR, DATA_DIR, LANGUAGES, TRANSLATIONS, t = _get_app_globals()
    data = request.json or {}
    web_search = data.get('web_search', False)

    from gangdan.learning.guided import generate_lesson
    save_dir = _learning_dir("guide")

    @safe_sse_generator
    def generate():
        OLLAMA.reset_stop()
        for event in generate_lesson(session_id, OLLAMA, CHROMA, CONFIG, DOCS_DIR, save_dir, web_search=web_search):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@learning_bp.route('/api/learning/guide/lesson/<session_id>')
def api_guide_lesson(session_id):
    OLLAMA, CHROMA, CONFIG, DOCS_DIR, DATA_DIR, LANGUAGES, TRANSLATIONS, t = _get_app_globals()

    from gangdan.learning.guided import generate_lesson
    save_dir = _learning_dir("guide")

    @safe_sse_generator
    def generate():
        OLLAMA.reset_stop()
        for event in generate_lesson(session_id, OLLAMA, CHROMA, CONFIG, DOCS_DIR, save_dir):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@learning_bp.route('/api/learning/guide/next/<session_id>', methods=['POST'])
def api_guide_next(session_id):
    from gangdan.learning.guided import next_point
    save_dir = _learning_dir("guide")
    result = next_point(session_id, save_dir)
    return jsonify(result)


@learning_bp.route('/api/learning/guide/chat/<session_id>', methods=['POST'])
def api_guide_chat(session_id):
    OLLAMA, CHROMA, CONFIG, DOCS_DIR, DATA_DIR, LANGUAGES, TRANSLATIONS, t = _get_app_globals()
    data = request.json
    message = data.get('message', '')
    web_search = data.get('web_search', False)
    if not message.strip():
        return jsonify({"error": "Message is required"})

    from gangdan.learning.guided import chat_in_session
    save_dir = _learning_dir("guide")

    @safe_sse_generator
    def generate():
        OLLAMA.reset_stop()
        for event in chat_in_session(session_id, message, OLLAMA, CHROMA, CONFIG, save_dir, web_search=web_search):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@learning_bp.route('/api/learning/guide/summary/<session_id>')
def api_guide_summary(session_id):
    OLLAMA, CHROMA, CONFIG, DOCS_DIR, DATA_DIR, LANGUAGES, TRANSLATIONS, t = _get_app_globals()

    from gangdan.learning.guided import generate_summary
    save_dir = _learning_dir("guide")

    @safe_sse_generator
    def generate():
        OLLAMA.reset_stop()
        for event in generate_summary(session_id, OLLAMA, CONFIG, save_dir):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@learning_bp.route('/api/learning/guide/sessions')
def api_guide_sessions():
    from gangdan.learning.guided import list_sessions
    save_dir = _learning_dir("guide")
    return jsonify({"sessions": list_sessions(save_dir)})


@learning_bp.route('/api/learning/guide/session/<session_id>')
def api_guide_session(session_id):
    from gangdan.learning.guided import get_session_state
    save_dir = _learning_dir("guide")
    state = get_session_state(session_id, save_dir)
    if not state:
        return jsonify({"error": "Session not found"}), 404
    return jsonify(state)


# =============================================================================
# Deep Research API
# =============================================================================

@learning_bp.route('/research')
def research_page():
    """Render the deep research page."""
    from flask import render_template
    from gangdan.app import CONFIG, LANGUAGES, TRANSLATIONS, t
    lang = CONFIG.language if CONFIG.language in LANGUAGES else "zh"
    translations_json = json.dumps(TRANSLATIONS, ensure_ascii=False)
    return render_template('research.html', 
        lang=lang, 
        languages=LANGUAGES, 
        t=t, 
        config=CONFIG,
        translations_json=translations_json)


@learning_bp.route('/api/learning/research/run', methods=['POST'])
def api_research_run():
    OLLAMA, CHROMA, CONFIG, DOCS_DIR, DATA_DIR, LANGUAGES, TRANSLATIONS, t = _get_app_globals()
    data = request.json or {}
    topic = data.get('topic', '')
    kb_names = data.get('kb_names', [])
    depth = data.get('depth', 'medium')
    web_search = data.get('web_search', False)
    output_size = data.get('output_size', 'medium')
    
    provider = data.get('provider', '') or CONFIG.research_provider or 'ollama'
    model_name = data.get('model_name', '') or CONFIG.research_model or ''
    api_url = data.get('api_url', '') or CONFIG.research_api_base_url or ''
    api_key = data.get('api_key', '') or CONFIG.research_api_key or ''
    api_type = data.get('api_type', 'openai')

    if not topic.strip():
        return jsonify({"error": "Topic is required"})
    if not kb_names:
        return jsonify({"error": t("no_kb_selected")})
    if not model_name:
        return jsonify({"error": "Please select a model in settings or on this page"})

    if provider == 'ollama' or not api_url:
        llm_client = OLLAMA
    else:
        from gangdan.core.llm_client import create_client
        llm_client = create_client(
            provider=provider,
            api_key=api_key,
            base_url=api_url
        )
        print(f"[Research] Provider: {provider}, API Type: {api_type}, URL: {api_url}", file=sys.stderr)

    from gangdan.learning.research import run_research
    save_dir = _learning_dir("research")
    
    from dataclasses import replace
    research_config = replace(CONFIG, chat_model=model_name)

    @safe_sse_generator
    def generate():
        if hasattr(llm_client, 'reset_stop'):
            llm_client.reset_stop()
        for event in run_research(topic, kb_names, depth, llm_client, CHROMA, research_config, save_dir, web_search=web_search, output_size=output_size):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@learning_bp.route('/api/learning/research/reports')
def api_research_reports():
    from gangdan.learning.research import list_reports
    save_dir = _learning_dir("research")
    return jsonify({"reports": list_reports(save_dir)})


@learning_bp.route('/api/learning/research/report/<report_id>')
def api_research_report(report_id):
    save_dir = _learning_dir("research")
    filepath = save_dir / f"{report_id}.json"
    if not filepath.exists():
        return jsonify({"error": "Report not found"}), 404
    from gangdan.learning.models import ResearchReport
    from dataclasses import asdict
    report = ResearchReport.load(filepath)
    return jsonify(asdict(report))


@learning_bp.route('/api/learning/research/report/<report_id>', methods=['DELETE'])
def api_research_report_delete(report_id):
    save_dir = _learning_dir("research")
    filepath = save_dir / f"{report_id}.json"
    md_path = save_dir / f"{report_id}.md"
    deleted = False
    if filepath.exists():
        filepath.unlink()
        deleted = True
    if md_path.exists():
        md_path.unlink()
    if deleted:
        return jsonify({"success": True})
    return jsonify({"error": "Report not found"}), 404


# =============================================================================
# Lecture & Handout API
# =============================================================================

@learning_bp.route('/api/learning/lecture/generate', methods=['POST'])
def api_lecture_generate():
    OLLAMA, CHROMA, CONFIG, DOCS_DIR, DATA_DIR, LANGUAGES, TRANSLATIONS, t = _get_app_globals()
    data = request.json
    topic = data.get('topic', '')
    kb_names = data.get('kb_names', [])
    web_search = data.get('web_search', False)

    if not topic.strip():
        return jsonify({"error": "Topic is required"})
    if not kb_names:
        return jsonify({"error": t("no_kb_selected")})
    if not CONFIG.chat_model:
        return jsonify({"error": t("no_chat_model")})

    from gangdan.learning.lecture import generate_lecture
    save_dir = _learning_dir("lectures")

    @safe_sse_generator
    def generate():
        OLLAMA.reset_stop()
        for event in generate_lecture(topic, kb_names, OLLAMA, CHROMA, CONFIG, DOCS_DIR, save_dir, web_search=web_search):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@learning_bp.route('/api/learning/lecture/list')
def api_lecture_list():
    from gangdan.learning.lecture import list_lectures
    save_dir = _learning_dir("lectures")
    return jsonify({"lectures": list_lectures(save_dir)})


@learning_bp.route('/api/learning/lecture/<lecture_id>')
def api_lecture_get(lecture_id):
    save_dir = _learning_dir("lectures")
    filepath = save_dir / f"{lecture_id}.json"
    if not filepath.exists():
        return jsonify({"error": "Lecture not found"}), 404
    from gangdan.learning.models import LectureDocument
    from dataclasses import asdict
    doc = LectureDocument.load(filepath)
    return jsonify(asdict(doc))


@learning_bp.route('/api/learning/lecture/<lecture_id>', methods=['DELETE'])
def api_lecture_delete(lecture_id):
    save_dir = _learning_dir("lectures")
    filepath = save_dir / f"{lecture_id}.json"
    md_path = save_dir / f"{lecture_id}.md"
    deleted = False
    if filepath.exists():
        filepath.unlink()
        deleted = True
    if md_path.exists():
        md_path.unlink()
    if deleted:
        return jsonify({"success": True})
    return jsonify({"error": "Lecture not found"}), 404


# =============================================================================
# Exam Paper API
# =============================================================================

@learning_bp.route('/api/learning/exam/generate', methods=['POST'])
def api_exam_generate():
    OLLAMA, CHROMA, CONFIG, DOCS_DIR, DATA_DIR, LANGUAGES, TRANSLATIONS, t = _get_app_globals()
    data = request.json
    topic = data.get('topic', '')
    kb_names = data.get('kb_names', [])
    difficulty = data.get('difficulty', 'medium')
    web_search = data.get('web_search', False)

    if not topic.strip():
        return jsonify({"error": "Topic is required"})
    if not kb_names:
        return jsonify({"error": t("no_kb_selected")})
    if not CONFIG.chat_model:
        return jsonify({"error": t("no_chat_model")})

    from gangdan.learning.exam import generate_exam
    save_dir = _learning_dir("exams")

    @safe_sse_generator
    def generate():
        OLLAMA.reset_stop()
        for event in generate_exam(topic, kb_names, difficulty, OLLAMA, CHROMA, CONFIG, DOCS_DIR, save_dir, web_search=web_search):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@learning_bp.route('/api/learning/exam/list')
def api_exam_list():
    from gangdan.learning.exam import list_exams
    save_dir = _learning_dir("exams")
    return jsonify({"exams": list_exams(save_dir)})


@learning_bp.route('/api/learning/exam/<paper_id>')
def api_exam_get(paper_id):
    save_dir = _learning_dir("exams")
    filepath = save_dir / f"{paper_id}.json"
    if not filepath.exists():
        return jsonify({"error": "Exam not found"}), 404
    from gangdan.learning.models import ExamPaper
    from dataclasses import asdict
    paper = ExamPaper.load(filepath)
    return jsonify(asdict(paper))


@learning_bp.route('/api/learning/exam/<paper_id>', methods=['DELETE'])
def api_exam_delete(paper_id):
    save_dir = _learning_dir("exams")
    filepath = save_dir / f"{paper_id}.json"
    paper_md = save_dir / f"{paper_id}_paper.md"
    answers_md = save_dir / f"{paper_id}_answers.md"
    deleted = False
    if filepath.exists():
        filepath.unlink()
        deleted = True
    if paper_md.exists():
        paper_md.unlink()
    if answers_md.exists():
        answers_md.unlink()
    if deleted:
        return jsonify({"success": True})
    return jsonify({"error": "Exam not found"}), 404


# =============================================================================
# Shared: KB list for learning pages
# =============================================================================

@learning_bp.route('/api/learning/kb/list')
def api_learning_kb_list():
    """List available KBs for learning features (lightweight, no doc counting)."""
    OLLAMA, CHROMA, CONFIG, DOCS_DIR, DATA_DIR, LANGUAGES, TRANSLATIONS, t = _get_app_globals()
    from gangdan.core.config import load_user_kbs

    kbs = []
    if CHROMA:
        coll_names = CHROMA.list_collections()
        user_kbs = load_user_kbs()
        for name in coll_names:
            display_name = name
            kb_type = "builtin"
            doc_count = 0
            if name in user_kbs:
                display_name = user_kbs[name].get("display_name", name)
                kb_type = "user"
                doc_count = user_kbs[name].get("file_count", 0)
            else:
                # Estimate from docs directory
                kb_dir = DOCS_DIR / name
                if kb_dir.exists():
                    doc_count = len(list(kb_dir.glob("*.md")) + list(kb_dir.glob("*.txt")))
            kbs.append({
                "name": name,
                "display_name": display_name,
                "doc_count": doc_count,
                "type": kb_type,
            })
    return jsonify({"kbs": kbs})
