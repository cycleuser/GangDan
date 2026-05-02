"""Wiki builder for GangDan knowledge bases.

Generates structured wiki pages from KB documents with automatic
keyword extraction and internal linking between related concepts.

Inspired by the LLMWiki three-layer architecture:
- Layer 1: Raw source documents (immutable)
- Layer 2: Wiki pages (LLM-generated summaries, concepts, entities)
- Layer 3: Index and cross-references (auto-maintained)
"""

import sys
import json
import re
import hashlib
import os
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime

from gangdan.core.config import CONFIG, DATA_DIR, DOCS_DIR, t
from gangdan.core.ollama_client import OllamaClient


def _get_llm_client():
    """Get an LLM client for wiki generation."""
    # Use Ollama directly - it's the most reliable for local wiki generation
    return OllamaClient(CONFIG.ollama_url)


def _get_model_name():
    """Get the model name for wiki generation.
    
    Prefers smaller, faster models for wiki generation since it makes
    many LLM calls. Falls back to configured model if no small model found.
    """
    try:
        ollama = OllamaClient(CONFIG.ollama_url)
        available = ollama.get_chat_models()
    except Exception:
        available = []
    
    if not available:
        return CONFIG.chat_model_name or CONFIG.chat_model
    
    # Prefer smaller models for wiki generation (faster, cheaper)
    preferred = ['qwen2-math', 'qwen3.5-abliterated', 'qwen2.5']
    for pref in preferred:
        for m in available:
            if pref in m.lower():
                return m
    
    # Fall back to first available
    return available[0]


@dataclass
class WikiPage:
    """A single wiki page."""
    title: str
    content: str
    keywords: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    category: str = "concept"  # concept, entity, overview


@dataclass
class WikiIndex:
    """Wiki index/catalog for a knowledge base."""
    kb_name: str
    pages: List[Dict[str, str]] = field(default_factory=list)
    all_keywords: Set[str] = field(default_factory=set)


@dataclass
class WikiCache:
    """Versioned static storage for wiki snapshots.
    
    Each wiki generation creates a new snapshot stored under:
      {kb_dir}/.wiki_cache/{timestamp}/
    
    Snapshots contain the full wiki tree (manifest.json, index.md, concepts/, entities/).
    The latest snapshot is symlinked/copied to the active wiki/ directory for serving.
    This enables rollback, comparison between generations, and safe incremental updates.
    """
    kb_name: str
    cache_dir: Path = field(init=False)
    active_dir: Path = field(init=False)

    def __post_init__(self):
        candidates = [DOCS_DIR / self.kb_name, DATA_DIR / "custom_kbs" / self.kb_name, DATA_DIR / "preprint_kbs" / self.kb_name]
        kb_dir = next((d for d in candidates if d.exists() and d.is_dir()), candidates[0])
        self.active_dir = kb_dir / "wiki"
        self.cache_dir = kb_dir / ".wiki_cache"

    def _ensure_cache_dir(self):
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def snapshot(self, timestamp: Optional[str] = None) -> Path:
        """Create a versioned snapshot of the current active wiki.
        
        Returns the path to the snapshot directory.
        """
        self._ensure_cache_dir()
        if timestamp is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap_dir = self.cache_dir / timestamp
        if snap_dir.exists():
            return snap_dir
        
        import shutil
        if not self.active_dir.exists():
            snap_dir.mkdir(parents=True, exist_ok=True)
            return snap_dir
        
        snap_dir.mkdir(parents=True, exist_ok=True)
        for item in self.active_dir.iterdir():
            if item.name == ".cache":
                continue
            dest = snap_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
        return snap_dir

    def restore(self, snapshot_name: str) -> bool:
        """Restore wiki from a named snapshot.
        
        Returns True if restore succeeded.
        """
        snap_dir = self.cache_dir / snapshot_name
        if not snap_dir.exists():
            return False
        
        import shutil
        self.active_dir.mkdir(parents=True, exist_ok=True)
        
        # Clear existing content (except .cache)
        for item in self.active_dir.iterdir():
            if item.name == ".cache":
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        
        # Copy from snapshot
        for item in snap_dir.iterdir():
            dest = self.active_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
        return True

    def list_snapshots(self) -> List[Dict[str, str]]:
        """List all available snapshots sorted by time (newest first)."""
        if not self.cache_dir.exists():
            return []
        snaps = []
        for d in sorted(self.cache_dir.iterdir(), reverse=True):
            if d.is_dir():
                manifest = d / "manifest.json"
                meta = {"name": d.name, "path": str(d)}
                if manifest.exists():
                    try:
                        data = json.loads(manifest.read_text(encoding="utf-8"))
                        meta["generated_at"] = data.get("generated_at", "")
                        meta["pages"] = data.get("stats", {}).get("pages", 0)
                        meta["mode"] = data.get("generation_mode", "unknown")
                    except Exception:
                        pass
                snaps.append(meta)
        return snaps

    def delete_snapshot(self, snapshot_name: str) -> bool:
        """Delete a specific snapshot."""
        import shutil
        snap_dir = self.cache_dir / snapshot_name
        if snap_dir.exists():
            shutil.rmtree(snap_dir)
            return True
        return False

    def cleanup(self, keep: int = 5):
        """Keep only the N most recent snapshots, delete the rest."""
        import shutil
        snaps = self.list_snapshots()
        for snap in snaps[keep:]:
            shutil.rmtree(self.cache_dir / snap["name"])


