"""Multi-source academic paper search aggregator.

This module provides a unified search interface across multiple academic
sources: arXiv, Semantic Scholar, CrossRef, PubMed, GitHub, OpenAlex, and DBLP.

Each source is implemented as a separate Fetcher class with its own
API client, rate limiting, and error handling. The ResearchSearcher
orchestrates parallel searches and merges/deduplicates results.
"""

from __future__ import annotations

import logging
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlencode

import requests

from gangdan.core.config import CONFIG, get_proxies
from gangdan.core.query_expander import ExpandedQuery
from gangdan.core.research_models import PaperMetadata, SearchResult
from gangdan.core.s2_cache import S2Cache

logger = logging.getLogger(__name__)


class BaseFetcher:
    """Base class for all academic search source fetchers.

    Subclasses must implement the search() method.
    """

    name: str = "base"

    def __init__(self, timeout: int = 15, max_results: int = 10) -> None:
        self.timeout = timeout
        self.max_results = max_results
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": "GangDan/1.0 (https://github.com/cycleuser/GangDan)"}
        )

    def _get_proxies(self) -> Optional[Dict[str, str]]:
        """Get proxy configuration."""
        return get_proxies()

    def search(self, query: str) -> List[PaperMetadata]:
        """Search this source for papers.

        Parameters
        ----------
        query : str
            Search query string.

        Returns
        -------
        List[PaperMetadata]
            List of papers found.
        """
        raise NotImplementedError


class ArxivFetcher(BaseFetcher):
    """Fetch papers from arXiv using the official API.

    Supports multiple fallback plans:
    1. arXiv API (Atom XML)
    2. arXiv HTML abstract page
    """

    name = "arxiv"
    API_URL = "http://export.arxiv.org/api/query"

    def search(self, query: str) -> List[PaperMetadata]:
        """Search arXiv for papers matching the query.

        Parameters
        ----------
        query : str
            Search query.

        Returns
        -------
        List[PaperMetadata]
            Papers found on arXiv.
        """
        papers = []
        try:
            params = {
                "search_query": f"all:{query}",
                "start": 0,
                "max_results": self.max_results,
                "sortBy": "relevance",
                "sortOrder": "descending",
            }
            resp = self._session.get(
                self.API_URL, params=params, timeout=self.timeout, proxies=self._get_proxies()
            )
            resp.raise_for_status()
            papers = self._parse_atom_response(resp.text)
        except Exception as e:
            logger.error("[ArxivFetcher] Search failed: %s", e)

        return papers

    def _parse_atom_response(self, xml_text: str) -> List[PaperMetadata]:
        """Parse arXiv Atom XML response.

        Parameters
        ----------
        xml_text : str
            Atom XML response text.

        Returns
        -------
        List[PaperMetadata]
            Parsed paper metadata.
        """
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
                id_elem = entry.find("atom:id", ns)
                link_elem = entry.find("atom:link[@rel='alternate']", ns)
                pdf_link = entry.find("atom:link[@title='pdf']", ns)

                title = title_elem.text.strip() if title_elem is not None else ""
                abstract = summary_elem.text.strip() if summary_elem is not None else ""
                arxiv_id = self._extract_arxiv_id(id_elem.text if id_elem is not None else "")
                url = link_elem.get("href", "") if link_elem is not None else ""
                pdf_url = pdf_link.get("href", "") if pdf_link is not None else ""

                year = 0
                if published_elem is not None and published_elem.text:
                    try:
                        year = int(published_elem.text[:4])
                    except (ValueError, TypeError):
                        pass

                authors = []
                for author_elem in entry.findall("atom:author", ns):
                    name_elem = author_elem.find("atom:name", ns)
                    if name_elem is not None and name_elem.text:
                        authors.append(name_elem.text.strip())

                papers.append(
                    PaperMetadata(
                        title=title,
                        authors=authors,
                        year=year,
                        abstract=abstract,
                        arxiv_id=arxiv_id,
                        url=url,
                        pdf_url=pdf_url or f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                        source="arxiv",
                        raw_data={"arxiv_id": arxiv_id},
                    )
                )
        except ET.ParseError as e:
            logger.error("[ArxivFetcher] XML parse error: %s", e)

        return papers

    @staticmethod
    def _extract_arxiv_id(url: str) -> str:
        """Extract arXiv ID from a URL or ID string.

        Parameters
        ----------
        url : str
            arXiv URL or ID string.

        Returns
        -------
        str
            Clean arXiv ID.
        """
        import re

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


