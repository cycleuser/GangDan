"""gd-summarize - Summarize text with an LLM.

Usage:
    gd-summarize "Long text to summarize..."
    cat paper.txt | gd-summarize --stdin
    gd-summarize "text" --style bullet    # Bullet point summary
    gd-summarize "text" --style abstract  # Abstract style
"""

from __future__ import annotations

import argparse
import sys


def main(args=None) -> None:
    parser = argparse.ArgumentParser(
        prog="gd-summarize",
        description="Summarize text with an LLM",
    )
    parser.add_argument("text", nargs="?", help="Text to summarize (use --stdin for piped input)")
    parser.add_argument("--stdin", action="store_true", help="Read text from stdin")
    parser.add_argument("--style", "-s", default="paragraph",
                        choices=["paragraph", "bullet", "abstract", "key_points", "eli5"],
                        help="Summary style")
    parser.add_argument("--length", "-l", default="medium",
                        choices=["brief", "medium", "detailed"],
                        help="Summary length")
    parser.add_argument("--model", "-m", default="", help="Model to use")
    parser.add_argument("--provider", "-p", default="", help="LLM provider")
    parser.add_argument("--api-key", default="", help="API key for cloud providers")
    parser.add_argument("--language", default="", help="Output language code (zh, en, ja, etc.)")
    from .common import add_common_args, init_env, output, output_error, get_llm_client
    add_common_args(parser)
    parsed = parser.parse_args(args)
    init_env(parsed)

    if parsed.stdin:
        text = sys.stdin.read().strip()
    elif parsed.text:
        text = parsed.text
    else:
        output_error("Text required. Use positional arg or --stdin", parsed)

    from ..core.config import CONFIG
    from ..core.config import detect_language

    style_prompts = {
        "paragraph": "Summarize the following text in a concise paragraph.",
        "bullet": "Summarize the following text as bullet points.",
        "abstract": "Write an academic abstract summarizing the following text.",
        "key_points": "Extract the key points from the following text.",
        "eli5": "Explain the following text in simple terms a 5-year-old could understand.",
    }

    length_hints = {"brief": "in 1-2 sentences", "medium": "in 2-4 sentences", "detailed": "in detail"}

    prompt = style_prompts.get(parsed.style, style_prompts["paragraph"])
    prompt += f" {length_hints.get(parsed.length, '')}."

    if parsed.language:
        from ..core.config import LANGUAGES
        lang_name = LANGUAGES.get(parsed.language, parsed.language)
        prompt += f" Write in {lang_name}."
    elif parsed.style != "eli5":
        detected = detect_language(text)
        if detected != "en":
            prompt += " Write in the same language as the input."

    if parsed.provider == "ollama" or (not parsed.provider and not parsed.api_key):
        from ..llm.ollama import OllamaClient
        client = OllamaClient(CONFIG.llm.ollama_url)
        model = parsed.model or CONFIG.llm.chat_model
    else:
        client = get_llm_client(provider=parsed.provider)
        model = parsed.model or CONFIG.llm.chat_model

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": text},
    ]
    summary = client.chat(messages=messages, model=model)

    output({
        "success": True,
        "summary": summary,
        "style": parsed.style,
        "length": parsed.length,
        "model": model,
    }, parsed, text=summary)