@dataclass
class WikiManifest:
    """Manifest for tracking wiki generation state and incremental updates.
    
    Stores information about source documents, generated pages, and their
    dependencies to enable efficient incremental updates.
    
    Version 3.0 adds:
    - Content hashes for source files (detect content changes, not just mtime)
    - Page dependency tracking (which sources each page uses)
    - Dirty flag for pages needing regeneration
    - Generation mode tracking (rule-based vs llm)
    """
    kb_name: str
    version: str = "3.0"
    generated_at: str = ""
    source_files: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    page_sources: Dict[str, List[str]] = field(default_factory=dict)
    page_content_hashes: Dict[str, str] = field(default_factory=dict)
    keywords: Set[str] = field(default_factory=set)
    stats: Dict[str, int] = field(default_factory=dict)
    generation_mode: str = "rule"  # "rule", "llm", or "hybrid"
    dirty_pages: Set[str] = field(default_factory=set)

    @staticmethod
    def _compute_file_hash(filepath: Path) -> str:
        """Compute MD5 hash of file content."""
        try:
            return hashlib.md5(filepath.read_bytes()).hexdigest()[:12]
        except Exception:
            return ""

    @staticmethod
    def _compute_content_hash(content: str) -> str:
        """Compute MD5 hash of text content for page content tracking."""
        return hashlib.md5(content.encode('utf-8')).hexdigest()[:16]

    @staticmethod
    def _get_file_mtime(filepath: Path) -> float:
        """Get file modification time."""
        try:
            return filepath.stat().st_mtime
        except Exception:
            return 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert manifest to dictionary for JSON serialization."""
        return {
            "kb_name": self.kb_name,
            "version": self.version,
            "generated_at": self.generated_at,
            "source_files": self.source_files,
            "page_sources": self.page_sources,
            "page_content_hashes": self.page_content_hashes,
            "keywords": list(self.keywords),
            "stats": self.stats,
            "generation_mode": self.generation_mode,
            "dirty_pages": list(self.dirty_pages),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WikiManifest":
        """Create manifest from dictionary."""
        return cls(
            kb_name=data.get("kb_name", ""),
            version=data.get("version", "3.0"),
            generated_at=data.get("generated_at", ""),
            source_files=data.get("source_files", {}),
            page_sources=data.get("page_sources", {}),
            page_content_hashes=data.get("page_content_hashes", {}),
            keywords=set(data.get("keywords", [])),
            stats=data.get("stats", {}),
            generation_mode=data.get("generation_mode", "rule"),
            dirty_pages=set(data.get("dirty_pages", [])),
        )


class WikiBuilder:
    """Builds and maintains wiki pages for a knowledge base."""

    def __init__(self, kb_name: str, ollama: Optional[OllamaClient] = None):
        self.kb_name = kb_name
        # Search KB directory in multiple possible locations
        candidates = [
            DOCS_DIR / kb_name,
            DATA_DIR / "custom_kbs" / kb_name,
            DATA_DIR / "preprint_kbs" / kb_name,
        ]
        self.kb_dir = next((d for d in candidates if d.exists() and d.is_dir()), candidates[0])
        self.wiki_dir = self.kb_dir / "wiki"
        self.concepts_dir = self.wiki_dir / "concepts"
        self.entities_dir = self.wiki_dir / "entities"
        self._llm_client = None
        self._model_name = None
        self._cache = WikiCache(kb_name)

    @property
    def cache(self) -> WikiCache:
        """Access the wiki cache for snapshot management."""
        return self._cache

    def _ensure_dirs(self):
        """Create wiki directory structure."""
        self.wiki_dir.mkdir(parents=True, exist_ok=True)
        self.concepts_dir.mkdir(exist_ok=True)
        self.entities_dir.mkdir(exist_ok=True)

    @property
    def manifest_file(self) -> Path:
        """Path to the wiki manifest file."""
        return self.wiki_dir / "manifest.json"

    def _load_manifest(self) -> Optional[WikiManifest]:
        """Load wiki manifest if exists."""
        if not self.manifest_file.exists():
            return None
        try:
            data = json.loads(self.manifest_file.read_text(encoding="utf-8"))
            return WikiManifest.from_dict(data)
        except Exception as e:
            print(f"[Wiki] Error loading manifest: {e}", file=sys.stderr)
            return None

    def _save_manifest(self, manifest: WikiManifest):
        """Save wiki manifest."""
        manifest.generated_at = datetime.now().isoformat()
        try:
            self.manifest_file.write_text(
                json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception as e:
            print(f"[Wiki] Error saving manifest: {e}", file=sys.stderr)

    def _compute_source_info(self) -> Dict[str, Dict[str, Any]]:
        """Compute information about all source files."""
        source_info = {}
        for ext in ("*.md", "*.txt", "*.rst"):
            for filepath in self.kb_dir.glob(ext):
                if filepath.parent.name == "wiki":
                    continue
                try:
                    content = filepath.read_text(encoding="utf-8")
                    source_info[filepath.name] = {
                        "hash": WikiManifest._compute_file_hash(filepath),
                        "content_hash": WikiManifest._compute_content_hash(content),
                        "mtime": WikiManifest._get_file_mtime(filepath),
                        "size": filepath.stat().st_size if filepath.exists() else 0,
                    }
                except Exception:
                    pass
        return source_info

    def _get_changed_sources(self, old_manifest: WikiManifest) -> Tuple[Set[str], Set[str], Set[str], Set[str]]:
        """Find source files that have changed, been removed, or been added.
        
        Returns
        -------
        Tuple[Set[str], Set[str], Set[str], Set[str]]
            (changed_files, removed_files, content_changed_files, new_files)
        """
        new_info = self._compute_source_info()
        old_info = old_manifest.source_files
        
        changed = set()
        removed = set()
        content_changed = set()
        new_files = set()
        
        for filename, info in old_info.items():
            if filename not in new_info:
                removed.add(filename)
            else:
                new_mtime = new_info[filename].get("mtime", 0)
                old_mtime = info.get("mtime", 0)
                if new_mtime > old_mtime:
                    changed.add(filename)
                new_content_hash = new_info[filename].get("content_hash", "")
                old_content_hash = info.get("content_hash", "")
                if new_content_hash != old_content_hash:
                    content_changed.add(filename)
        
        for filename in new_info:
            if filename not in old_info:
                new_files.add(filename)
        
        return changed, removed, content_changed, new_files

    def _get_source_docs(self) -> List[Tuple[str, str]]:
        """Get all source documents in the KB.
        
        Returns
        -------
        List[Tuple[str, str]]
            List of (filename, content) tuples.
        """
        docs = []
        if not self.kb_dir.exists():
            return docs
        for ext in ("*.md", "*.txt", "*.rst"):
            for filepath in self.kb_dir.glob(ext):
                if filepath.parent.name == "wiki":
                    continue
                try:
                    content = filepath.read_text(encoding="utf-8")
                    docs.append((filepath.name, content))
                except Exception as e:
                    print(f"[Wiki] Error reading {filepath}: {e}", file=sys.stderr)
        return docs

    def _get_client(self):
        """Get LLM client lazily."""
        if self._llm_client is None:
            self._llm_client = _get_llm_client()
            self._model_name = _get_model_name()
        return self._llm_client, self._model_name

    def extract_keywords(self, text: str, max_keywords: int = 30) -> List[str]:
        """Extract key concepts and entities from text.
        
        Uses fallback extraction by default (fast, deterministic).
        LLM extraction is available but slow for large documents.
        """
        # Always use fallback for speed and reliability
        return self._fallback_keywords(text, max_keywords)

    def _fallback_keywords(self, text: str, max_keywords: int) -> List[str]:
        """Fallback keyword extraction without LLM."""
        keywords = set()
        
        skip_words = {
            'and', 'or', 'not', 'for', 'in', 'on', 'at', 'to', 'is', 'it',
            'the', 'a', 'an', 'of', 'by', 'as', 'be', 'we', 'you', 'this',
            'that', 'with', 'from', 'are', 'was', 'were', 'has', 'have',
            'true', 'false', 'none', 'any', 'also', 'get', 'set', 'use',
            'new', 'one', 'two', 'first', 'last', 'all', 'each', 'can',
            'will', 'would', 'should', 'could', 'may', 'might', 'must',
            'data', 'type', 'types', 'file', 'files', 'path', 'paths',
            'see', 'more', 'below', 'above', 'here', 'there', 'where',
            'when', 'which', 'what', 'how', 'why', 'who', 'its', 'his',
            'her', 'our', 'their', 'my', 'your', 'if', 'then', 'else',
            'list', 'dict', 'int', 'str', 'float', 'bool', 'object',
            'note', 'notes', 'example', 'examples', 'returns', 'return',
            'parameters', 'parameter', 'args', 'kwargs', 'default',
            'start', 'end', 'size', 'html', 'run', 'in', 'on', 'or',
            'bat', 'lib', 'bin', 'src', 'pkg', 'opt', 'dev', 'etc',
        }
        
        def is_valid_keyword(k):
            k = k.strip()
            if len(k) < 3 or len(k) > 50:
                return False
            if k.lower() in skip_words:
                return False
            # Must contain at least one letter
            if not re.search(r'[a-zA-Z]', k):
                return False
            # Reject pure numbers or number-like
            if re.match(r'^[\d\s\._]+$', k):
                return False
            # Reject punctuation-heavy
            non_alpha = sum(1 for c in k if not c.isalnum() and c != '_')
            if non_alpha > len(k) * 0.3:
                return False
            # Reject single char variable names like a1, b2
            if re.match(r'^[a-z]\d*$', k) and len(k) <= 2:
                return False
            # Reject RST artifacts
            if k.startswith(':') or k.startswith('.') or k.startswith('<') or k.startswith(','):
                return False
            if k.endswith(':') or '``' in k or '<' in k or '>' in k:
                return False
            # Reject common non-technical terms
            if re.match(r'^[a-z]{1,3}$', k):
                return False
            return True
        
        # 1. API function patterns (highest quality)
        for m in re.findall(r'(?:np|numpy|pd|pandas|torch|nn|tf|tensorflow|scipy|sklearn|plt|matplotlib)\.(\w+)', text):
            if is_valid_keyword(m):
                keywords.add(m)
        
        # 2. Inline code (filtered)
        for m in re.findall(r'`([^`]{3,40})`', text):
            m = m.strip()
            if is_valid_keyword(m):
                keywords.add(m)
        
        # 3. Clean section headers
        for m in re.findall(r'^#{1,4}\s+(.+)$', text, re.MULTILINE):
            m = m.strip().strip(':').strip()
            # Remove RST-style refs, links, and HTML tags
            m = re.sub(r'\s*:.*$', '', m)
            m = re.sub(r'\s*<.*>$', '', m)
            m = re.sub(r'\s*\[.*?\]$', '', m)
            m = re.sub(r'\s*\(.*?\)$', '', m)
            m = re.sub(r'\s*`.*?`\s*$', '', m)
            m = m.strip()
            if is_valid_keyword(m):
                keywords.add(m)
        
        # 4. Capitalized multi-word technical terms
        for m in re.findall(r'\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,3})\b', text):
            if is_valid_keyword(m):
                keywords.add(m)
        
        sorted_kws = sorted(keywords, key=lambda x: (len(x), x.lower()))
        return sorted_kws[:max_keywords]

    def generate_wiki(self, force: bool = False, use_llm: bool = False, mode: str = "auto") -> Dict[str, int]:
        """Generate wiki pages for the entire KB.
        
        Supports incremental updates based on source document changes.
        Pages are regenerated only when their source content changes.
        Creates a snapshot of the previous wiki before overwriting.
        
        Parameters
        ----------
        force : bool
            If True, regenerate even if wiki already exists.
        use_llm : bool
            If True, use LLM to generate refined wiki content.
            Deprecated: use `mode` parameter instead.
        mode : str
            Generation mode: "rule" (fast), "llm" (full LLM), "hybrid" (rule + LLM refine), "auto" (default).
            In "auto" mode, uses hybrid if LLM is available, falls back to rule.
            
        Returns
        -------
        Dict[str, int]
            Statistics: {'pages': N, 'keywords': M, 'links': L, 'updated': X, 'skipped': Y}
        """
        self._ensure_dirs()
        
        # Snapshot existing wiki before overwriting
        old_manifest = self._load_manifest()
        if old_manifest and not force:
            self._cache.snapshot()
        
        docs = self._get_source_docs()
        if not docs:
            return {"pages": 0, "keywords": 0, "links": 0, "updated": 0, "skipped": 0}

        # Resolve mode
        if use_llm:
            generation_mode = "llm"
        elif mode == "auto":
            generation_mode = "hybrid"
        elif mode in ("rule", "llm", "hybrid"):
            generation_mode = mode
        else:
            generation_mode = "hybrid"

        print(f"[Wiki] Building wiki for '{self.kb_name}' from {len(docs)} documents (mode={generation_mode})", file=sys.stderr)

        old_manifest = old_manifest if not force else None
        changed_files = set()
        removed_files = set()
        content_changed_files = set()
        new_files = set()
        
        if old_manifest:
            changed_files, removed_files, content_changed_files, new_files = self._get_changed_sources(old_manifest)
            if changed_files or removed_files or content_changed_files or new_files:
                print(f"[Wiki] Detected {len(changed_files)} changed, {len(removed_files)} removed, {len(content_changed_files)} content changed, {len(new_files)} new", file=sys.stderr)

        source_info = self._compute_source_info()
        
        all_keywords: Dict[str, List[str]] = {}
        doc_keywords: Dict[str, List[str]] = {}
        
        for filename, content in docs:
            kws = self.extract_keywords(content)
            doc_keywords[filename] = kws
            for kw in kws:
                if kw not in all_keywords:
                    all_keywords[kw] = []
                all_keywords[kw].append(filename)

        page_sources: Dict[str, List[str]] = {}
        page_content_hashes: Dict[str, str] = {}
        
        updated_pages = 0
        skipped_pages = 0
        
        for keyword, sources in all_keywords.items():
            page_file = self.concepts_dir / f"{self._slugify(keyword)}.md"
            slug = self._slugify(keyword)
            page_sources[slug] = sources
            
            needs_update = force
            
            if not needs_update and old_manifest:
                page_existed = slug in old_manifest.page_sources
                if not page_file.exists() and page_existed:
                    needs_update = True
                elif page_file.exists() and not page_existed:
                    needs_update = True
                else:
                    page_sources_set = set(sources)
                    old_sources_set = set(old_manifest.page_sources.get(slug, []))
                    if page_sources_set & content_changed_files:
                        needs_update = True
                    elif page_sources_set & removed_files:
                        needs_update = True
                    elif old_manifest.generation_mode != generation_mode:
                        needs_update = True
                    elif slug in old_manifest.dirty_pages:
                        needs_update = True
            
            if not needs_update and page_file.exists():
                page_content_hashes[slug] = old_manifest.page_content_hashes.get(slug, "")
                skipped_pages += 1
                continue
            
            relevant_text = self._gather_keyword_content(docs, keyword, sources)
            
            if generation_mode == "llm":
                page_content = self._generate_concept_page_llm(keyword, relevant_text, sources, docs)
            elif generation_mode == "hybrid":
                page_content = self._generate_concept_page_hybrid(keyword, relevant_text, sources, docs)
            else:
                page_content = self._generate_concept_page(keyword, relevant_text, sources)
            page_file.write_text(page_content, encoding="utf-8")
            page_content_hashes[slug] = WikiManifest._compute_content_hash(page_content)
            updated_pages += 1

        overview = self._generate_overiew(docs, all_keywords)
        overview_file = self.wiki_dir / "index.md"
        overview_file.write_text(overview, encoding="utf-8")

        link_count = self._add_internal_links(all_keywords)

        manifest = WikiManifest(
            kb_name=self.kb_name,
            source_files=source_info,
            page_sources=page_sources,
            page_content_hashes=page_content_hashes,
            keywords=set(all_keywords.keys()),
            stats={
                "pages": len(all_keywords) + 1,
                "keywords": len(all_keywords),
                "links": link_count,
                "updated": updated_pages,
                "skipped": skipped_pages,
            },
            generation_mode=generation_mode,
            dirty_pages=set(),
        )
        self._save_manifest(manifest)

        # Snapshot the newly generated wiki
        self._cache.snapshot()

        stats = {
            "pages": len(all_keywords) + 1,
            "keywords": len(all_keywords),
            "links": link_count,
            "updated": updated_pages,
            "skipped": skipped_pages,
        }
        print(f"[Wiki] Built: {stats}", file=sys.stderr)
        return stats

    def _gather_keyword_content(self, docs: List[Tuple[str, str]], keyword: str, sources: Optional[List[str]] = None) -> str:
        """Gather all content related to a keyword from source documents.
        
        Parameters
        ----------
        docs : List[Tuple[str, str]]
            List of (filename, content) tuples.
        keyword : str
            Keyword to search for.
        sources : Optional[List[str]]
            If provided, only search in these source files (for incremental updates).
        """
        snippets = []
        target_sources = set(sources) if sources else None
        
        for filename, content in docs:
            if target_sources and filename not in target_sources:
                continue
            lines = content.split('\n')
            current_section = ""
            for idx, line in enumerate(lines):
                if line.startswith('#'):
                    current_section = line
                if keyword.lower() in line.lower():
                    start = max(0, idx - 3)
                    end = min(len(lines), idx + 10)
                    context = '\n'.join(lines[start:end])
                    snippets.append(f"From {filename} ({current_section}):\n{context}")
                    if len(snippets) >= 5:
                        break
            if len(snippets) >= 5:
                break
        return '\n\n---\n\n'.join(snippets[:5])

    def _get_source_document_for_llm(self, docs: List[Tuple[str, str]], keyword: str, sources: List[str], max_chars: int = 8000) -> str:
        """Get source documents for LLM to read (not just snippets).
        
        This allows LLM to generate better summaries by reading the actual content.
        Each source file contributes up to max_chars to stay within context limits.
        """
        target_sources = set(sources)
        relevant_docs = []
        total_chars = 0
        
        for filename, content in docs:
            if filename not in target_sources:
                continue
            chars_to_use = min(len(content), max_chars // len(target_sources))
            relevant_docs.append(f"=== {filename} ===\n{content[:chars_to_use]}")
            total_chars += chars_to_use
        
        return '\n\n'.join(relevant_docs)

    def _generate_concept_page(self, keyword: str, content: str, sources: List[str]) -> str:
        """Generate a wiki concept page for a keyword.
        
        Uses fallback content extraction by default (fast, no LLM needed).
        """
        body = self._fallback_concept_content(keyword, content, sources)
        return self._build_page(keyword, body, sources)

    def _build_page(self, keyword: str, body: str, sources: List[str]) -> str:
        """Build a wiki page from body content."""
        sources_list = '\n'.join(f"- {s}" for s in sources)
        return f"""---