class SemanticScholarFetcher(BaseFetcher):
    """Fetch papers from Semantic Scholar Graph API.

    Supports search with year filters, citation counts, and influential citations.
    Implements rate limiting and caching-friendly requests.
    """

    name = "semantic_scholar"
    API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    FIELDS = "title,authors,year,abstract,externalIds,url,isOpenAccess,openAccessPdf,citationCount,influentialCitationCount,venue,journal,tldr"

    def __init__(self, timeout: int = 15, max_results: int = 10, api_key: str = "", cache=None) -> None:
        super().__init__(timeout, max_results)
        self.api_key = api_key
        if api_key:
            self._session.headers.update({"x-api-key": api_key})
        self._cache = cache

    def search(self, query: str) -> List[PaperMetadata]:
        """Search Semantic Scholar for papers.

        Parameters
        ----------
        query : str
            Search query.

        Returns
        -------
        List[PaperMetadata]
            Papers found on Semantic Scholar.
        """
        papers = []
        try:
            params = {
                "query": query,
                "fields": self.FIELDS,
                "limit": self.max_results,
            }
            resp = self._session.get(
                self.API_URL, params=params, timeout=self.timeout, proxies=self._get_proxies()
            )
            resp.raise_for_status()
            data = resp.json()
            papers = self._parse_response(data.get("data", []))
        except Exception as e:
            logger.error("[SemanticScholarFetcher] Search failed: %s", e)

        return papers

    def _parse_response(self, items: List[Dict]) -> List[PaperMetadata]:
        """Parse Semantic Scholar API response.

        Parameters
        ----------
        items : List[Dict]
            API response items.

        Returns
        -------
        List[PaperMetadata]
            Parsed paper metadata.
        """
        papers = []
        for item in items:
            external_ids = item.get("externalIds", {}) or {}
            doi = external_ids.get("DOI", "")
            arxiv_id = external_ids.get("ArXiv", "")

            authors = []
            for author in item.get("authors", []) or []:
                name = author.get("name", "")
                if name:
                    authors.append(name)

            pdf_url = ""
            open_access = item.get("openAccessPdf", {}) or {}
            if open_access.get("url"):
                pdf_url = open_access["url"]

            papers.append(
                PaperMetadata(
                    title=item.get("title", ""),
                    authors=authors,
                    year=item.get("year", 0) or 0,
                    abstract=item.get("abstract", "") or "",
                    doi=doi,
                    arxiv_id=arxiv_id,
                    url=item.get("url", ""),
                    pdf_url=pdf_url,
                    source="semantic_scholar",
                    citations=item.get("citationCount", 0) or 0,
                    venue=item.get("venue", "") or "",
                    journal=(item.get("journal", {}) or {}).get("name", "") or "",
                    raw_data=item,
                )
            )
        return papers

    def get_paper(self, paper_id: str) -> Optional[PaperMetadata]:
        """Get a single paper by S2 ID, DOI, arXiv ID, or PMID.

        Parameters
        ----------
        paper_id : str
            Paper identifier (S2 ID, DOI, ArXiv:ID, or PMID:ID).

        Returns
        -------
        PaperMetadata or None
            Paper metadata if found.
        """
        cache_key = f"s2_paper:{paper_id}"
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        try:
            url = f"{self.BASE_URL}/paper/{paper_id}"
            params = {"fields": self.FIELDS}
            resp = self._session.get(
                url, params=params, timeout=self.timeout, proxies=self._get_proxies()
            )
            resp.raise_for_status()
            data = resp.json()
            papers = self._parse_response([data])
            result = papers[0] if papers else None
            if self._cache and result:
                self._cache.put(cache_key, result)
            return result
        except Exception as e:
            logger.error("[SemanticScholarFetcher] get_paper failed: %s", e)
            return None

    def get_references(self, paper_id: str, limit: int = 20) -> List[PaperMetadata]:
        """Get papers cited by this paper.

        Parameters
        ----------
        paper_id : str
            Paper identifier.
        limit : int
            Maximum number of references to return.

        Returns
        -------
        List[PaperMetadata]
            List of referenced papers.
        """
        return self._get_related(paper_id, "references", limit)

    def get_citations(self, paper_id: str, limit: int = 20) -> List[PaperMetadata]:
        """Get papers citing this paper.

        Parameters
        ----------
        paper_id : str
            Paper identifier.
        limit : int
            Maximum number of citations to return.

        Returns
        -------
        List[PaperMetadata]
            List of citing papers.
        """
        return self._get_related(paper_id, "citations", limit)

    def get_recommendations(self, paper_id: str, limit: int = 10) -> List[PaperMetadata]:
        """Get recommended similar papers.

        Parameters
        ----------
        paper_id : str
            Paper identifier.
        limit : int
            Maximum number of recommendations.

        Returns
        -------
        List[PaperMetadata]
            List of recommended papers.
        """
        cache_key = f"s2_recs:{paper_id}:{limit}"
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        papers = []
        try:
            url = f"{self.BASE_URL}/recommendations/v1/papers/forpaper/{paper_id}"
            params = {"limit": limit, "fields": self.FIELDS}
            resp = self._session.get(
                url, params=params, timeout=self.timeout, proxies=self._get_proxies()
            )
            resp.raise_for_status()
            data = resp.json()
            papers = self._parse_response(data.get("recommendedPapers", []))
            if self._cache:
                self._cache.put(cache_key, papers)
        except Exception as e:
            logger.error("[SemanticScholarFetcher] get_recommendations failed: %s", e)

        return papers

    def autocomplete(self, query: str, limit: int = 5) -> List[Dict]:
        """Get paper title autocomplete suggestions.

        Parameters
        ----------
        query : str
            Partial query string.
        limit : int
            Maximum number of suggestions.

        Returns
        -------
        List[Dict]
            List of suggestion dicts with 'title' and 'score'.
        """
        cache_key = f"s2_auto:{query}:{limit}"
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        suggestions = []
        try:
            url = f"{self.BASE_URL}/paper/autocomplete"
            params = {"q": query, "limit": limit}
            resp = self._session.get(
                url, params=params, timeout=self.timeout, proxies=self._get_proxies()
            )
            resp.raise_for_status()
            data = resp.json()
            suggestions = data.get("suggestions", [])
            if self._cache:
                self._cache.put(cache_key, suggestions)
        except Exception as e:
            logger.error("[SemanticScholarFetcher] autocomplete failed: %s", e)

        return suggestions

    def _get_related(self, paper_id: str, relation: str, limit: int) -> List[PaperMetadata]:
        """Get related papers (references or citations).

        Parameters
        ----------
        paper_id : str
            Paper identifier.
        relation : str
            'references' or 'citations'.
        limit : int
            Maximum number of results.

        Returns
        -------
        List[PaperMetadata]
            List of related papers.
        """
        cache_key = f"s2_{relation}:{paper_id}:{limit}"
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        papers = []
        try:
            url = f"{self.BASE_URL}/paper/{paper_id}/{relation}"
            params = {"limit": limit, "fields": self.FIELDS}
            resp = self._session.get(
                url, params=params, timeout=self.timeout, proxies=self._get_proxies()
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("data", []) or data.get("externalIds", [])
            papers = self._parse_response(items)
            if self._cache:
                self._cache.put(cache_key, papers)
        except Exception as e:
            logger.error("[SemanticScholarFetcher] get_%s failed: %s", relation, e)

        return papers


class CrossRefFetcher(BaseFetcher):
    """Fetch paper metadata from CrossRef Works API.

    Primarily used for DOI resolution and metadata enrichment.
    Requires an email address for polite API usage.
    """

    name = "crossref"
    API_URL = "https://api.crossref.org/works"

    def __init__(
        self, timeout: int = 15, max_results: int = 10, email: str = ""
    ) -> None:
        super().__init__(timeout, max_results)
        self.email = email
        if email:
            self._session.headers.update({"mailto": email})

    def search(self, query: str) -> List[PaperMetadata]:
        """Search CrossRef for papers.

        Parameters
        ----------
        query : str
            Search query.

        Returns
        -------
        List[PaperMetadata]
            Papers found on CrossRef.
        """
        papers = []
        try:
            params = {
                "query": query,
                "rows": self.max_results,
                "select": "title,author,abstract,DOI,url,published-print,published-online,container-title,is-referenced-by-count,link",
            }
            resp = self._session.get(
                self.API_URL, params=params, timeout=self.timeout, proxies=self._get_proxies()
            )
            resp.raise_for_status()
            data = resp.json()
            message = data.get("message", {})
            items = message.get("items", [])
            papers = self._parse_response(items)
        except Exception as e:
            logger.error("[CrossRefFetcher] Search failed: %s", e)

        return papers

    def _parse_response(self, items: List[Dict]) -> List[PaperMetadata]:
        """Parse CrossRef API response."""
        papers = []
        for item in items:
            authors = []
            for author in item.get("author", []) or []:
                given = author.get("given", "")
                family = author.get("family", "")
                name = f"{given} {family}".strip()
                if name:
                    authors.append(name)

            year = 0
            for date_key in ("published-print", "published-online"):
                date_parts = item.get(date_key, {}).get("date-parts", [])
                if date_parts and date_parts[0]:
                    try:
                        year = int(date_parts[0][0])
                    except (ValueError, IndexError):
                        pass
                    if year:
                        break

            links = item.get("link", [])
            pdf_url = ""
            for link in links:
                if link.get("content-type", "") == "application/pdf":
                    pdf_url = link.get("URL", "")
                    break

            papers.append(
                PaperMetadata(
                    title=(item.get("title", []) or [""])[0],
                    authors=authors,
                    year=year,
                    abstract=item.get("abstract", "") or "",
                    doi=item.get("DOI", ""),
                    url=item.get("url", ""),
                    pdf_url=pdf_url,
                    source="crossref",
                    citations=item.get("is-referenced-by-count", 0) or 0,
                    journal=(item.get("container-title", []) or [""])[0],
                    raw_data=item,
                )
            )
        return papers


class PubMedFetcher(BaseFetcher):
    """Fetch papers from PubMed via NCBI E-Utilities.

    Specialized for biomedical literature.
    """

    name = "pubmed"
    ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

    def __init__(
        self, timeout: int = 15, max_results: int = 10, api_key: str = ""
    ) -> None:
        super().__init__(timeout, max_results)
        self.api_key = api_key
        self._rate_limit = 0.1 if api_key else 0.35

    def search(self, query: str) -> List[PaperMetadata]:
        """Search PubMed for papers.

        Parameters
        ----------
        query : str
            Search query.

        Returns
        -------
        List[PaperMetadata]
            Papers found on PubMed.
        """
        papers = []
        try:
            params = {
                "db": "pubmed",
                "term": query,
                "retmax": self.max_results,
                "retmode": "json",
            }
            if self.api_key:
                params["api_key"] = self.api_key

            resp = self._session.get(
                self.ESEARCH_URL, params=params, timeout=self.timeout, proxies=self._get_proxies()
            )
            resp.raise_for_status()
            ids = resp.json().get("esearchresult", {}).get("idlist", [])

            if ids:
                papers = self._fetch_details(ids)
        except Exception as e:
            logger.error("[PubMedFetcher] Search failed: %s", e)

        return papers

    def _fetch_details(self, pmids: List[str]) -> List[PaperMetadata]:
        """Fetch detailed paper information for a list of PMIDs."""
        papers = []
        try:
            params = {
                "db": "pubmed",
                "id": ",".join(pmids),
                "retmode": "xml",
                "rettype": "abstract",
            }
            if self.api_key:
                params["api_key"] = self.api_key

            resp = self._session.get(
                self.EFETCH_URL, params=params, timeout=self.timeout, proxies=self._get_proxies()
            )
            resp.raise_for_status()
            papers = self._parse_xml_response(resp.text)
        except Exception as e:
            logger.error("[PubMedFetcher] Fetch details failed: %s", e)

        return papers

    def _parse_xml_response(self, xml_text: str) -> List[PaperMetadata]:
        """Parse PubMed XML response."""
        papers = []
        try:
            root = ET.fromstring(xml_text)
            for article in root.findall(".//PubmedArticle"):
                medline = article.find(".//MedlineCitation")
                if medline is None:
                    medline = article.find(".//Article")

                title_elem = article.find(".//ArticleTitle")
                abstract_elem = article.find(".//AbstractText")
                year_elem = article.find(".//PubDate/Year")
                journal_elem = article.find(".//Journal/Title")

                title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
                abstract = abstract_elem.text.strip() if abstract_elem is not None and abstract_elem.text else ""

                year = 0
                if year_elem is not None and year_elem.text:
                    try:
                        year = int(year_elem.text)
                    except ValueError:
                        pass

                authors = []
                for author_elem in article.findall(".//Author"):
                    last = author_elem.find("LastName")
                    fore = author_elem.find("ForeName")
                    parts = []
                    if fore is not None and fore.text:
                        parts.append(fore.text)
                    if last is not None and last.text:
                        parts.append(last.text)
                    if parts:
                        authors.append(" ".join(parts))

                pmid_elem = article.find(".//PMID")
                pmid = pmid_elem.text if pmid_elem is not None and pmid_elem.text else ""

                papers.append(
                    PaperMetadata(
                        title=title,
                        authors=authors,
                        year=year,
                        abstract=abstract,
                        source="pubmed",
                        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
                        journal=journal_elem.text.strip() if journal_elem is not None and journal_elem.text else "",
                        raw_data={"pmid": pmid},
                    )
                )
        except ET.ParseError as e:
            logger.error("[PubMedFetcher] XML parse error: %s", e)

        return papers


class GitHubFetcher(BaseFetcher):
    """Search GitHub for code repositories related to a research topic.

    Uses the GitHub Search API to find relevant repositories.
    """

    name = "github"
    API_URL = "https://api.github.com/search/repositories"

    def __init__(
        self, timeout: int = 15, max_results: int = 10, token: str = ""
    ) -> None:
        super().__init__(timeout, max_results)
        self.token = token
        if token:
            self._session.headers.update({"Authorization": f"Bearer {token}"})

    def search(self, query: str) -> List[PaperMetadata]:
        """Search GitHub for repositories.

        Parameters
        ----------
        query : str
            Search query.

        Returns
        -------
        List[PaperMetadata]
            Repositories found on GitHub.
        """
        papers = []
        try:
            params = {
                "q": f"{query} language:python OR language:jupyter-notebook",
                "sort": "stars",
                "order": "desc",
                "per_page": self.max_results,
            }
            resp = self._session.get(
                self.API_URL, params=params, timeout=self.timeout, proxies=self._get_proxies()
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])

            for item in items:
                papers.append(
                    PaperMetadata(
                        title=item.get("full_name", ""),
                        authors=[item.get("owner", {}).get("login", "")],
                        year=0,
                        abstract=item.get("description", "") or "",
                        url=item.get("html_url", ""),
                        source="github",
                        citations=item.get("stargazers_count", 0) or 0,
                        raw_data={
                            "stars": item.get("stargazers_count", 0),
                            "forks": item.get("forks_count", 0),
                            "language": item.get("language", ""),
                        },
                    )
                )
        except Exception as e:
            logger.error("[GitHubFetcher] Search failed: %s", e)

        return papers


