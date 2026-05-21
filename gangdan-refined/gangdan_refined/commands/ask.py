"""gd-ask - Ask a question against a knowledge base (RAG).

Usage:
    gd-ask "What is machine learning?" --kb my_docs
    gd-ask "How does RAG work?" --kb papers --top-k 10 --json
    echo "What is quantum computing?" | gd-ask --kb physics --stdin
"""

from __future__ import annotations

import argparse
import sys


def main(args=None) -> None:
    parser = argparse.ArgumentParser(
        prog="gd-ask",
        description="Ask a question against a knowledge base (RAG)",
    )
    parser.add_argument("question", nargs="?", help="Question to ask (use --stdin for piped input)")
    parser.add_argument("--stdin", action="store_true", help="Read question from stdin")
    parser.add_argument("--kb", "-k", default="default", help="Knowledge base name")
    parser.add_argument("--top-k", "-n", type=int, default=None, help="Number of results to retrieve")
    parser.add_argument("--model", "-m", default="", help="Model for generation")
    parser.add_argument("--no-generate", action="store_true", help="Only retrieve, don't generate answer")
    parser.add_argument("--provider", "-p", default="", help="LLM provider")
    from .common import add_common_args, init_env, output, output_error, get_llm_client
    add_common_args(parser)
    parsed = parser.parse_args(args)
    init_env(parsed)

    if parsed.stdin:
        question = sys.stdin.read().strip()
    elif parsed.question:
        question = parsed.question
    else:
        output_error("Question required. Use positional arg or --stdin", parsed)

    from ..core.config import CONFIG
    from ..storage.kb_manager import CustomKBManager
    from ..llm.ollama import OllamaClient

    # Step 1: Retrieve relevant chunks from KB
    mgr = CustomKBManager()
    top_k = parsed.top_k or CONFIG.storage.top_k

    results = mgr.search_kb(parsed.kb, question, limit=top_k)

    if not results:
        output({"success": True, "question": question, "kb": parsed.kb, "answer": "", "sources": [], "context": ""}, parsed,
               text="No relevant documents found in the knowledge base.")
        return

    # Build context from search results
    context_parts = []
    for r in results:
        if isinstance(r, dict):
            context_parts.append(r.get("content", r.get("text", str(r))))
        else:
            context_parts.append(str(r))
    context = "\n\n---\n\n".join(context_parts[:top_k])

    if parsed.no_generate:
        output({
            "success": True, "question": question, "kb": parsed.kb,
            "context": context[:2000], "sources": len(results),
        }, parsed)
        return

    # Step 2: Generate answer using RAG
    from ..core.config import detect_language

    system_prompt = (
        "You are a helpful assistant. Answer the user's question based on the provided context. "
        "If the context doesn't contain enough information, say so. "
        "Cite specific parts of the context when possible."
    )

    user_prompt = f"Context:\n{context}\n\nQuestion: {question}"

    if parsed.provider == "ollama" or (not parsed.provider and not parsed.api_key):
        client = OllamaClient(CONFIG.llm.ollama_url)
        model = parsed.model or CONFIG.llm.chat_model
    else:
        client = get_llm_client(provider=parsed.provider)
        model = parsed.model or CONFIG.llm.chat_model

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    answer = client.chat(messages=messages, model=model)

    output({
        "success": True,
        "question": question,
        "kb": parsed.kb,
        "answer": answer,
        "sources": len(results),
        "model": model,
    }, parsed, text=answer)