title: "{keyword}"
category: concept
sources: {len(sources)}
---

# {keyword}

{body}

## Sources

{sources_list}
"""

    def _fallback_concept_content(self, keyword: str, content: str, sources: List[str]) -> str:
        """Generate basic concept content without LLM."""
        # Extract relevant paragraphs mentioning the keyword
        paragraphs = content.split('\n\n')
        relevant = []
        for p in paragraphs:
            if keyword.lower() in p.lower() and len(p) > 20:
                # Clean up RST markup
                p = re.sub(r':\w+:`([^`]+)`', r'`\1`', p)
                p = re.sub(r'``([^`]+)``', r'`\1`', p)
                p = re.sub(r'\.\.\s+\w+::\s*', '', p)
                relevant.append(p)
            if len(relevant) >= 5:
                break
        
        if relevant:
            return '\n\n'.join(relevant[:5])
        return f"Information about **{keyword}** found in: {', '.join(sources)}."

    def _generate_concept_page_llm(
        self,
        keyword: str,
        content: str,
        sources: List[str],
        docs: Optional[List[Tuple[str, str]]] = None
    ) -> str:
        """Generate refined wiki content using LLM.
        
        Creates a concise, well-structured summary from source content.
        Falls back to rule-based extraction if LLM is unavailable.
        
        Parameters
        ----------
        keyword : str
            The concept/keyword to generate page for.
        content : str
            Relevant snippets from source documents.
        sources : List[str]
            Source filenames this keyword appears in.
        docs : Optional[List[Tuple[str, str]]]
            Full source documents for deeper LLM reading (when available).
        """
        try:
            body = self._llm_concept_content(keyword, content, sources, docs)
            return self._build_page(keyword, body, sources)
        except Exception as e:
            print(f"[Wiki] LLM generation failed for '{keyword}': {e}", file=sys.stderr)
            body = self._fallback_concept_content(keyword, content, sources)
            return self._build_page(keyword, body, sources)

    def _generate_concept_page_hybrid(
        self,
        keyword: str,
        content: str,
        sources: List[str],
        docs: Optional[List[Tuple[str, str]]] = None
    ) -> str:
        """Generate wiki content using hybrid mode (rule-based + LLM refinement).
        
        More efficient than pure LLM: extracts baseline with rules, then refines.
        Falls back to rule-based if LLM is unavailable.
        """
        try:
            body = self._hybrid_concept_content(keyword, content, sources, docs)
            return self._build_page(keyword, body, sources)
        except Exception as e:
            print(f"[Wiki] Hybrid generation failed for '{keyword}': {e}", file=sys.stderr)
            body = self._fallback_concept_content(keyword, content, sources)
            return self._build_page(keyword, body, sources)

    def _llm_concept_content(
        self,
        keyword: str,
        content: str,
        sources: List[str],
        docs: Optional[List[Tuple[str, str]]] = None
    ) -> str:
        """Use LLM to generate refined concept content.

        If docs are provided, LLM reads the full source documents to create
        a more comprehensive and accurate summary.
        """
        client, model = self._get_client()

        if docs:
            full_doc_text = self._get_source_document_for_llm(docs, keyword, sources)
            context_note = "Read the full source documents below to understand the context."
            source_material = full_doc_text
        else:
            context_note = "Based on the following excerpts from source documents."
            source_material = content[:3000]

        prompt = f"""You are writing a concise wiki entry for the concept "{keyword}".

