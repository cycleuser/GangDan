"""Web page fetcher for GangDan Refined.

Downloads HTML pages and extracts readable text content.
Supports link discovery from search results to enrich research context.

Inspired by llm_wiki's source ingestion and mywiki's content extraction.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# Default user-agent for fetching
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

FETCH_TIMEOUT = 15
MAX_PAGE_SIZE = 1_000_000   # 1MB max
MAX_FETCH_COUNT = 5         # max sources to fetch per request


class WebFetcher:
    """Fetch and extract readable text from web pages.

    Attributes
    ----------
    timeout : int
        HTTP request timeout.
    max_size : int
        Maximum page size in bytes.
    """

    def __init__(self, timeout: int = FETCH_TIMEOUT, max_size: int = MAX_PAGE_SIZE) -> None:
        self.timeout = timeout
        self.max_size = max_size
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
        })

    def fetch(self, url: str) -> Tuple[str, str]:
        """Fetch a page and return (text_content, error).

        Parameters
        ----------
        url : str
            URL to fetch.

        Returns
        -------
        Tuple[str, str]
            (extracted_text, error_message). Error is empty on success.
        """
        try:
            resp = self._session.get(
                url,
                timeout=self.timeout,
                stream=True,
                allow_redirects=True,
            )
            resp.raise_for_status()

            # Check content type
            ct = resp.headers.get("Content-Type", "")
            if "text/html" not in ct and "text/plain" not in ct:
                return "", f"Non-HTML content type: {ct}"

            # Read up to max_size
            chunks = []
            total = 0
            for chunk in resp.iter_content(chunk_size=8192, decode_unicode=True):
                if isinstance(chunk, bytes):
                    chunk = chunk.decode("utf-8", errors="replace")
                chunks.append(chunk)
                total += len(chunk)
                if total >= self.max_size:
                    break
            html = "".join(chunks)[:self.max_size]

            text = self._extract_text(html)
            if len(text) < 50:
                return "", "Page too short or no readable content"

            return text[:20000], ""  # Cap at 20k chars

        except requests.RequestException as e:
            logger.debug("WebFetcher: %s -> %s", url, e)
            return "", str(e)
        except Exception as e:
            return "", str(e)

    def fetch_many(self, urls: List[str]) -> List[Dict[str, str]]:
        """Fetch multiple URLs and return results.

        Parameters
        ----------
        urls : List[str]
            URLs to fetch.

        Returns
        -------
        List[dict]
            Each result has keys: url, text, error, size.
        """
        results = []
        for url in urls[:MAX_FETCH_COUNT]:
            t0 = time.time()
            text, error = self.fetch(url)
            results.append({
                "url": url,
                "text": text,
                "error": error,
                "size": len(text),
                "time": round(time.time() - t0, 2),
            })
            if len(results) >= MAX_FETCH_COUNT:
                break
        return results

    def discover_and_fetch(
        self,
        search_results: List[dict],
    ) -> List[Dict[str, str]]:
        """From search results, discover and fetch top pages.

        Parameters
        ----------
        search_results : List[dict]
            Search results with 'url' key.

        Returns
        -------
        List[dict]
            Fetched page contents.
        """
        urls = [r.get("url", "") for r in search_results if r.get("url")]
        return self.fetch_many(urls)

    @staticmethod
    def _extract_text(html: str) -> str:
        """Extract readable text from HTML.

        Uses regex-based approach to strip tags and extract meaningful content.
        Falls back gracefully.
        """
        text = html

        # Remove script and style blocks
        text = re.sub(r'<script[^>]*>.*?</script>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<head[^>]*>.*?</head>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<nav[^>]*>.*?</nav>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<footer[^>]*>.*?</footer>', ' ', text, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)

        # Decode HTML entities
        text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        text = text.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')

        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        # Remove very short lines (likely navigation/boilerplate)
        lines = text.split('. ')
        meaningful = [l for l in lines if len(l.split()) > 4]
        return '. '.join(meaningful) if meaningful else text


# Singleton
_fetcher: Optional[WebFetcher] = None


def get_fetcher() -> WebFetcher:
    global _fetcher
    if _fetcher is None:
        _fetcher = WebFetcher()
    return _fetcher
