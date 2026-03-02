"""Web search integration."""

import re
import sys
from typing import List, Dict

import requests

from gangdan.core.config import get_proxies


class WebSearcher:
    """Web search using DuckDuckGo."""
    
    def __init__(self):
        self._timeout = 15
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        })
    
    def _get_proxies(self):
        return get_proxies()
    
    def search(self, query: str, num_results: int = 5) -> List[Dict]:
        """Search DuckDuckGo for results."""
        results = []
        proxies = self._get_proxies()
        
        if proxies:
            print(f"[WebSearch] Using proxy: {proxies.get('http', 'N/A')}", file=sys.stderr)
        
        try:
            url = "https://html.duckduckgo.com/html/"
            resp = self._session.post(url, data={"q": query}, timeout=self._timeout, proxies=proxies)
            resp.raise_for_status()
            
            pattern = re.compile(
                r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>.*?'
                r'<a[^>]*class="result__snippet"[^>]*>([^<]*)</a>',
                re.DOTALL
            )
            
            for match in pattern.finditer(resp.text):
                if len(results) >= num_results:
                    break
                link, title, snippet = match.groups()
                if "uddg=" in link:
                    from urllib.parse import unquote, parse_qs
                    parsed = parse_qs(link.split("?")[-1])
                    link = unquote(parsed.get("uddg", [link])[0])
                
                results.append({
                    "title": title.strip(),
                    "url": link,
                    "snippet": snippet.strip()[:200],
                })
        except Exception as e:
            print(f"[WebSearch] DuckDuckGo error: {e}", file=sys.stderr)
        
        return results