{context_note}

Source material (from: {', '.join(sources)}):

{source_material}

Create a well-structured wiki entry that:
1. Starts with a clear definition or one-sentence overview
2. Explains key functionality in 2-3 paragraphs
3. Includes practical usage examples if available in the source
4. Maintains technical accuracy
5. Uses markdown formatting appropriately

Write a concise wiki entry (200-400 words) in markdown format. Focus on what developers need to know to use this concept effectively:"""

        try:
            response = client.chat(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a technical documentation writer. Write clear, concise wiki entries in markdown format. Focus on practical information developers need. Output only the wiki content, no preamble or explanation."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
            )

            if isinstance(response, dict):
                return response.get("message", {}).get("content", "")
            elif hasattr(response, "message"):
                return response.message.content
            else:
                return str(response)
        except Exception as e:
            raise RuntimeError(f"LLM call failed: {e}") from e

    def _hybrid_concept_content(
        self,
        keyword: str,
        content: str,
        sources: List[str],
        docs: Optional[List[Tuple[str, str]]] = None
    ) -> str:
        """Hybrid mode: use rule-based extraction first, then LLM to refine.
        
        This is more efficient than pure LLM mode because:
        1. Rule-based extraction provides a solid baseline quickly
        2. LLM only needs to refine/summarize, not generate from scratch
        3. Falls back gracefully if LLM is unavailable
        """
        rule_content = self._fallback_concept_content(keyword, content, sources)
        
        try:
            client, model = self._get_client()
            
            prompt = f"""You are improving a wiki entry for "{keyword}". 

