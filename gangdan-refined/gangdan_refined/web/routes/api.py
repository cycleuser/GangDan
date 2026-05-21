"""Compatibility API routes matching original GangDan's URL patterns.

This blueprint provides all the /api/* endpoints that the frontend JS
files expect, using the refined module architecture internally.
"""

from __future__ import annotations

import json
import io
import zipfile
from flask import Blueprint, request, jsonify, Response, stream_with_context, send_file

from ...core.config import CONFIG, DATA_DIR, CHROMA_DIR, DOCS_DIR, LANGUAGES, TRANSLATIONS, t, save_config, load_config
from ...storage.doc_manager import DOC_SOURCES
from ...core.errors import GangDanError, create_error_response

api_bp = Blueprint("api", __name__)


# --- Models ---

@api_bp.route("/api/models")
def get_models():
    from ...llm.factory import create_chat_client
    client = create_chat_client()
    models = client.get_models()
    return jsonify({"models": models})


@api_bp.route("/api/model/info/<path:model_name>")
def get_model_info(model_name):
    from ...llm.ollama import OllamaClient
    client = OllamaClient(CONFIG.llm.ollama_url)
    info = client.get_model_info(model_name)
    return jsonify(info)


# --- Memory / Context ---

@api_bp.route("/api/memory")
def get_memory():
    from ...llm.ollama import OllamaClient
    client = OllamaClient(CONFIG.llm.ollama_url)
    return jsonify(client.get_memory_usage())


@api_bp.route("/api/context-length", methods=["GET", "POST"])
def context_length():
    from ...llm.ollama import OllamaClient
    client = OllamaClient(CONFIG.llm.ollama_url)
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        length = data.get("context_length", 4096)
        client.set_context_length(length)
        return jsonify({"success": True, "context_length": client.get_context_length()})
    return jsonify({"context_length": client.get_context_length()})


# --- Settings ---

@api_bp.route("/api/settings", methods=["POST"])
def update_settings():
    data = request.get_json(silent=True) or {}
    for key, value in data.items():
        if hasattr(CONFIG, key):
            setattr(CONFIG, key, value)
    save_config()
    return jsonify({"success": True})


@api_bp.route("/api/set-language", methods=["POST"])
def set_language():
    data = request.get_json(silent=True) or {}
    lang = data.get("language", "zh")
    CONFIG.ui.language = lang
    CONFIG.language = lang
    save_config()
    return jsonify({"success": True, "language": lang})


# --- Provider management ---

@api_bp.route("/api/providers")
def get_providers():
    from ...llm.factory import list_providers
    return jsonify({"success": True, "providers": list_providers()})


@api_bp.route("/api/chat-providers")
def get_chat_providers():
    from ...llm.factory import list_providers
    providers = list_providers()
    chat_providers = [p for p in providers if p["api_type"] in ("openai", "anthropic", "ollama")]
    return jsonify({"success": True, "providers": chat_providers})


@api_bp.route("/api/provider/keys", methods=["GET"])
def get_provider_keys():
    return jsonify({"success": True, "keys": CONFIG.llm.provider_keys, "base_urls": CONFIG.llm.provider_base_urls})


@api_bp.route("/api/provider/keys", methods=["POST"])
def set_provider_keys():
    data = request.get_json(silent=True) or {}
    CONFIG.llm.provider_keys = data.get("keys", CONFIG.llm.provider_keys)
    CONFIG.llm.provider_base_urls = data.get("base_urls", CONFIG.llm.provider_base_urls)
    save_config()
    return jsonify({"success": True})


@api_bp.route("/api/provider/models", methods=["POST"])
def get_provider_models():
    data = request.get_json(silent=True) or {}
    provider = data.get("provider", "")
    api_key = data.get("api_key", "")
    base_url = data.get("base_url", "")
    from ...llm.factory import create_client
    client = create_client(provider, api_key=api_key, base_url=base_url)
    models = client.get_models()
    return jsonify({"success": True, "models": models})


