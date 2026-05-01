"""Web search integration with multiple engine support.

Supports DuckDuckGo (free), Serper (Google via API), and Brave Search.
Uses an abstract engine pattern for easy extension.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from urllib.parse import parse_qs, unquote

import requests

from gangdan.core.config import get_proxies

logger = logging.getLogger(__name__)


class WebSearchEngine(ABC):
    """Abstract base class for web search engines."""

    @abstractmethod
    def search(self, query: str, max_results: int = 10) -> List[Dict]:
        """Search and return results.

        Parameters
        ----------
        query : str
            Search query string.
        max_results : int
            Maximum number of results to return.

        Returns
        -------
        List[Dict]
            List of results with 'title', 'url', and 'snippet' keys.
        """
        ...


class DuckDuckGoSearcher(WebSearchEngine):
    """DuckDuckGo HTML scraper (free, no API key needed)."""

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        )

    def search(self, query: str, max_results: int = 10) -> List[Dict]:
        """Search DuckDuckGo HTML interface."""
        results: List[Dict] = []
        proxies = get_proxies()

        try:
            url = "https://html.duckduckgo.com/html/"
            response = self._session.post(
                url,
                data={"q": query},
                timeout=self.timeout,
                proxies=proxies,
            )
            response.raise_for_status()

            pattern = re.compile(
                r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>.*?'
                r'<a[^>]*class="result__snippet"[^>]*>([^<]*)</a>',
                re.DOTALL,
            )

            for match in pattern.finditer(response.text):
                if len(results) >= max_results:
                    break

                link, title, snippet = match.groups()

                if "uddg=" in link:
                    parsed = parse_qs(link.split("?")[-1])
                    link = unquote(parsed.get("uddg", [link])[0])

                results.append(
                    {
                        "title": title.strip(),
                        "url": link,
                        "snippet": snippet.strip()[:200],
                    }
                )
        except Exception as e:
            logger.error("[DuckDuckGo] Search failed: %s", e)

        return results


class SerperSearcher(WebSearchEngine):
    """Google Search via Serper.dev API.

    Requires an API key from https://serper.dev.
    """

    def __init__(self, api_key: str, timeout: int = 15) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.api_url = "https://google.serper.dev/search"
        self._session = requests.Session()
        self._session.headers.update(
            {"X-API-KEY": api_key, "Content-Type": "application/json"}
        )

    def search(self, query: str, max_results: int = 10) -> List[Dict]:
        """Search Google via Serper API."""
        results: List[Dict] = []
        try:
            resp = self._session.post(
                self.api_url,
                json={"q": query, "num": max_results},
                timeout=self.timeout,
                proxies=get_proxies(),
            )
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("organic", [])[:max_results]:
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("link", ""),
                        "snippet": item.get("snippet", ""),
                    }
                )
        except Exception as e:
            logger.error("[Serper] Search failed: %s", e)

        return results


class BraveSearcher(WebSearchEngine):
    """Brave Search API.

    Requires an API key from https://brave.com/search/api/.
    """

    def __init__(self, api_key: str, timeout: int = 15) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.api_url = "https://api.search.brave.com/res/v1/web/search"
        self._session = requests.Session()
        self._session.headers.update(
            {"X-Subscription-Token": api_key, "Accept": "application/json"}
        )

    def search(self, query: str, max_results: int = 10) -> List[Dict]:
        """Search via Brave Search API."""
        results: List[Dict] = []
        try:
            resp = self._session.get(
                self.api_url,
                params={"q": query, "count": max_results},
                timeout=self.timeout,
                proxies=get_proxies(),
            )
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("web", {}).get("results", [])[:max_results]:
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("description", ""),
                    }
                )
        except Exception as e:
            logger.error("[Brave] Search failed: %s", e)

        return results


class WebSearcher:
    """Web search with configurable engine.

    Parameters
    ----------
    engine : str
        Search engine name: 'duckduckgo', 'serper', or 'brave'.
    serper_api_key : str
        API key for Serper (required if engine='serper').
    brave_api_key : str
        API key for Brave (required if engine='brave').
    """

    def __init__(
        self,
        engine: str = "duckduckgo",
        serper_api_key: str = "",
        brave_api_key: str = "",
    ) -> None:
        self._engine = self._create_engine(engine, serper_api_key, brave_api_key)

    @staticmethod
    def _create_engine(
        engine: str, serper_api_key: str, brave_api_key: str
    ) -> WebSearchEngine:
        """Create the appropriate search engine instance."""
        if engine == "serper" and serper_api_key:
            return SerperSearcher(api_key=serper_api_key)
        elif engine == "brave" and brave_api_key:
            return BraveSearcher(api_key=brave_api_key)
        else:
            if engine not in ("duckduckgo", "serper", "brave"):
                logger.warning("[WebSearcher] Unknown engine '%s', falling back to DuckDuckGo", engine)
            return DuckDuckGoSearcher()

    def search(self, query: str, num_results: int = 5) -> List[Dict]:
        """Search the web.

        Parameters
        ----------
        query : str
            Search query string.
        num_results : int
            Maximum number of results to return.

        Returns
        -------
        List[Dict]
            List of search results with title, url, and snippet.
        """
        return self._engine.search(query, max_results=num_results)
