"""Multi-source Open Access PDF discovery and download manager.

Inspired by CiteBox's three-source parallel OA discovery:
1. Unpaywall API (DOI-based OA discovery)
2. Europe PMC (biomedical literature)
3. PMC ID Converter (PubMed Central)

Falls back to direct arXiv PDF URLs and Semantic Scholar OA links.

All downloaded PDFs are SHA-256 deduplicated.
"""

from __future__ import annotations

import hashlib
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

import requests

from gangdan.core.config import CONFIG, get_proxies
from gangdan.core.constants import (
    PDF_DOWNLOAD_TIMEOUT,
    PDF_MAX_SIZE_MB,
    PDF_SHA256_BLOCK_SIZE,
    PAPERS_DIR_NAME,
    UNPAYWALL_API_URL,
    EUROPE_PMC_API_URL,
    PMC_ID_CONVERTER_URL,
)
from gangdan.core.research_models import DownloadResult, PaperMetadata, PaperRecord

logger = logging.getLogger(__name__)


class PDFDownloadManager:
    """Multi-source OA PDF discovery and download manager.

    Parameters
    ----------
    papers_dir : Path or None
        Directory to store downloaded papers. Defaults to DATA_DIR/papers.
    """

    def __init__(self, papers_dir: Optional[Path] = None) -> None:
        if papers_dir is None:
            from gangdan.core.config import DATA_DIR

            papers_dir = DATA_DIR / PAPERS_DIR_NAME
        self.papers_dir = Path(papers_dir)
        self.papers_dir.mkdir(parents=True, exist_ok=True)
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": "GangDan/1.0 (mailto:gangdan@localhost)"}
        )

    def _sha256_file(self, filepath: Path) -> str:
        """Compute SHA-256 hash of a file.

        Parameters
        ----------
        filepath : Path
            Path to the file.

        Returns
        -------
        str
            Hex digest of the SHA-256 hash.
        """
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            while True:
                block = f.read(PDF_SHA256_BLOCK_SIZE)
                if not block:
                    break
                sha256.update(block)
        return sha256.hexdigest()

    def _check_duplicate(self, sha256: str) -> Optional[Path]:
        """Check if a file with the given SHA-256 already exists.

        Parameters
        ----------
        sha256 : str
            SHA-256 hash to check.

        Returns
        -------
        Path or None
            Path to existing file if duplicate, None otherwise.
        """
        for pdf_file in self.papers_dir.rglob("*.pdf"):
            try:
                if self._sha256_file(pdf_file) == sha256:
                    return pdf_file
            except OSError:
                continue
        return None

    def discover_oa_urls(self, paper: PaperMetadata) -> List[Dict[str, str]]:
        """Discover Open Access PDF URLs from multiple sources.

        Parameters
        ----------
        paper : PaperMetadata
            Paper metadata with DOI, arXiv ID, or PMID.

        Returns
        -------
        List[Dict[str, str]]
            List of candidate dicts with 'url' and 'source' keys, deduplicated.
        """
        candidates = []
        seen_urls = set()

        if paper.doi:
            urls = self._discover_from_unpaywall(paper.doi)
            for u in urls:
                if u["url"] not in seen_urls:
                    seen_urls.add(u["url"])
                    candidates.append(u)

            urls = self._discover_from_crossref_oa(paper.doi)
            for u in urls:
                if u["url"] not in seen_urls:
                    seen_urls.add(u["url"])
                    candidates.append(u)

        if paper.arxiv_id:
            url = f"https://arxiv.org/pdf/{paper.arxiv_id}.pdf"
            if url not in seen_urls:
                seen_urls.add(url)
                candidates.append({"url": url, "source": "arxiv"})

        if paper.pdf_url and paper.pdf_url not in seen_urls:
            seen_urls.add(paper.pdf_url)
            candidates.append({"url": paper.pdf_url, "source": paper.source})

        raw_pmid = ""
        if paper.raw_data:
            raw_pmid = paper.raw_data.get("pmid", "") or paper.raw_data.get("pmid", "")

        if paper.doi or raw_pmid:
            urls = self._discover_from_europe_pmc(paper.doi, raw_pmid)
            for u in urls:
                if u["url"] not in seen_urls:
                    seen_urls.add(u["url"])
                    candidates.append(u)

        return candidates

    def _discover_from_unpaywall(self, doi: str) -> List[Dict[str, str]]:
        """Discover OA URL from Unpaywall.

        Parameters
        ----------
        doi : str
            DOI of the paper.

        Returns
        -------
        List[Dict[str, str]]
            OA URL candidates.
        """
        results = []
        try:
            url = f"{UNPAYWALL_API_URL}/{doi}"
            params = {"email": "gangdan@localhost"}
            proxies = get_proxies()
            resp = self._session.get(url, params=params, timeout=15, proxies=proxies)
            resp.raise_for_status()
            data = resp.json()

            best = data.get("best_oa_location", {}) or {}
            if best.get("url_for_pdf"):
                results.append({"url": best["url_for_pdf"], "source": "unpaywall_best"})

            for loc in data.get("oa_locations", []) or []:
                pdf_url = loc.get("url_for_pdf")
                if pdf_url and pdf_url not in [r["url"] for r in results]:
                    results.append({"url": pdf_url, "source": "unpaywall"})
        except Exception as e:
            logger.debug("[Unpaywall] DOI %s failed: %s", doi, e)

        return results

    def _discover_from_crossref_oa(self, doi: str) -> List[Dict[str, str]]:
        """Discover OA URL from CrossRef links.

        Parameters
        ----------
        doi : str
            DOI of the paper.

        Returns
        -------
        List[Dict[str, str]]
            OA URL candidates.
        """
        results = []
        try:
            url = f"https://api.crossref.org/works/{doi}"
            proxies = get_proxies()
            resp = self._session.get(url, timeout=15, proxies=proxies)
            resp.raise_for_status()
            data = resp.json().get("message", {})

            for link in data.get("link", []) or []:
                if link.get("content-type") == "application/pdf":
                    pdf_url = link.get("URL", "")
                    if pdf_url:
                        results.append({"url": pdf_url, "source": "crossref"})
                        break
        except Exception as e:
            logger.debug("[CrossRef OA] DOI %s failed: %s", doi, e)

        return results

    def _discover_from_europe_pmc(self, doi: str = "", pmid: str = "") -> List[Dict[str, str]]:
        """Discover OA URL from Europe PMC.

        Parameters
        ----------
        doi : str
            DOI of the paper.
        pmid : str
            PubMed ID.

        Returns
        -------
        List[Dict[str, str]]
            OA URL candidates.
        """
        results = []
        try:
            params = {"format": "json", "pageSize": 1}
            if doi:
                params["query"] = f'DOI:"{doi}"'
            elif pmid:
                params["query"] = f'EXT_ID:"{pmid}"'
            else:
                return results

            proxies = get_proxies()
            resp = self._session.get(
                EUROPE_PMC_API_URL, params=params, timeout=15, proxies=proxies
            )
            resp.raise_for_status()
            data = resp.json()
            results_list = data.get("resultList", {}).get("result", [])

            for result in results_list[:1]:
                if result.get("isOpenAccess") == "Y":
                    pmcid = result.get("pmcid", "")
                    if pmcid:
                        results.append(
                            {
                                "url": f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML",
                                "source": "europe_pmc",
                            }
                        )
        except Exception as e:
            logger.debug("[Europe PMC] failed: %s", e)

        return results

    def download_pdf(
        self,
        paper: PaperMetadata,
        filename: Optional[str] = None,
    ) -> DownloadResult:
        """Download a paper's PDF with multi-source OA discovery.

        Parameters
        ----------
        paper : PaperMetadata
            Paper metadata. Must have DOI, arXiv ID, or pdf_url.
        filename : str or None
            Custom filename. If None, auto-generated from paper title.

        Returns
        -------
        DownloadResult
            Download result with path, source, and hash info.
        """
        if not filename:
            safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in paper.title[:80])
            filename = f"{safe_title}.pdf"

        candidates = self.discover_oa_urls(paper)
        if not candidates:
            return DownloadResult(error="No OA PDF sources found")

        max_bytes = PDF_MAX_SIZE_MB * 1024 * 1024

        for candidate in candidates:
            result = self._try_download(candidate["url"], filename, max_bytes)
            if result.success:
                result.source = candidate["source"]
                if paper.doi or paper.arxiv_id or paper.title:
                    dedup = self._check_duplicate(result.sha256)
                    if dedup and dedup != Path(result.pdf_path):
                        Path(result.pdf_path).unlink(missing_ok=True)
                        return DownloadResult(
                            success=True,
                            pdf_path=str(dedup),
                            source=result.source,
                            file_size=dedup.stat().st_size,
                            sha256=result.sha256,
                        )
                return result

        return DownloadResult(error="All download attempts failed")

    def _try_download(self, url: str, filename: str, max_bytes: int) -> DownloadResult:
        """Attempt to download a PDF from a single URL.

        Parameters
        ----------
        url : str
            URL to download from.
        filename : str
            Target filename.
        max_bytes : int
            Maximum allowed file size in bytes.

        Returns
        -------
        DownloadResult
            Download result.
        """
        try:
            proxies = get_proxies()
            resp = self._session.get(
                url, timeout=PDF_DOWNLOAD_TIMEOUT, stream=True, proxies=proxies
            )
            resp.raise_for_status()

            content_type = resp.headers.get("Content-Type", "")
            if "text/html" in content_type and "pdf" not in content_type.lower():
                return DownloadResult(error=f"Response is HTML, not PDF: {content_type}")

            content_length = int(resp.headers.get("Content-Length", 0))
            if content_length > max_bytes:
                return DownloadResult(
                    error=f"File too large: {content_length / 1024 / 1024:.1f} MB"
                )

            filepath = self.papers_dir / filename
            sha256 = hashlib.sha256()
            total_size = 0

            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        total_size += len(chunk)
                        if total_size > max_bytes:
                            filepath.unlink(missing_ok=True)
                            return DownloadResult(error="File exceeded size limit during download")
                        f.write(chunk)
                        sha256.update(chunk)

            return DownloadResult(
                success=True,
                pdf_path=str(filepath),
                file_size=total_size,
                sha256=sha256.hexdigest(),
            )
        except Exception as e:
            logger.error("[PDFDownload] Failed %s: %s", url[:80], e)
            return DownloadResult(error=str(e))

    def list_papers(self) -> List[Path]:
        """List all PDF files in the papers directory.

        Returns
        -------
        List[Path]
            List of PDF file paths.
        """
        return sorted(self.papers_dir.rglob("*.pdf"))

    def get_paper_dir(self) -> Path:
        """Return the papers directory path."""
        return self.papers_dir