class OpenAlexFetcher(BaseFetcher):
    """Fetch papers from OpenAlex (open scholarly index, 250M+ works).

    OpenAlex is a free, open catalog of the global research system.
    No API key required. Rate limit: 10 requests/second for polite pool
    (with mailto parameter), 1 request/second without.
    """

    name = "openalex"
    API_URL = "https://api.openalex.org/works"

    def __init__(
        self, timeout: int = 15, max_results: int = 10, email: str = ""
    ) -> None:
        super().__init__(timeout, max_results)
        self.email = email
        if email:
            self._session.headers.update({"mailto": email})

    def search(self, query: str) -> List[PaperMetadata]:
        """Search OpenAlex for papers.

        Parameters
        ----------
        query : str
            Search query.

        Returns
        -------
        List[PaperMetadata]
            Papers found on OpenAlex.
        """
        papers = []
        try:
            params = {
                "search": query,
                "per_page": self.max_results,
                "select": "id,title,authorships,publication_year,abstract_inverted_index,doi,open_access,type,cited_by_count,primary_location",
            }
            resp = self._session.get(
                self.API_URL, params=params, timeout=self.timeout, proxies=self._get_proxies()
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            papers = self._parse_response(results)
        except Exception as e:
            logger.error("[OpenAlexFetcher] Search failed: %s", e)

        return papers

    def _parse_response(self, items: List[Dict]) -> List[PaperMetadata]:
        """Parse OpenAlex API response.

        Parameters
        ----------
        items : List[Dict]
            API response items.

        Returns
        -------
        List[PaperMetadata]
            Parsed paper metadata.
        """
        papers = []
        for item in items:
            doi = ""
            doi_url = item.get("doi", "") or ""
            if doi_url.startswith("https://doi.org/"):
                doi = doi_url[len("https://doi.org/"):]
            elif doi_url.startswith("http://doi.org/"):
                doi = doi_url[len("http://doi.org/"):]

            authors = []
            for authorship in item.get("authorships", []) or []:
                author = authorship.get("author", {}) or {}
                name = author.get("display_name", "")
                if name:
                    authors.append(name)

            abstract = self._decode_inverted_index(
                item.get("abstract_inverted_index", {})
            )

            pdf_url = ""
            oa = item.get("open_access", {}) or {}
            if oa.get("oa_url"):
                pdf_url = oa["oa_url"]

            year = item.get("publication_year", 0) or 0

            location = item.get("primary_location", {}) or {}
            source_obj = location.get("source", {}) or {}
            journal = source_obj.get("display_name", "") or ""
            venue = journal

            url = ""
            landing_url = location.get("landing_page_url", "") or ""
            if landing_url:
                url = landing_url
            elif doi_url:
                url = doi_url

            openalex_id = ""
            oa_id = item.get("id", "") or ""
            if oa_id.startswith("https://openalex.org/"):
                openalex_id = oa_id[len("https://openalex.org/"):]

            papers.append(
                PaperMetadata(
                    title=item.get("title", "") or "",
                    authors=authors,
                    year=year,
                    abstract=abstract,
                    doi=doi,
                    url=url,
                    pdf_url=pdf_url,
                    source="openalex",
                    citations=item.get("cited_by_count", 0) or 0,
                    journal=journal,
                    venue=venue,
                    raw_data={"openalex_id": openalex_id},
                )
            )
        return papers

    @staticmethod
    def _decode_inverted_index(inverted_index: Dict) -> str:
        """Decode OpenAlex abstract_inverted_index to plain text.

        OpenAlex stores abstracts as an inverted index mapping words
        to their position indices. This reconstructs the original text.

        Parameters
        ----------
        inverted_index : Dict
            Mapping of word strings to lists of position integers.

        Returns
        -------
        str
            Reconstructed abstract text, or empty string if unavailable.
        """
        if not inverted_index:
            return ""

        position_word = {}
        for word, positions in inverted_index.items():
            for pos in positions:
                position_word[pos] = word

        if not position_word:
            return ""

        max_pos = max(position_word.keys())
        words = [position_word.get(i, "") for i in range(max_pos + 1)]
        return " ".join(words)


class DBLPFetcher(BaseFetcher):
    """Fetch papers from DBLP (computer science bibliography).

    DBLP provides a public API for searching computer science publications.
    No API key required.
    """

    name = "dblp"
    API_URL = "https://dblp.org/search/publ/api"

    def search(self, query: str) -> List[PaperMetadata]:
        """Search DBLP for publications.

        Parameters
        ----------
        query : str
            Search query.

        Returns
        -------
        List[PaperMetadata]
            Publications found on DBLP.
        """
        papers = []
        try:
            params = {
                "q": query,
                "format": "json",
                "h": self.max_results,
            }
            resp = self._session.get(
                self.API_URL, params=params, timeout=self.timeout, proxies=self._get_proxies()
            )
            resp.raise_for_status()
            data = resp.json()
            hits = data.get("result", {}).get("hits", {}).get("hit", [])
            papers = self._parse_response(hits)
        except Exception as e:
            logger.error("[DBLPFetcher] Search failed: %s", e)

        return papers

    def _parse_response(self, hits: List[Dict]) -> List[PaperMetadata]:
        """Parse DBLP API response.

        Parameters
        ----------
        hits : List[Dict]
            API response hit items.

        Returns
        -------
        List[PaperMetadata]
            Parsed paper metadata.
        """
        papers = []
        for hit in hits:
            info = hit.get("info", {})
            if not info:
                continue

            title = info.get("title", "") or ""

            authors = []
            author_data = info.get("authors", {}) or {}
            author_list = author_data.get("author", []) or []
            if isinstance(author_list, dict):
                author_list = [author_list]
            for author in author_list:
                name = author.get("text", "") if isinstance(author, dict) else str(author)
                if name:
                    authors.append(name)

            year = 0
            year_str = info.get("year", "")
            if year_str:
                try:
                    year = int(year_str)
                except (ValueError, TypeError):
                    pass

            doi = info.get("doi", "") or ""

            url = info.get("url", "") or ""
            ee_url = info.get("ee", "") or ""
            if not url and ee_url:
                url = ee_url

            pdf_url = ""
            if ee_url and ee_url.endswith(".pdf"):
                pdf_url = ee_url

            venue = info.get("venue", "") or ""
            journal = venue

            papers.append(
                PaperMetadata(
                    title=title,
                    authors=authors,
                    year=year,
                    abstract="",
                    doi=doi,
                    url=url,
                    pdf_url=pdf_url,
                    source="dblp",
                    citations=0,
                    journal=journal,
                    venue=venue,
                    raw_data=info,
                )
            )
        return papers


class ResearchSearcher:
    """Multi-source academic paper search orchestrator.

    Searches across multiple academic sources in parallel,
    merges results, deduplicates by DOI/arXiv ID/title,
    and returns ranked results.

    Parameters
    ----------
    sources : List[str]
        List of source names to search. Valid: arxiv, semantic_scholar,
        crossref, pubmed, github, openalex, dblp.
    max_results : int
        Maximum results per source.
    timeout : int
        HTTP timeout in seconds.
    semantic_scholar_api_key : str
        Optional Semantic Scholar API key for higher rate limits.
    crossref_email : str
        Email for polite CrossRef API usage.
    pubmed_api_key : str
        Optional PubMed API key for higher rate limits.
    github_token : str
        Optional GitHub token for higher rate limits.
    openalex_email : str
        Email for polite OpenAlex pool (higher rate limit).
    """

    VALID_SOURCES = {"arxiv", "semantic_scholar", "crossref", "pubmed", "github", "openalex", "dblp"}

    def __init__(
        self,
        sources: Optional[List[str]] = None,
        max_results: int = 10,
        timeout: int = 15,
        semantic_scholar_api_key: str = "",
        crossref_email: str = "",
        pubmed_api_key: str = "",
        github_token: str = "",
        openalex_email: str = "",
    ) -> None:
        self.sources = sources or ["arxiv", "semantic_scholar", "crossref"]
        self.max_results = max_results
        self.timeout = timeout
        self._s2_cache = S2Cache(ttl_seconds=CONFIG.s2_cache_ttl)
        self.fetchers = self._init_fetcher(
            semantic_scholar_api_key, crossref_email, pubmed_api_key, github_token, openalex_email
        )

    def _init_fetcher(
        self,
        s2_key: str,
        crossref_email: str,
        pubmed_key: str,
        github_token: str,
        openalex_email: str,
    ) -> Dict[str, BaseFetcher]:
        """Initialize fetcher instances based on configured sources."""
        fetchers = {}
        for source in self.sources:
            if source not in self.VALID_SOURCES:
                logger.warning("[ResearchSearcher] Unknown source: %s", source)
                continue

            if source == "arxiv":
                fetchers["arxiv"] = ArxivFetcher(
                    timeout=self.timeout, max_results=self.max_results
                )
            elif source == "semantic_scholar":
                fetchers["semantic_scholar"] = SemanticScholarFetcher(
                    timeout=self.timeout, max_results=self.max_results, api_key=s2_key, cache=self._s2_cache
                )
            elif source == "crossref":
                fetchers["crossref"] = CrossRefFetcher(
                    timeout=self.timeout, max_results=self.max_results, email=crossref_email
                )
            elif source == "pubmed":
                fetchers["pubmed"] = PubMedFetcher(
                    timeout=self.timeout, max_results=self.max_results, api_key=pubmed_key
                )
            elif source == "github":
                fetchers["github"] = GitHubFetcher(
                    timeout=self.timeout, max_results=self.max_results, token=github_token
                )
            elif source == "openalex":
                fetchers["openalex"] = OpenAlexFetcher(
                    timeout=self.timeout, max_results=self.max_results, email=openalex_email
                )
            elif source == "dblp":
                fetchers["dblp"] = DBLPFetcher(
                    timeout=self.timeout, max_results=self.max_results
                )

        return fetchers

    def search(
        self,
        query: str | ExpandedQuery,
        max_results: Optional[int] = None,
    ) -> List[SearchResult]:
        """Search across all configured sources.

        Parameters
        ----------
        query : str or ExpandedQuery
            Search query. If ExpandedQuery, searches each category separately.
        max_results : int or None
            Override for maximum results per source.

        Returns
        -------
        List[SearchResult]
            Ranked and deduplicated search results.
        """
        queries = [query] if isinstance(query, str) else query.all_queries()
        limit = max_results or self.max_results

        all_results: List[SearchResult] = []
        seen_ids: set = set()

        def search_source(source_name: str, fetcher: BaseFetcher, search_query: str) -> List[SearchResult]:
            """Search a single source for a single query."""
            results = []
            try:
                papers = fetcher.search(search_query)
                for paper in papers:
                    dedup_key = self._dedup_key(paper)
                    if dedup_key and dedup_key not in seen_ids:
                        seen_ids.add(dedup_key)
                        results.append(
                            SearchResult(
                                paper=paper,
                                score=self._score_paper(paper),
                                matched_query=search_query,
                            )
                        )
            except Exception as e:
                logger.error(
                    "[ResearchSearcher] %s search for '%s' failed: %s",
                    source_name, search_query, e,
                )
            return results

        with ThreadPoolExecutor(max_workers=len(self.fetchers)) as executor:
            futures = {}
            for source_name, fetcher in self.fetchers.items():
                for q in queries:
                    future = executor.submit(search_source, source_name, fetcher, q)
                    futures[future] = (source_name, q)

            for future in as_completed(futures):
                all_results.extend(future.result())

        all_results.sort(key=lambda r: r.score, reverse=True)
        return all_results[:limit * len(queries)]

    def _dedup_key(self, paper: PaperMetadata) -> str:
        """Generate a deduplication key for a paper.

        Priority: DOI > arXiv ID > normalized title.
        """
        if paper.doi:
            return f"doi:{paper.doi.lower()}"
        if paper.arxiv_id:
            return f"arxiv:{paper.arxiv_id.lower()}"
        if paper.title:
            normalized = paper.title.lower().strip()
            normalized = "".join(c for c in normalized if c.isalnum() or c.isspace())
            normalized = " ".join(normalized.split())
            if normalized:
                return f"title:{normalized}"
        return ""

    def _score_paper(self, paper: PaperMetadata) -> float:
        """Score a paper for ranking purposes.

        Higher score = more relevant. Factors:
        - Citation count (normalized)
        - Has abstract
        - Has PDF URL
        - Source reliability
        """
        score = 0.0

        if paper.citations > 0:
            score += min(paper.citations / 100.0, 1.0)

        if paper.abstract:
            score += 0.2

        if paper.pdf_url:
            score += 0.1

        if paper.doi:
            score += 0.1

        source_weights = {
            "semantic_scholar": 0.15,
            "openalex": 0.12,
            "arxiv": 0.1,
            "crossref": 0.1,
            "pubmed": 0.1,
            "dblp": 0.08,
            "github": 0.05,
        }
        score += source_weights.get(paper.source, 0.0)

        return score
