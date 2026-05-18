"""Web search using DuckDuckGo."""

from __future__ import annotations

import re
from typing import Dict, List
from urllib.parse import parse_qs, unquote

import requests

from gangdan_refined.core.config import get_proxies


class WebSearcher:
    """Web search using DuckDuckGo HTML interface."""

    def __init__(self):
        self._timeout = 15
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        })

    def search(self, query: str, num_results: int = 5) -> List[Dict]:
        results = []
        proxies = get_proxies()
        try:
            url = "https://html.duckduckgo.com/html/"
            resp = self._session.post(url, data={"q": query}, timeout=self._timeout, proxies=proxies)
            resp.raise_for_status()
            pattern = re.compile(
                r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>.*?'
                r'<a[^>]*class="result__snippet"[^>]*>([^<]*)</a>', re.DOTALL,
            )
            for match in pattern.finditer(resp.text):
                if len(results) >= num_results:
                    break
                link, title, snippet = match.groups()
                if "uddg=" in link:
                    parsed = parse_qs(link.split("?")[-1])
                    link = unquote(parsed.get("uddg", [link])[0])
                results.append({"title": title.strip(), "url": link, "snippet": snippet.strip()[:200]})
        except Exception:
            pass
        return results
