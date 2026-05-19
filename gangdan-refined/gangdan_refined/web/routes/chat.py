"""Chat route blueprint."""

from __future__ import annotations

from flask import Blueprint, request, jsonify, Response, stream_with_context

from ...core.config import CONFIG
from ...core.errors import GangDanError, create_error_response

chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/send", methods=["POST"])
def chat_send():
    """Send a chat message and get a response."""
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")
    model = data.get("model", "")
    stream = data.get("stream", False)

    if not message:
        return jsonify({"success": False, "error": "Empty message"}), 400

    try:
        from ...llm.factory import create_chat_client
        from ...storage.conversation import ConversationManager

        client = create_chat_client()
        model_name = model or CONFIG.llm.chat_model

        messages = []
        if data.get("system_prompt"):
            messages.append({"role": "system", "content": data["system_prompt"]})

        conversation_id = data.get("conversation_id")
        if conversation_id:
            mgr = ConversationManager()
            mgr.load_from_file()
            messages.extend(mgr.get_messages(limit=CONFIG.storage.top_k))

        messages.append({"role": "user", "content": message})

        if stream:
            def generate():
                for chunk in client.chat_stream(messages=messages, model=model_name):
                    yield chunk
            return Response(
                stream_with_context(generate()),
                mimetype="text/plain",
            )

        reply = client.chat(messages=messages, model=model_name)
        return jsonify({"success": True, "response": reply, "model": model_name})

    except GangDanError as e:
        return jsonify(create_error_response(e)), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@chat_bp.route("/stream", methods=["POST"])
def chat_stream():
    """Stream a chat response."""
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")
    model = data.get("model", "")

    if not message:
        return jsonify({"success": False, "error": "Empty message"}), 400

    try:
        from ...llm.factory import create_chat_client

        client = create_chat_client()
        model_name = model or CONFIG.llm.chat_model

        messages = [{"role": "user", "content": message}]
        if data.get("system_prompt"):
            messages.insert(0, {"role": "system", "content": data["system_prompt"]})

        def generate():
            for chunk in client.chat_stream(messages=messages, model=model_name):
                yield chunk

        return Response(generate(), mimetype="text/plain")

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500