Below is the current draft extracted from source documents. Please refine it to be:
- More concise and readable
- Better structured with clear headings
- Technically accurate while removing redundancy
- Adding a brief overview sentence at the top if missing

Current draft:
{rule_content[:2000]}

Return only the improved version in markdown format:"""

            response = client.chat(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a technical documentation editor. Improve wiki drafts for clarity and conciseness. Output only the improved content."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.2,
            )

            if isinstance(response, dict):
                refined = response.get("message", {}).get("content", "")
            elif hasattr(response, "message"):
                refined = response.message.content
            else:
                refined = str(response)
            
            if refined and len(refined.strip()) > 50:
                return refined
        except Exception as e:
            print(f"[Wiki] Hybrid LLM refinement failed for '{keyword}', using rule-based: {e}", file=sys.stderr)
        
        return rule_content

    def _generate_overiew(self, docs: List[Tuple[str, str]], all_keywords: Dict[str, List[str]]) -> str:
        """Generate the wiki index/overview page."""
        kb_display = self.kb_name.replace('_', ' ').title()
        
        # Group keywords by category (heuristic)
        api_keywords = [k for k in all_keywords if '.' in k or '(' in k]
        concept_keywords = [k for k in all_keywords if '.' not in k and '(' not in k]
        
        api_links = '\n'.join(
            f"- [{k}](concepts/{self._slugify(k)}.md)" 
            for k in sorted(api_keywords)[:50]
        )
        concept_links = '\n'.join(
            f"- [{k}](concepts/{self._slugify(k)}.md)" 
            for k in sorted(concept_keywords)[:50]
        )
        
        source_list = '\n'.join(f"- {fn}" for fn, _ in docs)
        
        return f"""# {kb_display} Wiki

Auto-generated wiki for the **{kb_display}** knowledge base.

## API Reference

{api_links or '*No API terms detected*'}

## Concepts

{concept_links or '*No concepts detected*'}

## Source Documents

{source_list}

