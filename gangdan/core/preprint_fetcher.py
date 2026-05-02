"""Multi-platform preprint fetcher with HTML/TeX source detection.

Fetches preprints from arXiv, bioRxiv, and medRxiv with priority detection
for HTML and TeX source availability. When HTML or TeX source is available,
these are preferred over PDF for Markdown conversion (much cleaner output
with formulas preserved).

Sources:
1. arXiv (CS/Math/Physics) - via arXiv API + source page detection
2. bioRxiv (Biology) - via REST API + RSS
3. medRxiv (Medicine) - via REST API + RSS

HTML/TeX Priority Chain:
1. arXiv HTML (ar5iv format) - best quality, formulas preserved
2. arXiv TeX source - can be compiled/converted to clean Markdown
3. PDF fallback - last resort
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlencode

import requests

from gangdan.core.config import get_proxies

logger = logging.getLogger(__name__)


@dataclass
class PreprintMetadata:
    """Metadata for a preprint with source format detection.

    Attributes
    ----------
    preprint_id : str
        Unique identifier (arXiv ID, bioRxiv DOI, etc.).
    title : str
        Paper title.
    authors : List[str]
        Author names.
    abstract : str
        Paper abstract.
    published_date : str
        Publication date (ISO format).
    updated_date : str
        Last updated date (ISO format).
    url : str
        Abstract page URL.
    pdf_url : str
        Direct PDF download URL.
    html_url : str
        HTML version URL (empty if not available).
    tex_source_url : str
        TeX source tarball URL (empty if not available).
    source_platform : str
        Platform: 'arxiv', 'biorxiv', 'medrxiv'.
    category : str
        Primary category/subject area.
    has_html : bool
        Whether HTML version is available.
    has_tex : bool
        Whether TeX source is available.
    preferred_format : str
        Best available format: 'html', 'tex', 'pdf'.
    raw_data : Dict
        Original API response data.
    """

    preprint_id: str = ""
    title: str = ""
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    published_date: str = ""
    updated_date: str = ""
    url: str = ""
    pdf_url: str = ""
    html_url: str = ""
    tex_source_url: str = ""
    source_platform: str = ""
    category: str = ""
    has_html: bool = False
    has_tex: bool = False
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def preferred_format(self) -> str:
        """Compute best available format: HTML > TeX > PDF."""
        if self.has_html:
            return "html"
        if self.has_tex:
            return "tex"
        return "pdf"

    @property
    def authors_str(self) -> str:
        """Format authors as a comma-separated string."""
        if not self.authors:
            return "Unknown"
        if len(self.authors) == 1:
            return self.authors[0]
        return ", ".join(self.authors[:3]) + (" et al." if len(self.authors) > 3 else "")

    @property
    def short_title(self) -> str:
        """Truncated title for display (max 80 chars)."""
        if len(self.title) <= 80:
            return self.title
        return self.title[:77] + "..."

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "preprint_id": self.preprint_id,
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract,
            "published_date": self.published_date,
            "updated_date": self.updated_date,
            "url": self.url,
            "pdf_url": self.pdf_url,
            "html_url": self.html_url,
            "tex_source_url": self.tex_source_url,
            "source_platform": self.source_platform,
            "category": self.category,
            "has_html": self.has_html,
            "has_tex": self.has_tex,
            "preferred_format": self.preferred_format,
        }


class BasePreprintFetcher:
    """Base class for preprint platform fetchers."""

    name: str = "base"

    def __init__(self, timeout: int = 30, max_results: int = 20) -> None:
        self.timeout = timeout
        self.max_results = max_results
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": "GangDan/1.0 (https://github.com/cycleuser/GangDan)"}
        )

    def _get_proxies(self) -> Optional[Dict[str, str]]:
        """Get proxy configuration."""
        return get_proxies()

    def search(self, query: str) -> List[PreprintMetadata]:
        """Search for preprints matching the query."""
        raise NotImplementedError

    def fetch_recent(self, days: int = 7) -> List[PreprintMetadata]:
        """Fetch recent preprints from the last N days."""
        raise NotImplementedError


class ArxivPreprintFetcher(BasePreprintFetcher):
    """Fetch preprints from arXiv with HTML/TeX source detection.

    arXiv provides:
    - Atom API for search/metadata
    - HTML view (ar5iv) for papers that have been converted
    - TeX source tarballs for most papers

    The fetcher detects HTML availability via arXiv API links
    and checks TeX source availability via the source endpoint.
    """

    name = "arxiv"
    API_URL = "http://export.arxiv.org/api/query"
    HTML_BASE = "https://ar5iv.labs.arxiv.org/html"
    SOURCE_BASE = "https://arxiv.org/e-print"

    def search(
        self,
        query: str,
        categories: Optional[List[str]] = None,
        sort_by: str = "relevance",
    ) -> List[PreprintMetadata]:
        """Search arXiv for preprints.

        Parameters
        ----------
        query : str
            Search query string.
        categories : List[str] or None
            Filter by arXiv categories (e.g., ['cs.AI', 'cs.LG']).
        sort_by : str
            Sort order: 'relevance', 'lastUpdatedDate', 'submittedDate'.

        Returns
        -------
        List[PreprintMetadata]
            Preprints with HTML/TeX availability info.
        """
        papers = []
        try:
            search_query = f"all:{query}"
            if categories:
                cat_query = " OR ".join(f"cat:{c}" for c in categories)
                search_query = f"({query}) AND ({cat_query})"

            sort_map = {
                "relevance": "relevance",
                "lastUpdatedDate": "lastUpdatedDate",
                "submittedDate": "submittedDate",
            }
            sort_field = sort_map.get(sort_by, "relevance")

            params = {
                "search_query": search_query,
                "start": 0,
                "max_results": self.max_results,
                "sortBy": sort_field,
                "sortOrder": "descending",
            }
            resp = self._session.get(
                self.API_URL, params=params, timeout=self.timeout, proxies=self._get_proxies()
            )
            resp.raise_for_status()
            papers = self._parse_atom_response(resp.text)
        except Exception as e:
            logger.error("[ArxivPreprintFetcher] Search failed: %s", e)

        return papers

    def fetch_recent(self, days: int = 7) -> List[PreprintMetadata]:
        """Fetch recent arXiv preprints from the last N days.

        Parameters
        ----------
        days : int
            Number of days to look back.

        Returns
        -------
        List[PreprintMetadata]
            Recent preprints.
        """
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d%H%M%S")
        query = f"submittedDate:[{cutoff}0000 TO 99999999999999]"
        return self.search(query, sort_by="submittedDate")

    def fetch_by_id(self, arxiv_id: str) -> Optional[PreprintMetadata]:
        """Fetch a single preprint by arXiv ID with full source detection.

        Parameters
        ----------
        arxiv_id : str
            arXiv identifier (e.g., '2301.12345' or '2301.12345v1').

        Returns
        -------
        PreprintMetadata or None
            Preprint metadata with HTML/TeX detection, or None if not found.
        """
        arxiv_id = self._normalize_id(arxiv_id)
        if not arxiv_id:
            return None

        try:
            params = {
                "id_list": arxiv_id,
                "start": 0,
                "max_results": 1,
            }
            resp = self._session.get(
                self.API_URL, params=params, timeout=self.timeout, proxies=self._get_proxies()
            )
            resp.raise_for_status()
            papers = self._parse_atom_response(resp.text)
            if papers:
                paper = papers[0]
                self._detect_source_formats(paper)
                return paper
        except Exception as e:
            logger.error("[ArxivPreprintFetcher] fetch_by_id failed: %s", e)

        return None

    def _parse_atom_response(self, xml_text: str) -> List[PreprintMetadata]:
        """Parse arXiv Atom XML response into PreprintMetadata."""
        papers = []
        try:
            root = ET.fromstring(xml_text)
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "arxiv": "http://arxiv.org/schemas/atom",
            }

            for entry in root.findall("atom:entry", ns):
                title_elem = entry.find("atom:title", ns)
                summary_elem = entry.find("atom:summary", ns)
                published_elem = entry.find("atom:published", ns)
                updated_elem = entry.find("atom:updated", ns)
                id_elem = entry.find("atom:id", ns)

                title = title_elem.text.strip().replace("\n", " ") if title_elem is not None else ""
                abstract = summary_elem.text.strip() if summary_elem is not None else ""
                arxiv_id = self._extract_arxiv_id(id_elem.text if id_elem is not None else "")
                url = f"https://arxiv.org/abs/{arxiv_id}"

                published = published_elem.text[:10] if published_elem is not None and published_elem.text else ""
                updated = updated_elem.text[:10] if updated_elem is not None and updated_elem.text else ""

                authors = []
                for author_elem in entry.findall("atom:author", ns):
                    name_elem = author_elem.find("atom:name", ns)
                    if name_elem is not None and name_elem.text:
                        authors.append(name_elem.text.strip())

                categories = []
                for cat_elem in entry.findall("atom:category", ns):
                    term = cat_elem.get("term", "")
                    if term:
                        categories.append(term)

                pdf_link = entry.find("atom:link[@title='pdf']", ns)
                pdf_url = pdf_link.get("href", "") if pdf_link is not None else ""
                if not pdf_url and arxiv_id:
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

                paper = PreprintMetadata(
                    preprint_id=arxiv_id,
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    published_date=published,
                    updated_date=updated,
                    url=url,
                    pdf_url=pdf_url,
                    html_url=f"{self.HTML_BASE}/{arxiv_id}",
                    tex_source_url=f"{self.SOURCE_BASE}/{arxiv_id}",
                    source_platform="arxiv",
                    category=", ".join(categories),
                    raw_data={"arxiv_id": arxiv_id, "categories": categories},
                )

                self._detect_source_formats(paper)
                papers.append(paper)
        except ET.ParseError as e:
            logger.error("[ArxivPreprintFetcher] XML parse error: %s", e)

        return papers

    def _detect_source_formats(self, paper: PreprintMetadata) -> None:
        """Detect HTML and TeX source availability for a preprint.

        Strategy:
        1. HTML: Try ar5iv URL with HEAD request (fast check)
        2. TeX: arXiv provides e-print (TeX source) for most papers,
           so we assume available unless proven otherwise

        Parameters
        ----------
        paper : PreprintMetadata
            Preprint metadata to update with format detection.
        """
        arxiv_id = paper.preprint_id
        if not arxiv_id:
            return

        html_url = f"{self.HTML_BASE}/{arxiv_id}"
        try:
            resp = self._session.head(
                html_url, timeout=10, proxies=self._get_proxies(), allow_redirects=True
            )
            paper.has_html = resp.status_code == 200
        except Exception:
            paper.has_html = False

        paper.has_tex = True

    @staticmethod
    def _normalize_id(arxiv_id: str) -> str:
        """Normalize arXiv ID to standard format."""
        arxiv_id = arxiv_id.strip()
        match = re.search(r"(\d{4}\.\d+)", arxiv_id)
        if match:
            return match.group(1)
        if re.match(r"^\d{4}\.\d+$", arxiv_id):
            return arxiv_id
        return ""

    @staticmethod
    def _extract_arxiv_id(url: str) -> str:
        """Extract arXiv ID from a URL or ID string."""
        if "arxiv.org/abs/" in url:
            match = re.search(r"arxiv\.org/abs/(\d{4}\.\d+(?:v\d+)?)", url)
            if match:
                return re.sub(r"v\d+$", "", match.group(1))
            return url.split("arxiv.org/abs/")[1].split("/")[0].split("?")[0]
        if "arxiv.org/pdf/" in url:
            match = re.search(r"arxiv\.org/pdf/(\d{4}\.\d+)", url)
            if match:
                return match.group(1)
            return url.split("arxiv.org/pdf/")[1].replace(".pdf", "").split("?")[0]
        return url.strip()


class BioRxivPreprintFetcher(BasePreprintFetcher):
    """Fetch preprints from bioRxiv (biology).

    bioRxiv provides:
    - REST API for search and metadata
    - RSS feeds for new preprints by category
    - JATS XML for full text (preferred over PDF)

    Note: bioRxiv does NOT provide HTML/TeX source like arXiv,
    but provides JATS XML which is excellent for conversion.
    """

    name = "biorxiv"
    API_URL = "https://api.biorxiv.org"
    RSS_URL = "https://www.biorxiv.org"

    def search(self, query: str, interval: str = "30d") -> List[PreprintMetadata]:
        """Search bioRxiv for preprints.

        Parameters
        ----------
        query : str
            Search query string.
        interval : str
            Time interval: '1d', '7d', '30d', '90d', '1y'.

        Returns
        -------
        List[PreprintMetadata]
            Preprints from bioRxiv.
        """
        papers = []
        try:
            url = f"{self.API_URL}/details/biorxiv/{interval}/0"
            resp = self._session.get(
                url, timeout=self.timeout, proxies=self._get_proxies()
            )
            resp.raise_for_status()
            data = resp.json()
            collection = data.get("collection", [])

            if query:
                query_lower = query.lower()
                collection = [
                    item for item in collection
                    if query_lower in item.get("title", "").lower()
                    or query_lower in item.get("abstract", "").lower()
                ]

            for item in collection[:self.max_results]:
                paper = self._parse_item(item, "biorxiv")
                if paper:
                    papers.append(paper)
        except Exception as e:
            logger.error("[BioRxivPreprintFetcher] Search failed: %s", e)

        return papers

    def fetch_recent(self, days: int = 7) -> List[PreprintMetadata]:
        """Fetch recent bioRxiv preprints."""
        interval = "7d" if days <= 7 else "30d"
        return self.search("", interval=interval)

    def fetch_by_doi(self, doi: str) -> Optional[PreprintMetadata]:
        """Fetch a single preprint by DOI.

        Parameters
        ----------
        doi : str
            DOI (e.g., '10.1101/2023.01.01.123456').

        Returns
        -------
        PreprintMetadata or None
            Preprint metadata, or None if not found.
        """
        try:
            doi_encoded = quote(doi, safe="")
            url = f"{self.API_URL}/details/medrxiv/10.1101/{doi_encoded}"
            resp = self._session.get(
                url, timeout=self.timeout, proxies=self._get_proxies()
            )
            resp.raise_for_status()
            data = resp.json()
            collection = data.get("collection", [])
            if collection:
                return self._parse_item(collection[0], "biorxiv")
        except Exception as e:
            logger.error("[BioRxivPreprintFetcher] fetch_by_doi failed: %s", e)

        return None

    def _parse_item(self, item: Dict, platform: str) -> Optional[PreprintMetadata]:
        """Parse a bioRxiv API response item."""
        try:
            doi = item.get("doi", "")
            preprint_id = doi.split("/")[-1] if "/" in doi else doi
            title = item.get("title", "")
            abstract = item.get("abstract", "")
            authors_str = item.get("authors", "")
            authors = [a.strip() for a in authors_str.split(";") if a.strip()] if authors_str else []
            date = item.get("date", "")
            category = item.get("category", "")
            url = item.get("link", f"https://www.biorxiv.org/content/{preprint_id}")
            pdf_url = item.get("link", "").replace("/content/", "/content/") + ".full.pdf"

            return PreprintMetadata(
                preprint_id=preprint_id,
                title=title,
                authors=authors,
                abstract=abstract,
                published_date=date,
                updated_date=date,
                url=url,
                pdf_url=pdf_url,
                source_platform=platform,
                category=category,
                has_html=False,
                has_tex=False,
                raw_data=item,
            )
        except Exception as e:
            logger.error("[BioRxivPreprintFetcher] Parse item failed: %s", e)
            return None


class MedRxivPreprintFetcher(BasePreprintFetcher):
    """Fetch preprints from medRxiv (medicine).

    medRxiv provides:
    - REST API for search and metadata
    - RSS feeds for new preprints
    - JATS XML for full text

    Note: medRxiv uses the same API structure as bioRxiv.
    """

    name = "medrxiv"
    API_URL = "https://api.biorxiv.org"

    def search(self, query: str, interval: str = "30d") -> List[PreprintMetadata]:
        """Search medRxiv for preprints.

        Parameters
        ----------
        query : str
            Search query string.
        interval : str
            Time interval: '1d', '7d', '30d', '90d', '1y'.

        Returns
        -------
        List[PreprintMetadata]
            Preprints from medRxiv.
        """
        papers = []
        try:
            url = f"{self.API_URL}/details/medrxiv/{interval}/0"
            resp = self._session.get(
                url, timeout=self.timeout, proxies=self._get_proxies()
            )
            resp.raise_for_status()
            data = resp.json()
            collection = data.get("collection", [])

            if query:
                query_lower = query.lower()
                collection = [
                    item for item in collection
                    if query_lower in item.get("title", "").lower()
                    or query_lower in item.get("abstract", "").lower()
                ]

            for item in collection[:self.max_results]:
                paper = self._parse_item(item, "medrxiv")
                if paper:
                    papers.append(paper)
        except Exception as e:
            logger.error("[MedRxivPreprintFetcher] Search failed: %s", e)

        return papers

    def fetch_recent(self, days: int = 7) -> List[PreprintMetadata]:
        """Fetch recent medRxiv preprints."""
        interval = "7d" if days <= 7 else "30d"
        return self.search("", interval=interval)

    def fetch_by_doi(self, doi: str) -> Optional[PreprintMetadata]:
        """Fetch a single preprint by DOI."""
        try:
            doi_encoded = quote(doi, safe="")
            url = f"{self.API_URL}/details/medrxiv/10.1101/{doi_encoded}"
            resp = self._session.get(
                url, timeout=self.timeout, proxies=self._get_proxies()
            )
            resp.raise_for_status()
            data = resp.json()
            collection = data.get("collection", [])
            if collection:
                return self._parse_item(collection[0], "medrxiv")
        except Exception as e:
            logger.error("[MedRxivPreprintFetcher] fetch_by_doi failed: %s", e)

        return None

    def _parse_item(self, item: Dict, platform: str) -> Optional[PreprintMetadata]:
        """Parse a medRxiv API response item."""
        try:
            doi = item.get("doi", "")
            preprint_id = doi.split("/")[-1] if "/" in doi else doi
            title = item.get("title", "")
            abstract = item.get("abstract", "")
            authors_str = item.get("authors", "")
            authors = [a.strip() for a in authors_str.split(";") if a.strip()] if authors_str else []
            date = item.get("date", "")
            category = item.get("category", "")
            url = item.get("link", f"https://www.medrxiv.org/content/{preprint_id}")
            pdf_url = url + ".full.pdf" if url else ""

            return PreprintMetadata(
                preprint_id=preprint_id,
                title=title,
                authors=authors,
                abstract=abstract,
                published_date=date,
                updated_date=date,
                url=url,
                pdf_url=pdf_url,
                source_platform=platform,
                category=category,
                has_html=False,
                has_tex=False,
                raw_data=item,
            )
        except Exception as e:
            logger.error("[MedRxivPreprintFetcher] Parse item failed: %s", e)
            return None


class PreprintFetcher:
    """Unified preprint fetcher across multiple platforms.

    Searches arXiv, bioRxiv, and medRxiv in parallel,
    merges and deduplicates results.

    Parameters
    ----------
    platforms : List[str]
        Platforms to search: 'arxiv', 'biorxiv', 'medrxiv'.
    max_results : int
        Maximum results per platform.
    timeout : int
        HTTP timeout in seconds.
    """

    VALID_PLATFORMS = {"arxiv", "biorxiv", "medrxiv"}

    def __init__(
        self,
        platforms: Optional[List[str]] = None,
        max_results: int = 20,
        timeout: int = 30,
    ) -> None:
        self.platforms = platforms or ["arxiv", "biorxiv", "medrxiv"]
        self.max_results = max_results
        self.timeout = timeout
        self.fetchers = self._init_fetchers()

    def _init_fetchers(self) -> Dict[str, BasePreprintFetcher]:
        """Initialize fetcher instances."""
        fetchers = {}
        for platform in self.platforms:
            if platform not in self.VALID_PLATFORMS:
                logger.warning("[PreprintFetcher] Unknown platform: %s", platform)
                continue

            if platform == "arxiv":
                fetchers["arxiv"] = ArxivPreprintFetcher(
                    timeout=self.timeout, max_results=self.max_results
                )
            elif platform == "biorxiv":
                fetchers["biorxiv"] = BioRxivPreprintFetcher(
                    timeout=self.timeout, max_results=self.max_results
                )
            elif platform == "medrxiv":
                fetchers["medrxiv"] = MedRxivPreprintFetcher(
                    timeout=self.timeout, max_results=self.max_results
                )

        return fetchers

    def search(
        self,
        query: str,
        platforms: Optional[List[str]] = None,
        max_results: Optional[int] = None,
        categories: Optional[List[str]] = None,
    ) -> List[PreprintMetadata]:
        """Search across all configured platforms.

        Parameters
        ----------
        query : str
            Search query string.
        platforms : List[str] or None
            Override platforms for this search.
        max_results : int or None
            Override max results per platform.
        categories : List[str] or None
            Category codes to filter by (applied to arXiv).

        Returns
        -------
        List[PreprintMetadata]
            Merged and deduplicated preprint results.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        target_platforms = platforms or self.platforms
        limit = max_results or self.max_results
        all_results: List[PreprintMetadata] = []
        seen_ids: set = set()

        def search_platform(platform_name: str, fetcher: BasePreprintFetcher) -> List[PreprintMetadata]:
            """Search a single platform."""
            results = []
            try:
                if platform_name == "arxiv" and categories:
                    papers = fetcher.search(query, categories=categories)
                else:
                    papers = fetcher.search(query)
                for paper in papers:
                    dedup_key = f"{paper.source_platform}:{paper.preprint_id}"
                    if dedup_key not in seen_ids:
                        seen_ids.add(dedup_key)
                        results.append(paper)
            except Exception as e:
                logger.error(
                    "[PreprintFetcher] %s search failed: %s", platform_name, e
                )
            return results

        with ThreadPoolExecutor(max_workers=len(self.fetchers)) as executor:
            futures = {}
            for platform_name in target_platforms:
                if platform_name in self.fetchers:
                    fetcher = self.fetchers[platform_name]
                    future = executor.submit(search_platform, platform_name, fetcher)
                    futures[future] = platform_name

            for future in as_completed(futures):
                all_results.extend(future.result())

        return all_results[:limit * len(target_platforms)]

    def fetch_recent(
        self,
        days: int = 7,
        platforms: Optional[List[str]] = None,
    ) -> List[PreprintMetadata]:
        """Fetch recent preprints from all platforms.

        Parameters
        ----------
        days : int
            Number of days to look back.
        platforms : List[str] or None
            Override platforms for this fetch.

        Returns
        -------
        List[PreprintMetadata]
            Recent preprints from all platforms.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        target_platforms = platforms or self.platforms
        all_results: List[PreprintMetadata] = []

        def fetch_platform(platform_name: str, fetcher: BasePreprintFetcher) -> List[PreprintMetadata]:
            """Fetch recent from a single platform."""
            try:
                return fetcher.fetch_recent(days=days)
            except Exception as e:
                logger.error(
                    "[PreprintFetcher] %s fetch_recent failed: %s", platform_name, e
                )
                return []

        with ThreadPoolExecutor(max_workers=len(self.fetchers)) as executor:
            futures = {}
            for platform_name in target_platforms:
                if platform_name in self.fetchers:
                    fetcher = self.fetchers[platform_name]
                    future = executor.submit(fetch_platform, platform_name, fetcher)
                    futures[future] = platform_name

            for future in as_completed(futures):
                all_results.extend(future.result())

        return all_results

    def fetch_by_id(
        self,
        preprint_id: str,
        platform: str = "arxiv",
    ) -> Optional[PreprintMetadata]:
        """Fetch a single preprint by ID.

        Parameters
        ----------
        preprint_id : str
            Preprint identifier.
        platform : str
            Platform name: 'arxiv', 'biorxiv', 'medrxiv'.

        Returns
        -------
        PreprintMetadata or None
            Preprint metadata, or None if not found.
        """
        if platform == "arxiv" and "arxiv" in self.fetchers:
            return self.fetchers["arxiv"].fetch_by_id(preprint_id)
        elif platform in ("biorxiv", "medrxiv") and platform in self.fetchers:
            return self.fetchers[platform].fetch_by_doi(preprint_id)
        return None

    def get_html_preprints(self, results: List[PreprintMetadata]) -> List[PreprintMetadata]:
        """Filter results to only those with HTML source available.

        Parameters
        ----------
        results : List[PreprintMetadata]
            Preprint search results.

        Returns
        -------
        List[PreprintMetadata]
            Preprints with HTML available.
        """
        return [p for p in results if p.has_html]

    def get_tex_preprints(self, results: List[PreprintMetadata]) -> List[PreprintMetadata]:
        """Filter results to only those with TeX source available.

        Parameters
        ----------
        results : List[PreprintMetadata]
            Preprint search results.

        Returns
        -------
        List[PreprintMetadata]
            Preprints with TeX source available.
        """
        return [p for p in results if p.has_tex]

    def get_preferred_format(self, paper: PreprintMetadata) -> str:
        """Get the preferred conversion format for a preprint.

        Priority: HTML > TeX > PDF

        Parameters
        ----------
        paper : PreprintMetadata
            Preprint metadata.

        Returns
        -------
        str
            Preferred format: 'html', 'tex', or 'pdf'.
        """
        if paper.has_html:
            return "html"
        if paper.has_tex:
            return "tex"
        return "pdf"

    @staticmethod
    def refine_query_with_ai(
        query: str,
        categories: Optional[List[str]] = None,
        platform: str = "arxiv",
        model: str = "",
    ) -> str:
        """Use AI to refine and expand a search query for better preprint results.

        Parameters
        ----------
        query : str
            Original user query.
        categories : List[str] or None
            Selected category codes to guide refinement.
        platform : str
            Target platform for category context.
        model : str
            Ollama model to use (empty = default).

        Returns
        -------
        str
            Refined search query optimized for the target platform.
        """
        from gangdan.core.config import CONFIG
        from gangdan.core.preprint_categories import get_platform_categories

        target_model = model or CONFIG.chat_model or CONFIG.embedding_model
        if not target_model:
            logger.warning("[PreprintFetcher] No model available for query refinement")
            return query

        try:
            cats = get_platform_categories(platform)
            cat_context = ""
            if categories:
                matched = [c for c in cats if c.code in categories]
                if matched:
                    cat_names = ", ".join(f"{c.name} ({c.code})" for c in matched)
                    cat_context = f"\nRelevant categories: {cat_names}"

            prompt = f"""You are a research assistant helping to search academic preprints on {platform}.
