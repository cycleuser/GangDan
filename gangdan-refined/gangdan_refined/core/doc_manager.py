"""Document downloader and indexer."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Dict, List, Tuple

import requests

from gangdan_refined.core.config import CONFIG, detect_language, get_proxies

DOC_SOURCES = {
    "python": {"name": "Python Docs", "urls": [
        "https://docs.python.org/3/tutorial/index.rst",
        "https://docs.python.org/3/library/index.rst",
    ]},
    "flask": {"name": "Flask Docs", "urls": [
        "https://raw.githubusercontent.com/pallets/flask/main/docs/tutorial.rst",
    ]},
    "numpy": {"name": "NumPy Docs", "urls": [
        "https://raw.githubusercontent.com/numpy/numpy/main/doc/source/user/quickstart.rst",
    ]},
    "django": {"name": "Django Docs", "urls": [
        "https://raw.githubusercontent.com/django/django/main/docs/intro/tutorial01.txt",
    ]},
}


class DocManager:
    """Downloads and indexes documentation into the knowledge base."""

    def __init__(self, docs_dir: Path, chroma, ollama):
        self.docs_dir = docs_dir
        self.chroma = chroma
        self.ollama = ollama
        self._session = requests.Session()

    def download_source(self, source_name: str) -> Tuple[int, List[str]]:
        if source_name not in DOC_SOURCES:
            return 0, [f"Unknown source: {source_name}"]
        source = DOC_SOURCES[source_name]
        urls = source["urls"]
        downloaded = 0
        errors = []
        proxies = get_proxies()
        source_dir = self.docs_dir / source_name
        source_dir.mkdir(parents=True, exist_ok=True)

        for url in urls:
            filename = url.split("/")[-1]
            try:
                r = self._session.get(url, timeout=30, proxies=proxies)
                r.raise_for_status()
                content = r.text
                if filename.endswith(".rst"):
                    filename = filename.replace(".rst", ".md")
                elif filename.endswith((".py", ".ipynb")):
                    content = f"```python\n{content}\n```"
                    filename = filename.replace(".py", ".md").replace(".ipynb", ".md")
                elif filename.endswith(".html"):
                    filename = filename.replace(".html", ".md")
                elif filename.endswith(".texi"):
                    filename = filename.replace(".texi", ".md")
                elif filename.endswith(".cpp"):
                    content = f"```cpp\n{content}\n```"
                    filename = filename.replace(".cpp", ".md")
                elif not filename.endswith(".md"):
                    filename += ".md"
                filepath = source_dir / filename
                filepath.write_text(content, encoding="utf-8")
                downloaded += 1
            except Exception as e:
                errors.append(f"{filename}: {type(e).__name__}")
            time.sleep(0.2)
        return downloaded, errors

    def index_source(self, source_name: str, process_images: bool = True,
                     image_mode: str = "copy") -> Tuple[int, int, int]:
        if self.chroma is None or self.chroma.client is None:
            return 0, 0, 0
        if not CONFIG.embedding_model:
            return 0, 0, 0
        source_dir = self.docs_dir / source_name
        if not source_dir.exists():
            return 0, 0, 0
        files = list(source_dir.glob("*.md")) + list(source_dir.glob("*.txt"))
        if not files:
            return 0, 0, 0
        documents, embeddings, metadatas, ids = [], [], [], []
        detected_languages = set()
        total_images = 0

        for filepath in files:
            content = filepath.read_text(encoding="utf-8")
            if process_images and filepath.suffix.lower() == ".md":
                content, img_count = self._process_document_images(source_dir, filepath, content, image_mode)
                total_images += img_count
            doc_lang = detect_language(content)
            detected_languages.add(doc_lang)
            chunks = self._chunk_text(content, CONFIG.chunk_size, CONFIG.chunk_overlap)
            for i, chunk in enumerate(chunks):
                if len(chunk.strip()) < 50:
                    continue
                try:
                    emb = self.ollama.embed(chunk, CONFIG.embedding_model)
                    doc_id = hashlib.md5(f"{filepath.name}_{i}".encode()).hexdigest()
                    documents.append(chunk)
                    embeddings.append(emb)
                    metadatas.append({"source": source_name, "file": filepath.name, "chunk": i, "language": doc_lang})
                    ids.append(doc_id)
                except Exception:
                    continue
        if documents:
            self.chroma.add_documents(source_name, documents, embeddings, metadatas, ids)
            emb_dim = len(embeddings[0]) if embeddings else 0
            if emb_dim > 0:
                self.chroma.set_collection_embedding_model(source_name, CONFIG.embedding_model, emb_dim)
        return len(files), len(documents), total_images

    def _process_document_images(self, kb_dir: Path, source_path: Path,
                                  content: str, image_mode: str = "copy") -> Tuple[str, int]:
        from gangdan_refined.core.image_handler import ImageHandler
        try:
            handler = ImageHandler(kb_dir)
            result = handler.process_document(content, source_path, embed_mode=image_mode)
            if result.copied_count > 0:
                source_path.write_text(result.updated_content, encoding="utf-8")
            return result.updated_content, result.copied_count
        except Exception:
            return content, 0

    def _chunk_text(self, text: str, chunk_size: int, overlap: int) -> List[str]:
        if overlap >= chunk_size:
            overlap = max(0, chunk_size - 1)
        chunks, start = [], 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk)
            start = end - overlap
        return chunks

    def list_downloaded(self) -> List[Dict]:
        result = []
        if self.docs_dir.exists():
            for d in self.docs_dir.iterdir():
                if d.is_dir():
                    result.append({"name": d.name, "files": len(list(d.glob("*.md")))})
        return result