---
*Generated by GangDan Wiki Builder*
"""

    def _add_internal_links(self, all_keywords: Dict[str, List[str]]) -> int:
        """Add internal links between wiki pages for related keywords."""
        link_count = 0
        keyword_pages = {}
        
        # Common words to skip when linking
        skip_words = {
            'and', 'or', 'not', 'for', 'in', 'on', 'at', 'to', 'is', 'it',
            'the', 'a', 'an', 'of', 'by', 'as', 'be', 'we', 'you', 'this',
            'that', 'with', 'from', 'are', 'was', 'were', 'has', 'have',
            'true', 'false', 'none', 'any', 'also', 'get', 'set', 'use',
            'new', 'one', 'two', 'first', 'last', 'all', 'each', 'can',
            'will', 'would', 'should', 'could', 'may', 'might', 'must',
            'data', 'type', 'types', 'file', 'files', 'path', 'paths',
            'see', 'more', 'below', 'above', 'here', 'there', 'where',
            'when', 'which', 'what', 'how', 'why', 'who', 'its', 'his',
            'her', 'our', 'their', 'my', 'your', 'if', 'then', 'else',
        }
        
        for keyword in all_keywords:
            if keyword.lower() in skip_words or len(keyword) < 3:
                continue
            slug = self._slugify(keyword)
            page_file = self.concepts_dir / f"{slug}.md"
            if page_file.exists():
                keyword_pages[keyword.lower()] = (keyword, page_file)
        
        for keyword, (display_name, page_file) in keyword_pages.items():
            try:
                content = page_file.read_text(encoding="utf-8")
            except Exception:
                continue
            
            parts = content.split('---', 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                body = parts[2]
            else:
                frontmatter = ""
                body = content
            
            modified = False
            for other_kw, (other_display, other_file) in keyword_pages.items():
                if other_kw == keyword:
                    continue
                if other_kw.lower() in skip_words or len(other_display) < 3:
                    continue
                    
                other_slug = self._slugify(other_display)
                other_path = f"concepts/{other_slug}.md"
                
                escaped = re.escape(other_display)
                pattern = re.compile(
                    r'(?<!\[)(?<!`)(?<!\()(?<!href=")(?<!/)' + escaped + r'(?!\])(?!`)(?!\))(?!")(?!</)',
                    re.IGNORECASE
                )
                
                def replace_with_link(match):
                    nonlocal link_count, modified
                    link_count += 1
                    modified = True
                    return f'[{match.group(0)}]({other_path})'
                
                body = pattern.sub(replace_with_link, body, count=1)
            
            if modified:
                new_content = f"---{frontmatter}---{body}"
                page_file.write_text(new_content, encoding="utf-8")
        
        return link_count

    def _slugify(self, text: str) -> str:
        """Convert text to a filename-safe slug."""
        text = text.lower().strip()
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'[\s_]+', '-', text)
        text = re.sub(r'-+', '-', text)
        return text.strip('-')

    def get_wiki_pages(self) -> List[Dict[str, str]]:
        """Get list of all wiki pages for this KB.
        
        Returns
        -------
        List[Dict[str, str]]
            List of page info dicts with title, path, category.
        """
        pages = []
        if not self.wiki_dir.exists():
            return pages
        
        # Index page
        index_file = self.wiki_dir / "index.md"
        if index_file.exists():
            pages.append({
                "title": f"{self.kb_name} Wiki",
                "path": "wiki/index.md",
                "category": "index",
            })
        
        # Concept pages
        if self.concepts_dir.exists():
            for page_file in sorted(self.concepts_dir.glob("*.md")):
                try:
                    content = page_file.read_text(encoding="utf-8")
                    # Extract title from frontmatter or heading
                    title = page_file.stem.replace('-', ' ').title()
                    match = re.search(r'^title:\s*"(.+?)"', content, re.MULTILINE)
                    if match:
                        title = match.group(1)
                    else:
                        match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
                        if match:
                            title = match.group(1)
                    
                    pages.append({
                        "title": title,
                        "path": f"wiki/concepts/{page_file.name}",
                        "category": "concept",
                    })
                except Exception:
                    pass
        
        return pages

    def get_wiki_page(self, page_path: str) -> Optional[str]:
        """Get content of a specific wiki page.
        
        Parameters
        ----------
        page_path : str
            Relative path within the wiki (e.g., "concepts/numpy-array.md").
            
        Returns
        -------
        str or None
            Page content, or None if not found.
        """
        full_path = (self.wiki_dir / page_path).resolve()
        if not str(full_path).startswith(str(self.wiki_dir.resolve())):
            return None
        if full_path.exists():
            return full_path.read_text(encoding="utf-8")
        return None

    def wiki_exists(self) -> bool:
        """Check if wiki has been generated for this KB."""
        return (self.wiki_dir / "index.md").exists()

    def get_wiki_status(self) -> Dict[str, Any]:
        """Get current wiki status including dirty pages needing updates.
        
        Returns
        -------
        Dict[str, Any]
            Status info including pages, dirty count, last generated, mode.
        """
        manifest = self._load_manifest()
        if not manifest:
            return {
                "exists": False,
                "pages": 0,
                "dirty": 0,
                "generation_mode": None,
                "last_generated": None,
            }
        
        changed_files, removed_files, content_changed, new_files = self._get_changed_sources(manifest)
        dirty_keywords = []
        
        for slug, sources in manifest.page_sources.items():
            source_set = set(sources)
            if source_set & content_changed:
                dirty_keywords.append(slug)
            elif source_set & removed_files:
                dirty_keywords.append(slug)
        
        for slug, sources in manifest.page_sources.items():
            source_set = set(sources)
            if source_set & new_files:
                if slug not in dirty_keywords:
                    dirty_keywords.append(slug)
        
        return {
            "exists": True,
            "pages": manifest.stats.get("pages", 0),
            "keywords": len(manifest.keywords),
            "dirty": len(dirty_keywords),
            "dirty_pages": dirty_keywords[:20],
            "changed_sources": list(content_changed)[:10],
            "removed_sources": list(removed_files)[:10],
            "new_sources": list(new_files)[:10],
            "generation_mode": manifest.generation_mode,
            "last_generated": manifest.generated_at,
        }

    def update_dirty_pages(self, use_llm: bool = False, mode: str = "auto") -> Dict[str, int]:
        """Update only pages marked as dirty due to source changes.

        This enables true incremental updates - only regenerate affected pages.

        Parameters
        ----------
        use_llm : bool
            If True, use LLM for regenerated pages.
            Deprecated: use `mode` parameter instead.
        mode : str
            Generation mode: "rule", "llm", "hybrid", or "auto".

        Returns
        -------
        Dict[str, int]
            Statistics about the update.
        """
        manifest = self._load_manifest()
        if not manifest:
            return {"pages": 0, "updated": 0, "skipped": 0, "error": "No wiki exists"}

        changed_files, removed_files, content_changed, new_files = self._get_changed_sources(manifest)
        if not changed_files and not removed_files and not content_changed and not new_files:
            return {"pages": 0, "updated": 0, "skipped": 0, "message": "No changes detected"}

        docs = self._get_source_docs()
        if not docs:
            return {"pages": 0, "updated": 0, "skipped": 0, "error": "No source documents"}

        print(f"[Wiki] Incremental update for '{self.kb_name}': {len(content_changed)} content changed, {len(removed_files)} removed, {len(new_files)} new (mode={generation_mode})", file=sys.stderr)

        updated_pages = 0
        skipped_pages = 0
        page_content_hashes = dict(manifest.page_content_hashes)
        page_sources = dict(manifest.page_sources)

        all_keywords = {}
        for filename, content in docs:
            kws = self.extract_keywords(content)
            for kw in kws:
                if kw not in all_keywords:
                    all_keywords[kw] = []
                all_keywords[kw].append(filename)

        for keyword, sources in all_keywords.items():
            slug = self._slugify(keyword)
            page_file = self.concepts_dir / f"{slug}.md"
            source_set = set(sources)

            needs_update = False
            if source_set & content_changed:
                needs_update = True
            elif source_set & removed_files:
                needs_update = True
            elif source_set & new_files:
                needs_update = True
            elif not page_file.exists():
                needs_update = True

            if not needs_update:
                skipped_pages += 1
                continue

            relevant_text = self._gather_keyword_content(docs, keyword, sources)

            if generation_mode == "llm":
                page_content = self._generate_concept_page_llm(keyword, relevant_text, sources, docs)
            elif generation_mode == "hybrid":
                page_content = self._generate_concept_page_hybrid(keyword, relevant_text, sources, docs)
            else:
                page_content = self._generate_concept_page(keyword, relevant_text, sources)

            page_file.write_text(page_content, encoding="utf-8")
            page_content_hashes[slug] = WikiManifest._compute_content_hash(page_content)
            page_sources[slug] = sources
            updated_pages += 1

        link_count = self._add_internal_links(all_keywords)

        new_manifest = WikiManifest(
            kb_name=self.kb_name,
            source_files=self._compute_source_info(),
            page_sources=page_sources,
            page_content_hashes=page_content_hashes,
            keywords=set(all_keywords.keys()),
            stats={
                "pages": len(all_keywords) + 1,
                "keywords": len(all_keywords),
                "links": link_count,
                "updated": updated_pages,
                "skipped": skipped_pages,
            },
            generation_mode=generation_mode,
            dirty_pages=set(),
        )
        self._save_manifest(new_manifest)

        # Snapshot after incremental update
        self._cache.snapshot()

        return {
            "pages": len(all_keywords) + 1,
            "updated": updated_pages,
            "skipped": skipped_pages,
            "links": link_count,
        }

    def regenerate_pages(self, page_slugs: List[str], use_llm: bool = True, mode: str = "auto") -> Dict[str, int]:
        """Regenerate specific wiki pages by slug.

        Useful for upgrading pages from rule-based to LLM-generated without
        rebuilding the entire wiki.

        Parameters
        ----------
        page_slugs : List[str]
            List of page slugs to regenerate (without .md extension).
        use_llm : bool
            If True, use LLM for regeneration. If False, use rule-based.
            Deprecated: use `mode` parameter instead.
        mode : str
            Generation mode: "rule", "llm", "hybrid", or "auto".

        Returns
        -------
        Dict[str, int]
            Statistics about the regeneration.
        """
        manifest = self._load_manifest()
        if not manifest:
            return {"pages": 0, "updated": 0, "error": "No wiki exists"}

        docs = self._get_source_docs()
        if not docs:
            return {"pages": 0, "updated": 0, "error": "No source documents"}

        # Resolve mode
        if use_llm:
            generation_mode = "llm"
        elif mode == "auto":
            generation_mode = "hybrid"
        elif mode in ("rule", "llm", "hybrid"):
            generation_mode = mode
        else:
            generation_mode = "hybrid"

        updated_pages = 0
        not_found = []

        for slug in page_slugs:
            keyword = self._find_keyword_by_slug(slug, manifest)
            if not keyword:
                not_found.append(slug)
                continue

            sources = manifest.page_sources.get(slug, [])
            page_file = self.concepts_dir / f"{slug}.md"

            relevant_text = self._gather_keyword_content(docs, keyword, sources)

            if generation_mode == "llm":
                page_content = self._generate_concept_page_llm(keyword, relevant_text, sources, docs)
            elif generation_mode == "hybrid":
                page_content = self._generate_concept_page_hybrid(keyword, relevant_text, sources, docs)
            else:
                page_content = self._generate_concept_page(keyword, relevant_text, sources)

            page_file.write_text(page_content, encoding="utf-8")
            manifest.page_content_hashes[slug] = WikiManifest._compute_content_hash(page_content)
            updated_pages += 1

        if updated_pages > 0:
            manifest.generation_mode = generation_mode
            manifest.dirty_pages.difference_update(page_slugs)
            self._save_manifest(manifest)

        self._add_internal_links({kw: [] for kw in manifest.keywords})

        result = {
            "pages": len(page_slugs),
            "updated": updated_pages,
        }
        if not_found:
            result["not_found"] = not_found

        return result

    def _find_keyword_by_slug(self, slug: str, manifest: WikiManifest) -> Optional[str]:
        """Find keyword by its page slug."""
        for keyword, sources in manifest.page_sources.items():
            page_slug = self._slugify(keyword)
            if page_slug == slug:
                return keyword
        return None


# =============================================================================
# Cross-KB Wiki Builder
# =============================================================================

class CrossWikiBuilder:
    """Builds a unified wiki across multiple knowledge bases.
    
    Merges related concepts from different KBs and creates
    cross-references between them.
    """
    
    def __init__(self, kb_names: List[str]):
        self.kb_names = kb_names
        self.cross_wiki_dir = DOCS_DIR / "cross_wiki"
        self.concepts_dir = self.cross_wiki_dir / "concepts"
        self.builders = {name: WikiBuilder(name) for name in kb_names}
    
    def _ensure_dirs(self):
        self.cross_wiki_dir.mkdir(parents=True, exist_ok=True)
        self.concepts_dir.mkdir(exist_ok=True)
    
    def build(self, force: bool = False) -> Dict[str, int]:
        """Build cross-KB wiki.
        
        Parameters
        ----------
        force : bool
            If True, regenerate even if wiki already exists.
            
        Returns
        -------
        Dict[str, int]
            Statistics about the generated wiki.
        """
        self._ensure_dirs()
        
        print(f"[CrossWiki] Building wiki for {len(self.kb_names)} KBs: {self.kb_names}", file=sys.stderr)
        
        # Step 1: Collect keywords from all KBs
        all_keywords: Dict[str, Dict[str, List[str]]] = {}  # keyword -> {kb_name: [sources]}
        
        for kb_name in self.kb_names:
            builder = self.builders[kb_name]
            docs = builder._get_source_docs()
            for filename, content in docs:
                kws = builder._fallback_keywords(content, 40)
                for kw in kws:
                    if kw not in all_keywords:
                        all_keywords[kw] = {}
                    if kb_name not in all_keywords[kw]:
                        all_keywords[kw][kb_name] = []
                    all_keywords[kw][kb_name].append(filename)
        
        print(f"[CrossWiki] Found {len(all_keywords)} unique keywords across KBs", file=sys.stderr)
        
        # Step 2: Generate concept pages (merged from multiple KBs)
        concept_count = 0
        for keyword, kb_sources in all_keywords.items():
            slug = _slugify(keyword)
            page_file = self.concepts_dir / f"{slug}.md"
            
            if page_file.exists() and not force:
                concept_count += 1
                continue
            
            # Gather content from all KBs
            relevant_sections = []
            for kb_name, source_files in kb_sources.items():
                builder = self.builders[kb_name]
                docs = builder._get_source_docs()
                for filename, content in docs:
                    if filename in source_files:
                        snippets = builder._gather_keyword_content(docs, keyword)
                        if snippets:
                            relevant_sections.append(f"### From {kb_name}/{filename}\n\n{snippets[:1500]}")
            
            if not relevant_sections:
                continue
            
            # Build merged page
            merged_content = '\n\n'.join(relevant_sections[:5])
            sources_list = []
            for kb_name, files in kb_sources.items():
                for f in files:
                    sources_list.append(f"- {kb_name}/{f}")
            
            page = f"""---