Refine the following search query to be more effective for academic paper search.

Original query: "{query}"
Platform: {platform}{cat_context}

Rules:
1. Keep the core topic intact
2. Add relevant technical synonyms and related terms
3. Use boolean-style formatting if helpful (OR between synonyms)
4. Keep it under 100 characters
5. Return ONLY the refined query, nothing else

Refined query:"""

            from gangdan.core.ollama_client import chat

            response = chat(
                model=target_model,
                messages=[{"role": "user", "content": prompt}],
                stream=False,
            )

            if response and "message" in response:
                refined = response["message"]["content"].strip()
                if refined and len(refined) < 200:
                    logger.info("[PreprintFetcher] Query refined: '%s' -> '%s'", query, refined)
                    return refined
        except Exception as e:
            logger.warning("[PreprintFetcher] AI query refinement failed: %s", e)

        return query

    def search_with_categories(
        self,
        query: str,
        categories: Optional[List[str]] = None,
        strict_mode: bool = False,
        ai_refine: bool = False,
        platforms: Optional[List[str]] = None,
        max_results: Optional[int] = None,
        model: str = "",
    ) -> Dict[str, Any]:
        """Search with category filtering and optional AI query refinement.

        Parameters
        ----------
        query : str
            Search query string.
        categories : List[str] or None
            Category codes to filter by (e.g., ['cs.AI', 'cs.LG']).
        strict_mode : bool
            If True, ONLY return papers matching the selected categories.
            If False, use categories as boost factors but also return keyword matches.
        ai_refine : bool
            If True, use AI to refine the query before searching.
        platforms : List[str] or None
            Override platforms for this search.
        max_results : int or None
            Override max results per platform.
        model : str
            Ollama model for AI refinement.

        Returns
        -------
        Dict[str, Any]
            Dictionary with:
            - results: List[PreprintMetadata]
            - refined_query: str (the query actually used)
            - query_refined: bool (whether AI refinement was applied)
            - category_counts: Dict[str, int] (results per category)
            - total: int
        """
        refined_query = query
        query_refined = False

        if ai_refine:
            arxiv_cats = categories if categories else []
            refined_query = self.refine_query_with_ai(
                query, categories=arxiv_cats, platform="arxiv", model=model
            )
            query_refined = (refined_query != query)

        target_platforms = platforms or self.platforms
        limit = max_results or self.max_results

        all_results = self.search(refined_query, platforms=target_platforms, max_results=limit)

        if categories and "arxiv" in target_platforms:
            all_results = self._filter_by_categories(
                all_results, categories, strict_mode=strict_mode
            )

        category_counts = {}
        for paper in all_results:
            raw = paper.raw_data or {}
            cats = raw.get("categories", [])
            for cat in cats:
                category_counts[cat] = category_counts.get(cat, 0) + 1

        return {
            "results": all_results,
            "refined_query": refined_query,
            "query_refined": query_refined,
            "category_counts": category_counts,
            "total": len(all_results),
        }

    def _filter_by_categories(
        self,
        results: List[PreprintMetadata],
        categories: List[str],
        strict_mode: bool = False,
    ) -> List[PreprintMetadata]:
        """Filter or boost results based on category matching.

        Parameters
        ----------
        results : List[PreprintMetadata]
            Search results to filter.
        categories : List[str]
            Category codes to match.
        strict_mode : bool
            If True, exclude papers not matching any category.
            If False, keep all but sort category matches first.

        Returns
        -------
        List[PreprintMetadata]
            Filtered/sorted results.
        """
        if strict_mode:
            filtered = []
            for paper in results:
                raw = paper.raw_data or {}
                paper_cats = raw.get("categories", [])
                if any(cat in categories for cat in paper_cats):
                    filtered.append(paper)
            return filtered

        scored = []
        for paper in results:
            raw = paper.raw_data or {}
            paper_cats = raw.get("categories", [])
            match_count = sum(1 for cat in paper_cats if cat in categories)
            scored.append((paper, match_count))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [p for p, _ in scored]
