"""Web search integration."""

from __future__ import annotations

import re
import sys
from typing import Dict, List
from urllib.parse import parse_qs, unquote

import requests

from gangdan.core.config import get_proxies


class WebSearcher:
    """Web search using DuckDuckGo HTML interface."""

    def __init__(self) -> None:
        self._timeout = 15
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        )

    def _get_proxies(self) -> Dict[str, str] | None:
        """Get proxy configuration."""
        return get_proxies()

    def search(self, query: str, num_results: int = 5) -> List[Dict]:
        """Search DuckDuckGo for results.

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
        results: List[Dict] = []
        proxies = self._get_proxies()

        if proxies:
            print(
                f"[WebSearch] Using proxy: {proxies.get('http', 'N/A')}",
                file=sys.stderr,
            )

        try:
            url = "https://html.duckduckgo.com/html/"
            response = self._session.post(
                url,
                data={"q": query},
                timeout=self._timeout,
                proxies=proxies,
            )
            response.raise_for_status()

            pattern = re.compile(
                r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>.*?'
                r'<a[^>]*class="result__snippet"[^>]*>([^<]*)</a>',
                re.DOTALL,
            )

            for match in pattern.finditer(response.text):
                if len(results) >= num_results:
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
        except requests.RequestException as e:
            print(f"[WebSearch] DuckDuckGo network error: {e}", file=sys.stderr)
        except re.error as e:
            print(f"[WebSearch] Regex parsing error: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[WebSearch] DuckDuckGo error: {e}", file=sys.stderr)

        return results