title: "{keyword}"
category: concept
kbs: {len(kb_sources)}
sources: {sum(len(v) for v in kb_sources.values())}
---

# {keyword}

{merged_content}

## Sources

{chr(10).join(sources_list)}
"""
            page_file.write_text(page, encoding="utf-8")
            concept_count += 1
        
        # Step 3: Add internal links
        link_count = self._add_internal_links(all_keywords)
        
        # Step 4: Generate index
        self._generate_index(all_keywords)
        
        stats = {
            "pages": concept_count + 1,
            "keywords": len(all_keywords),
            "links": link_count,
            "kbs": len(self.kb_names),
        }
        print(f"[CrossWiki] Built: {stats}", file=sys.stderr)
        return stats
    
    def _add_internal_links(self, all_keywords: Dict[str, Dict[str, List[str]]]) -> int:
        """Add internal links between cross-KB wiki pages."""
        link_count = 0
        keyword_pages = {}
        
        skip_words = {
            'and', 'or', 'not', 'for', 'in', 'on', 'at', 'to', 'is', 'it',
            'the', 'a', 'an', 'of', 'by', 'as', 'be', 'we', 'you', 'this',
            'that', 'with', 'from', 'are', 'was', 'were', 'has', 'have',
            'true', 'false', 'none', 'any', 'also', 'get', 'set', 'use',
            'new', 'one', 'two', 'first', 'last', 'all', 'each', 'can',
            'data', 'type', 'types', 'file', 'files', 'path', 'paths',
            'see', 'more', 'below', 'above', 'here', 'there', 'where',
            'when', 'which', 'what', 'how', 'why', 'who', 'its', 'his',
            'her', 'our', 'their', 'my', 'your', 'if', 'then', 'else',
            'list', 'dict', 'int', 'str', 'float', 'bool', 'object',
            'note', 'notes', 'example', 'examples', 'returns', 'return',
            'start', 'end', 'size', 'html', 'run', 'in', 'on', 'or',
            'bat', 'lib', 'bin', 'src', 'pkg', 'opt', 'dev', 'etc',
        }
        
        for keyword in all_keywords:
            if keyword.lower() in skip_words or len(keyword) < 3:
                continue
            slug = _slugify(keyword)
            page_file = self.concepts_dir / f"{slug}.md"
            if page_file.exists():
                keyword_pages[keyword.lower()] = (keyword, page_file)
        
        for keyword, (display_name, page_file) in keyword_pages.items():
            try:
                content = page_file.read_text(encoding="utf-8")
            except Exception:
                continue
            
            parts = content.split('---', 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                body = parts[2]
            else:
                frontmatter = ""
                body = content
            
            modified = False
            for other_kw, (other_display, other_file) in keyword_pages.items():
                if other_kw == keyword:
                    continue
                if other_kw.lower() in skip_words or len(other_display) < 3:
                    continue
                    
                other_slug = _slugify(other_display)
                other_path = f"concepts/{other_slug}.md"
                
                escaped = re.escape(other_display)
                pattern = re.compile(
                    r'(?<!\[)(?<!`)(?<!\()(?<!href=")(?<!/)' + escaped + r'(?!\])(?!`)(?!\))(?!")(?!</)',
                    re.IGNORECASE
                )
                
                def replace_with_link(match):
                    nonlocal link_count, modified
                    link_count += 1
                    modified = True
                    return f'[{match.group(0)}]({other_path})'
                
                body = pattern.sub(replace_with_link, body, count=1)
            
            if modified:
                new_content = f"---{frontmatter}---{body}"
                page_file.write_text(new_content, encoding="utf-8")
        
        return link_count
    
    def _generate_index(self, all_keywords: Dict[str, Dict[str, List[str]]]) -> str:
        """Generate the cross-KB wiki index page."""
        kb_names_str = ', '.join(self.kb_names)
        
        # Group keywords by how many KBs they appear in
        multi_kb = {k: v for k, v in all_keywords.items() if len(v) > 1}
        single_kb = {k: v for k, v in all_keywords.items() if len(v) == 1}
        
        multi_links = '\n'.join(
            f"- [{k}](concepts/{_slugify(k)}.md) *({', '.join(v.keys())})*"
            for k, v in sorted(multi_kb.items())[:100]
        )
        
        # Group single-KB keywords by KB
        kb_groups = {}
        for k, v in single_kb.items():
            kb_name = list(v.keys())[0]
            if kb_name not in kb_groups:
                kb_groups[kb_name] = []
            kb_groups[kb_name].append(k)
        
        kb_sections = '\n'.join(
            f"\n### {kb_name}\n\n" + '\n'.join(
                f"- [{k}](concepts/{_slugify(k)}.md)"
                for k in sorted(ks)[:50]
            )
            for kb_name, ks in sorted(kb_groups.items())
        )
        
        index = f"""# Cross-KB Wiki