@api_bp.route("/api/test-connection", methods=["POST"])
def test_connection():
    from ...llm.ollama import OllamaClient
    client = OllamaClient(CONFIG.llm.ollama_url)
    return jsonify({"success": True, "available": client.is_available()})


@api_bp.route("/api/test-provider", methods=["POST"])
def test_provider():
    data = request.get_json(silent=True) or {}
    provider = data.get("provider", "")
    api_key = data.get("api_key", "")
    base_url = data.get("base_url", "")
    from ...llm.factory import create_client
    client = create_client(provider, api_key=api_key, base_url=base_url)
    available = client.is_available()
    models = client.get_models() if available else []
    return jsonify({"success": True, "available": available, "models": models})


@api_bp.route("/api/test-api", methods=["POST"])
def test_api():
    data = request.get_json(silent=True) or {}
    provider = data.get("provider", "")
    model = data.get("model", "")
    api_key = data.get("api_key", "")
    base_url = data.get("base_url", "")
    from ...llm.factory import create_client
    client = create_client(provider, api_key=api_key, base_url=base_url)
    try:
        reply = client.chat(messages=[{"role": "user", "content": "Hello"}], model=model)
        return jsonify({"success": True, "reply": reply[:200]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# --- Chat ---

@api_bp.route("/api/chat", methods=["POST"])
def chat_send():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")
    model = data.get("model", "")
    stream = data.get("stream", False)
    system_prompt = data.get("system_prompt", "")
    conversation_id = data.get("conversation_id", "")

    if not message:
        return jsonify({"success": False, "error": "Empty message"}), 400

    from ...llm.factory import create_chat_client
    from ...storage.conversation import ConversationManager

    client = create_chat_client()
    model_name = model or CONFIG.llm.chat_model

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    if conversation_id:
        mgr = ConversationManager()
        messages.extend(mgr.get_messages(limit=CONFIG.storage.top_k))

    messages.append({"role": "user", "content": message})

    if stream:
        def generate():
            for chunk in client.chat_stream(messages=messages, model=model_name):
                yield chunk
        return Response(stream_with_context(generate()), mimetype="text/plain")

    try:
        reply = client.chat(messages=messages, model=model_name)
        return jsonify({"success": True, "response": reply, "model": model_name})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/stop", methods=["POST"])
def stop_generation():
    from ...llm.factory import create_chat_client
    client = create_chat_client()
    if hasattr(client, "stop_generation"):
        client.stop_generation()
    return jsonify({"success": True})


@api_bp.route("/api/clear", methods=["POST"])
def clear_conversation():
    from ...storage.conversation import ConversationManager
    mgr = ConversationManager()
    mgr.clear()
    return jsonify({"success": True})


# --- Conversation ---

@api_bp.route("/api/save-conversation")
def save_conversation():
    from ...storage.conversation import ConversationManager
    mgr = ConversationManager()
    return jsonify({"success": mgr.save_to_file(DATA_DIR / "conversation.json")})


@api_bp.route("/api/load-conversation", methods=["POST"])
def load_conversation():
    from ...storage.conversation import ConversationManager
    mgr = ConversationManager()
    count = mgr.load_auto_saved()
    return jsonify({"success": True, "count": count})


# --- Export ---

@api_bp.route("/api/export")
def get_export_data():
    from flask import request as req
    export_type = req.args.get("type", "conversation")
    if export_type == "conversation":
        from ...storage.conversation import ConversationManager
        mgr = ConversationManager()
        return jsonify({"success": True, "messages": mgr.get_all()})
    return jsonify({"success": False, "error": "Unknown export type"})


# --- Knowledge Base ---

@api_bp.route("/api/kb/list")
def kb_list():
    from ...storage.kb_manager import CustomKBManager
    try:
        mgr = CustomKBManager()
        kbs = mgr.list_kbs()
        return jsonify({"success": True, "kbs": [kb.to_dict() for kb in kbs]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/kb/delete", methods=["POST"])
def kb_delete():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    delete_files = data.get("delete_files", False)
    from ...storage.kb_manager import CustomKBManager
    try:
        mgr = CustomKBManager()
        success = mgr.delete_kb(name, delete_files=delete_files)
        return jsonify({"success": success})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/kb/refine-query", methods=["POST"])
def kb_refine_query():
    data = request.get_json(silent=True) or {}
    query = data.get("query", "")
    kb_name = data.get("kb_name", "")
    from ...search.query_expander import QueryExpander
    from ...llm.factory import create_chat_client
    try:
        client = create_chat_client()
        expander = QueryExpander(client)
        expanded = expander.expand(query)
        return jsonify({"success": True, "original": query, "expanded": expanded.expanded_query, "terms": expanded.search_terms})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/kb/translate", methods=["POST"])
def kb_translate():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    target = data.get("target_language", "en")
    source = data.get("source_language", "auto")
    from ...llm.factory import create_chat_client
    try:
        client = create_chat_client()
        result = client.translate(text, target_language=target, source_language=source)
        return jsonify({"success": True, "translation": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Docs ---

@api_bp.route("/api/docs/list")
def docs_list():
    from ...storage.doc_manager import DOC_SOURCES
    return jsonify({"success": True, "sources": DOC_SOURCES})


@api_bp.route("/api/docs/download", methods=["POST"])
def docs_download():
    data = request.get_json(silent=True) or {}
    source = data.get("source", "")
    from ...storage.doc_manager import DocManager
    from ...storage.chroma_manager import ChromaManager
    from ...llm.ollama import OllamaClient
    try:
        ollama = OllamaClient(CONFIG.llm.ollama_url)
        chroma = ChromaManager(persist_dir=str(CHROMA_DIR))
        doc_mgr = DocManager(DOCS_DIR, chroma, ollama)
        count, errors = doc_mgr.download_source(source)
        return jsonify({"success": True, "count": count, "errors": errors})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/docs/index", methods=["POST"])
def docs_index():
    data = request.get_json(silent=True) or {}
    source = data.get("source", "")
    from ...storage.doc_manager import DocManager
    from ...storage.chroma_manager import ChromaManager
    from ...llm.ollama import OllamaClient
    try:
        ollama = OllamaClient(CONFIG.llm.ollama_url)
        chroma = ChromaManager(persist_dir=str(CHROMA_DIR))
        doc_mgr = DocManager(DOCS_DIR, chroma, ollama)
        files, chunks, images = doc_mgr.index_source(source)
        return jsonify({"success": True, "files": files, "chunks": chunks, "images": images})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Search ---

@api_bp.route("/api/ai-summarize", methods=["POST"])
def ai_summarize():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    from ...llm.factory import create_chat_client
    try:
        client = create_chat_client()
        model = data.get("model", CONFIG.llm.chat_model)
        reply = client.chat(
            messages=[{"role": "system", "content": "Summarize the following text concisely."}, {"role": "user", "content": text}],
            model=model,
        )
        return jsonify({"success": True, "summary": reply})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Execute Command ---

@api_bp.route("/api/execute", methods=["POST"])
def execute_command():
    data = request.get_json(silent=True) or {}
    command = data.get("command", "")
    if not command:
        return jsonify({"success": False, "error": "No command provided"}), 400
    try:
        import subprocess
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        return jsonify({
            "success": True,
            "stdout": result.stdout[:10000],
            "stderr": result.stderr[:5000],
            "returncode": result.returncode,
        })
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Command timed out"}), 408
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Terminal ---

@api_bp.route("/api/terminal", methods=["POST"])
def terminal_command():
    data = request.get_json(silent=True) or {}
    command = data.get("command", "")
    cwd = data.get("cwd", str(DATA_DIR))
    if not command:
        return jsonify({"success": False, "error": "No command provided"}), 400
    try:
        import subprocess
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30, cwd=cwd)
        return jsonify({
            "success": True,
            "stdout": result.stdout[:10000],
            "stderr": result.stderr[:5000],
            "returncode": result.returncode,
            "cwd": cwd,
        })
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Command timed out"}), 408
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- AI Command ---

@api_bp.route("/api/ai-command", methods=["POST"])
def ai_command():
    data = request.get_json(silent=True) or {}
    command = data.get("command", "")
    context = data.get("context", "")
    if not command:
        return jsonify({"success": False, "error": "No command provided"}), 400
    try:
        from ...llm.factory import create_chat_client
        client = create_chat_client()
        prompt = f"Execute this command and explain the result: {command}\n\nContext: {context}"
        result = client.chat(
            messages=[{"role": "user", "content": prompt}],
            model=CONFIG.llm.chat_model,
        )
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- System Stats ---

@api_bp.route("/api/system/stats", methods=["GET"])
def system_stats():
    import psutil
    try:
        stats = {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage(str(DATA_DIR)).percent,
            "docs_dir": str(DOCS_DIR),
            "data_dir": str(DATA_DIR),
            "chroma_dir": str(CHROMA_DIR),
        }
        if DOCS_DIR.exists():
            stats["docs_count"] = sum(1 for _ in DOCS_DIR.rglob("*.md"))
        return jsonify({"success": True, "stats": stats})
    except ImportError:
        return jsonify({"success": True, "stats": {"docs_dir": str(DOCS_DIR), "data_dir": str(DATA_DIR)}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- GitHub Search ---

@api_bp.route("/api/github-search", methods=["POST"])
def github_search():
    data = request.get_json(silent=True) or {}
    query = data.get("query", "")
    max_results = data.get("max_results", 10)
    if not query:
        return jsonify({"success": False, "error": "Query is required"}), 400
    try:
        from ...search.web_searcher import WebSearcher
        searcher = WebSearcher()
        results = searcher.search_github(query, max_results=max_results)
        return jsonify({"success": True, "results": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- GitHub Download ---

@api_bp.route("/api/github-download", methods=["POST"])
def github_download():
    data = request.get_json(silent=True) or {}
    repo_url = data.get("url", data.get("repo", ""))
    kb_name = data.get("kb_name", "github")
    if not repo_url:
        return jsonify({"success": False, "error": "Repository URL is required"}), 400
    try:
        from ...document.pdf_downloader import download_github_repo
        result = download_github_repo(repo_url, dest_dir=DOCS_DIR / kb_name)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Wiki Endpoints ---

@api_bp.route("/api/wiki/list", methods=["GET"])
def wiki_list():
    from ...core.config import DOCS_DIR
    wikis = []
    if DOCS_DIR.exists():
        for d in sorted(DOCS_DIR.iterdir()):
            if d.is_dir() and (d / "wiki.json").exists():
                wikis.append({"name": d.name, "path": str(d)})
    return jsonify({"success": True, "wikis": wikis})


@api_bp.route("/api/wiki/build", methods=["POST"])
def wiki_build():
    data = request.get_json(silent=True) or {}
    kb_name = data.get("kb_name", "")
    return jsonify({"success": True, "message": "Wiki build not yet implemented in refined version"})


@api_bp.route("/api/wiki/pages", methods=["GET"])
def wiki_pages():
    kb_name = request.args.get("name", "")
    return jsonify({"success": True, "pages": []})


@api_bp.route("/api/wiki/page", methods=["GET"])
def wiki_page():
    kb_name = request.args.get("name", "")
    page_name = request.args.get("page", "")
    return jsonify({"success": True, "content": "", "page": page_name})


@api_bp.route("/api/wiki/build-cross", methods=["POST"])
def wiki_build_cross():
    data = request.get_json(silent=True) or {}
    return jsonify({"success": True, "message": "Cross-wiki build not yet implemented"})


@api_bp.route("/api/wiki/cross-pages", methods=["GET"])
def wiki_cross_pages():
    return jsonify({"success": True, "pages": []})


@api_bp.route("/api/wiki/cross-page", methods=["GET"])
def wiki_cross_page():
    return jsonify({"success": True, "content": ""})


@api_bp.route("/api/wiki/status", methods=["GET"])
def wiki_status():
    kb_name = request.args.get("name", "")
    return jsonify({"success": True, "status": "ready"})


@api_bp.route("/api/wiki/update-dirty", methods=["POST"])
def wiki_update_dirty():
    data = request.get_json(silent=True) or {}
    return jsonify({"success": True, "updated": 0})


@api_bp.route("/api/wiki/regenerate-pages", methods=["POST"])
def wiki_regenerate_pages():
    data = request.get_json(silent=True) or {}
    return jsonify({"success": True, "regenerated": 0})


# --- Export/Import (top-level routes) ---

@api_bp.route("/api/export-raw-files", methods=["GET"])
def export_raw_files():
    kb_name = request.args.get("name", "").strip()
    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400
    kb_dir = DOCS_DIR / kb_name
    if not kb_dir.exists():
        kb_dir = DOCS_DIR / f"user_{kb_name}"
    if not kb_dir.exists():
        return jsonify({"success": False, "error": f"KB '{kb_name}' not found"}), 404
    try:
        import zipfile
        import io
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for fpath in kb_dir.rglob("*"):
                if fpath.is_file():
                    zf.write(str(fpath), fpath.relative_to(kb_dir))
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype="application/zip", as_attachment=True, download_name=f"{kb_name}_raw.zip")
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/import-raw-files", methods=["POST"])
def import_raw_files():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file provided"}), 400
    uploaded = request.files["file"]
    kb_name = request.form.get("kb_name", "imports")
    try:
        from ...core.config import sanitize_kb_name
        internal_name = sanitize_kb_name(kb_name)
        kb_dir = DOCS_DIR / internal_name
        kb_dir.mkdir(parents=True, exist_ok=True)
        zip_buffer = io.BytesIO(uploaded.read())
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            zf.extractall(str(kb_dir))
        return jsonify({"success": True, "kb_name": kb_name})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/export-kb", methods=["GET"])
def export_kb():
    kb_name = request.args.get("name", "").strip()
    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400
    try:
        from ...storage.chroma_manager import ChromaManager
        chroma = ChromaManager(persist_dir=str(CHROMA_DIR))
        if not chroma.collection_exists(kb_name):
            return jsonify({"success": False, "error": f"KB '{kb_name}' not found"}), 404
        documents = chroma.get_all_documents(kb_name)
        import zipfile
        import io
        export_data = json.dumps({"kb_name": kb_name, "documents": documents}, ensure_ascii=False, indent=2)
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("kb_data.json", export_data)
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype="application/zip", as_attachment=True, download_name=f"{kb_name}_kb.zip")
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/import-kb", methods=["POST"])
def import_kb():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file provided"}), 400
    uploaded = request.files["file"]
    kb_name = request.form.get("kb_name", "imported_kb")
    try:
        from ...storage.chroma_manager import ChromaManager
        from ...core.config import sanitize_kb_name
        internal_name = sanitize_kb_name(kb_name)
        zip_buffer = io.BytesIO(uploaded.read())
        imported_docs = 0
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            for name in zf.namelist():
                if name == "kb_data.json":
                    data = json.loads(zf.read(name))
                    documents = data.get("documents", [])
                    chroma = ChromaManager(persist_dir=str(CHROMA_DIR))
                    for doc in documents:
                        chroma.add_documents(internal_name, [doc])
                        imported_docs += 1
        return jsonify({"success": True, "kb_name": kb_name, "imported_docs": imported_docs})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500