"""Compatibility API routes matching original GangDan's URL patterns.

This blueprint provides all the /api/* endpoints that the frontend JS
files expect, using the refined module architecture internally.
"""

from __future__ import annotations

import json
from flask import Blueprint, request, jsonify, Response, stream_with_context

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
        chroma = ChromaManager()
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
        chroma = ChromaManager()
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