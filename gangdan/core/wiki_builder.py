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
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass, field

from gangdan.core.config import CONFIG, DOCS_DIR, t
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


class WikiBuilder:
    """Builds and maintains wiki pages for a knowledge base."""

    def __init__(self, kb_name: str, ollama: Optional[OllamaClient] = None):
        self.kb_name = kb_name
        self.kb_dir = DOCS_DIR / kb_name
        self.wiki_dir = self.kb_dir / "wiki"
        self.concepts_dir = self.wiki_dir / "concepts"
        self.entities_dir = self.wiki_dir / "entities"
        self._llm_client = None
        self._model_name = None

    def _ensure_dirs(self):
        """Create wiki directory structure."""
        self.wiki_dir.mkdir(parents=True, exist_ok=True)
        self.concepts_dir.mkdir(exist_ok=True)
        self.entities_dir.mkdir(exist_ok=True)

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

    def generate_wiki(self, force: bool = False) -> Dict[str, int]:
        """Generate wiki pages for the entire KB.
        
        Parameters
        ----------
        force : bool
            If True, regenerate even if wiki already exists.
            
        Returns
        -------
        Dict[str, int]
            Statistics: {'pages': N, 'keywords': M, 'links': L}
        """
        self._ensure_dirs()
        
        docs = self._get_source_docs()
        if not docs:
            return {"pages": 0, "keywords": 0, "links": 0}

        print(f"[Wiki] Building wiki for '{self.kb_name}' from {len(docs)} documents", file=sys.stderr)

        # Step 1: Extract keywords from all documents
        all_keywords: Dict[str, List[str]] = {}  # keyword -> list of source files
        doc_keywords: Dict[str, List[str]] = {}  # filename -> keywords
        
        for filename, content in docs:
            kws = self.extract_keywords(content)
            doc_keywords[filename] = kws
            for kw in kws:
                if kw not in all_keywords:
                    all_keywords[kw] = []
                all_keywords[kw].append(filename)

        # Step 2: Generate concept pages
        concept_pages = 0
        for keyword, sources in all_keywords.items():
            page_file = self.concepts_dir / f"{self._slugify(keyword)}.md"
            if page_file.exists() and not force:
                concept_pages += 1
                continue
            
            # Gather relevant content for this keyword
            relevant_text = self._gather_keyword_content(docs, keyword)
            
            # Generate page content
            page_content = self._generate_concept_page(keyword, relevant_text, sources)
            page_file.write_text(page_content, encoding="utf-8")
            concept_pages += 1

        # Step 3: Generate overview page
        overview = self._generate_overiew(docs, all_keywords)
        overview_file = self.wiki_dir / "index.md"
        overview_file.write_text(overview, encoding="utf-8")

        # Step 4: Add internal links to all pages
        link_count = self._add_internal_links(all_keywords)

        stats = {
            "pages": concept_pages + 1,  # +1 for index
            "keywords": len(all_keywords),
            "links": link_count,
        }
        print(f"[Wiki] Built: {stats}", file=sys.stderr)
        return stats

    def _gather_keyword_content(self, docs: List[Tuple[str, str]], keyword: str) -> str:
        """Gather all content related to a keyword from source documents."""
        snippets = []
        for filename, content in docs:
            # Find paragraphs/sections mentioning the keyword
            lines = content.split('\n')
            current_section = ""
            for line in lines:
                if line.startswith('#'):
                    current_section = line
                if keyword.lower() in line.lower():
                    # Include surrounding context
                    idx = lines.index(line)
                    start = max(0, idx - 3)
                    end = min(len(lines), idx + 10)
                    context = '\n'.join(lines[start:end])
                    snippets.append(f"From {filename} ({current_section}):\n{context}")
                    if len(snippets) >= 5:
                        break
            if len(snippets) >= 5:
                break
        return '\n\n---\n\n'.join(snippets[:5])

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
        full_path = self.wiki_dir / page_path
        if full_path.exists():
            return full_path.read_text(encoding="utf-8")
        return None

    def wiki_exists(self) -> bool:
        """Check if wiki has been generated for this KB."""
        return (self.wiki_dir / "index.md").exists()
