"""arXiv full-text fetcher with multiple fallback sources.

Reference: DeepScientist's multi-layer arXiv fallback strategy.
Fallback order:
1. AlphaXiv overview: https://www.alphaxiv.org/overview/{id}.md
2. AlphaXiv full: https://www.alphaxiv.org/abs/{id}.md
3. arXiv HTML: https://arxiv.org/html/{id}
4. ar5iv Labs: https://ar5iv.labs.arxiv.org/html/{id}
5. ar5iv: https://ar5iv.org/html/{id}
6. arXiv abstract: https://arxiv.org/abs/{id}
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import requests

from gangdan.core.config import get_proxies
from gangdan.core.research_models import ArxivFullText, PaperMetadata

logger = logging.getLogger(__name__)


class ArxivFullTextFetcher:
    """Fetch full text from arXiv with multiple fallback sources.

    Parameters
    ----------
    timeout : int
        HTTP timeout in seconds.
    """

    SOURCES: List[Tuple[str, Callable[[str], str], str]] = [
        ("alphaxiv_overview", lambda aid: f"https://www.alphaxiv.org/overview/{aid}.md", "markdown"),
        ("alphaxiv_full", lambda aid: f"https://www.alphaxiv.org/abs/{aid}.md", "markdown"),
        ("arxiv_html", lambda aid: f"https://arxiv.org/html/{aid}", "html"),
        ("ar5iv_labs", lambda aid: f"https://ar5iv.labs.arxiv.org/html/{aid}", "html"),
        ("ar5iv", lambda aid: f"https://ar5iv.org/html/{aid}", "html"),
        ("arxiv_abstract", lambda aid: f"https://arxiv.org/abs/{aid}", "html"),
    ]

    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": "GangDan/1.0 (https://github.com/cycleuser/GangDan)"}
        )

    def fetch_full_text(self, arxiv_id: str) -> ArxivFullText:
        """Try each source in order, return first successful result.

        Parameters
        ----------
        arxiv_id : str
            arXiv identifier (e.g., '2301.12345').

        Returns
        -------
        ArxivFullText
            Full text content with source info.
        """
        arxiv_id = self._normalize_id(arxiv_id)
        if not arxiv_id:
            return ArxivFullText(arxiv_id="", error="Invalid arXiv ID")

        for source_name, url_func, content_type in self.SOURCES:
            try:
                result = self._try_fetch(arxiv_id, source_name, url_func, content_type)
                if result and result.content:
                    logger.info("[ArxivFullText] Got content from %s for %s", source_name, arxiv_id)
                    return result
            except Exception as e:
                logger.debug("[ArxivFullText] %s failed for %s: %s", source_name, arxiv_id, e)
                continue

        logger.warning("[ArxivFullText] All sources failed for %s", arxiv_id)
        return ArxivFullText(arxiv_id=arxiv_id, source="none", error="All sources failed")

    def _try_fetch(
        self,
        arxiv_id: str,
        source_name: str,
        url_func: Callable[[str], str],
        content_type: str,
    ) -> Optional[ArxivFullText]:
        """Attempt to fetch from a single source.

        Parameters
        ----------
        arxiv_id : str
            Normalized arXiv ID.
        source_name : str
            Name of the source.
        url_func : Callable
            Function to generate URL from arXiv ID.
        content_type : str
            Expected content type.

        Returns
        -------
        ArxivFullText or None
            Result if successful, None otherwise.
        """
        url = url_func(arxiv_id)
        proxies = get_proxies()
        resp = self._session.get(url, timeout=self.timeout, proxies=proxies)
        resp.raise_for_status()

        content = resp.text
        if not content or len(content) < 100:
            return None

        if source_name.startswith("alphaxiv"):
            content = self._clean_markdown(content)
        elif source_name == "arxiv_abstract":
            content = self._extract_abstract_html(content)

        return ArxivFullText(
            arxiv_id=arxiv_id,
            content=content,
            source=source_name,
            content_type=content_type,
        )

    def fetch_metadata(self, arxiv_id: str) -> Optional[PaperMetadata]:
        """Fetch paper metadata from arXiv API.

        Parameters
        ----------
        arxiv_id : str
            arXiv identifier.

        Returns
        -------
        PaperMetadata or None
            Paper metadata if found.
        """
        from gangdan.core.research_searcher import ArxivFetcher

        fetcher = ArxivFetcher()
        papers = fetcher.search(arxiv_id)
        if papers:
            return papers[0]
        return None

    @staticmethod
    def _normalize_id(arxiv_id: str) -> str:
        """Normalize arXiv ID to standard format.

        Parameters
        ----------
        arxiv_id : str
            Raw arXiv ID string.

        Returns
        -------
        str
            Normalized ID (e.g., '2301.12345').
        """
        arxiv_id = arxiv_id.strip()
        match = re.search(r"(\d{4}\.\d+)", arxiv_id)
        if match:
            return match.group(1)
        if re.match(r"^\d{4}\.\d+$", arxiv_id):
            return arxiv_id
        return ""

    @staticmethod
    def _clean_markdown(content: str) -> str:
        """Clean AlphaXiv markdown content.

        Parameters
        ----------
        content : str
            Raw markdown content.

        Returns
        -------
        str
            Cleaned markdown.
        """
        content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
        lines = content.split("\n")
        cleaned = []
        for line in lines:
            if line.strip():
                cleaned.append(line)
        return "\n".join(cleaned)

    @staticmethod
    def _extract_abstract_html(html: str) -> str:
        """Extract abstract text from arXiv abstract HTML page.

        Parameters
        ----------
        html : str
            Raw HTML content.

        Returns
        -------
        str
            Extracted abstract text.
        """
        match = re.search(r"<abstract[^>]*>(.*?)</abstract>", html, re.DOTALL)
        if match:
            text = re.sub(r"<[^>]+>", "", match.group(1))
            return text.strip()
        return ""
