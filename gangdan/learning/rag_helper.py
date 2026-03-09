"""Shared RAG retrieval helper for the learning module."""

import sys
import hashlib
from typing import List, Dict, Tuple


def retrieve_context(
    query: str,
    kb_names: List[str],
    ollama,
    chroma,
    config,
    max_chars: int = 3000,
    top_k: int = 10,
) -> Tuple[str, List[str]]:
    """Retrieve relevant context from knowledge bases via RAG.

    Returns:
        (context_string, list_of_source_filenames)
    """
    if not query or not kb_names or not ollama or not chroma:
        return "", []

    if not config.embedding_model:
        print("[RAG Helper] No embedding model configured", file=sys.stderr)
        return "", []

    try:
        query_emb = ollama.embed(query, config.embedding_model)
    except Exception as e:
        print(f"[RAG Helper] Embedding error: {e}", file=sys.stderr)
        return "", []

    # Determine which collections to search
    collections = chroma.list_collections()
    collections = [c for c in collections if c in kb_names]

    if not collections:
        print(f"[RAG Helper] No matching collections for: {kb_names}", file=sys.stderr)
        return "", []

    # Search across all matching collections
    all_results = []
    for coll_name in collections:
        try:
            results = chroma.search(coll_name, query_emb, top_k=top_k)
            for r in results:
                if r.get("distance", 1) < 1.5:
                    meta = r.get("metadata", {})
                    all_results.append({
                        "coll": coll_name,
                        "doc": r["document"],
                        "dist": r["distance"],
                        "id": r.get("id", hashlib.md5(r["document"][:100].encode()).hexdigest()),
                        "file": meta.get("file", "unknown"),
                        "source": meta.get("source", coll_name),
                    })
        except Exception as e:
            print(f"[RAG Helper] Search error in '{coll_name}': {e}", file=sys.stderr)

    # Deduplicate by document ID, keeping best distance
    seen = {}
    for r in all_results:
        if r["id"] not in seen or r["dist"] < seen[r["id"]]["dist"]:
            seen[r["id"]] = r

    merged = sorted(seen.values(), key=lambda x: x["dist"])

    # Build context string with source attribution
    context = ""
    sources_used = set()
    for r in merged:
        snippet = f"\n[Source: {r['file']}]\n{r['doc'][:500]}\n"
        if len(context) + len(snippet) > max_chars:
            break
        context += snippet
        sources_used.add(r["file"])

    sources = sorted(list(sources_used))
    print(f"[RAG Helper] Found {len(merged)} results, using {len(sources)} sources", file=sys.stderr)
    return context, sources


def collect_kb_documents(kb_names: List[str], docs_dir, max_total_chars: int = 8000) -> str:
    """Read raw document files from KB directories for content analysis.

    Returns a truncated summary of all documents concatenated.
    """
    all_text = ""
    for kb_name in kb_names:
        kb_dir = docs_dir / kb_name
        if not kb_dir.exists():
            continue
        for filepath in list(kb_dir.glob("*.md")) + list(kb_dir.glob("*.txt")):
            try:
                content = filepath.read_text(encoding="utf-8")
                header = f"\n--- {filepath.name} ---\n"
                snippet = content[:2000]
                if len(all_text) + len(header) + len(snippet) > max_total_chars:
                    all_text += header + snippet[:max(0, max_total_chars - len(all_text) - len(header))]
                    break
                all_text += header + snippet
            except Exception:
                continue
    return all_text


def compress_rag_notes(context: str, query: str, ollama, config, max_output_chars: int = 800) -> str:
    """Compress raw RAG context into focused notes relevant to the query.

    Applies the DeepTutor NoteAgent pattern: before passing RAG results to
    downstream prompts, compress them into concise summaries that retain
    only query-relevant information.

    Args:
        context: Raw RAG context string with source attributions.
        query: The query/topic the notes should focus on.
        ollama: OllamaClient instance.
        config: App config with chat_model.
        max_output_chars: Max length of compressed output.

    Returns:
        Compressed notes string, or original context if compression fails.
    """
    if not context or not context.strip():
        return context

    # Only compress if context is long enough to benefit
    if len(context) < 500:
        return context

    from gangdan.learning.prompts import get_prompt
    from gangdan.learning.utils import llm_call_with_retry

    lang = config.language if config.language in ("zh", "en") else "en"
    prompt_template = get_prompt("rag_compress", lang)
    prompt = prompt_template.format(query=query, context=context[:3000])

    messages = [{"role": "user", "content": prompt}]
    result = llm_call_with_retry(
        ollama, config, messages, temperature=0.3,
        max_retries=1, parse_json_response=False, label="rag_compress",
    )

    if result and len(result.strip()) > 50:
        return result[:max_output_chars]

    # Fallback: return original context truncated
    return context[:max_output_chars]