Unified wiki across: **{kb_names_str}**

## Shared Concepts (across multiple knowledge bases)

{multi_links or '*No shared concepts detected*'}

## KB-Specific Concepts

{kb_sections}

---
*Generated by GangDan Cross-KB Wiki Builder*
"""
        index_file = self.cross_wiki_dir / "index.md"
        index_file.write_text(index, encoding="utf-8")
        return index
    
    def get_wiki_pages(self) -> List[Dict[str, str]]:
        """Get list of all cross-KB wiki pages."""
        pages = []
        if not self.cross_wiki_dir.exists():
            return pages
        
        index_file = self.cross_wiki_dir / "index.md"
        if index_file.exists():
            pages.append({
                "title": "Cross-KB Wiki",
                "path": "index.md",
                "category": "index",
            })
        
        if self.concepts_dir.exists():
            for page_file in sorted(self.concepts_dir.glob("*.md")):
                try:
                    content = page_file.read_text(encoding="utf-8")
                    title = page_file.stem.replace('-', ' ').title()
                    match = re.search(r'^title:\s*"(.+?)"', content, re.MULTILINE)
                    if match:
                        title = match.group(1)
                    else:
                        match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
                        if match:
                            title = match.group(1)
                    
                    pages.append({
                        "title": title,
                        "path": f"concepts/{page_file.name}",
                        "category": "concept",
                    })
                except Exception:
                    pass
        
        return pages
    
    def get_wiki_page(self, page_path: str) -> Optional[str]:
        """Get content of a specific cross-KB wiki page."""
        full_path = (self.cross_wiki_dir / page_path).resolve()
        if not str(full_path).startswith(str(self.cross_wiki_dir.resolve())):
            return None
        if full_path.exists():
            return full_path.read_text(encoding="utf-8")
        return None
    
    def wiki_exists(self) -> bool:
        """Check if cross-KB wiki has been generated."""
        return (self.cross_wiki_dir / "index.md").exists()


def _slugify(text: str) -> str:
    """Convert text to a filename-safe slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')
