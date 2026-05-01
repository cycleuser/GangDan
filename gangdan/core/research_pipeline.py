"""End-to-end research pipeline: search -> download -> rename -> convert -> index.

This orchestrates the full workflow:
1. Expand query (optional, controlled by config)
2. Search multiple sources in parallel
3. Rank and deduplicate results
4. Download PDF (multi-source OA discovery)
5. Rename PDF to citation format
6. Convert PDF to Markdown (preserving formulas/images)
7. Index into knowledge base (ChromaDB)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from gangdan.core.config import CONFIG, DATA_DIR
from gangdan.core.constants import PAPERS_DIR_NAME
from gangdan.core.pdf_converter import PDFConverter
from gangdan.core.pdf_downloader import PDFDownloadManager
from gangdan.core.pdf_renamer import PDFRenamer
from gangdan.core.query_expander import QueryExpander
from gangdan.core.research_models import PaperMetadata, PaperRecord
from gangdan.core.research_searcher import ResearchSearcher

logger = logging.getLogger(__name__)

MANIFEST_FILE = DATA_DIR / PAPERS_DIR_NAME / "manifest.json"


class ResearchPipeline:
    """End-to-end research pipeline.

    Parameters
    ----------
    config : Config or None
        Configuration object. Uses global CONFIG if None.
    """

    def __init__(self, config: Optional[Any] = None) -> None:
        self.config = config or CONFIG
        self.papers_dir = DATA_DIR / PAPERS_DIR_NAME
        self.papers_dir.mkdir(parents=True, exist_ok=True)

        self.searcher = ResearchSearcher(
            sources=self._parse_sources(self.config.research_search_sources),
            max_results=self.config.research_max_results,
            timeout=self.config.research_search_timeout,
            semantic_scholar_api_key=self.config.semantic_scholar_api_key,
            crossref_email=self.config.crossref_email,
            pubmed_api_key=self.config.pubmed_api_key,
            github_token=self.config.github_token,
            openalex_email=self.config.openalex_email,
        )
        self.downloader = PDFDownloadManager(papers_dir=self.papers_dir)
        self.renamer = PDFRenamer()
        self.converter = PDFConverter(
            engine=self.config.pdf_convert_engine,
        )
        self.expander: Optional[QueryExpander] = None

    def search(
        self,
        query: str,
        expand_query: Optional[bool] = None,
        sources: Optional[List[str]] = None,
        max_results: Optional[int] = None,
    ) -> List[Any]:
        """Search for papers, optionally with LLM query expansion.

        Parameters
        ----------
        query : str
            Search query string.
        expand_query : bool or None
            Whether to expand query. None uses config default.
        sources : List[str] or None
            Override search sources.
        max_results : int or None
            Override max results per source.

        Returns
        -------
        List[SearchResult]
            Ranked and deduplicated search results.
        """
        should_expand = expand_query if expand_query is not None else self.config.query_expansion_enabled

        if should_expand and self.expander is None:
            from gangdan.app import get_research_client

            client = get_research_client()
            self.expander = QueryExpander(
                llm_client=client,
                enabled=True,
                model=self.config.query_expansion_model or "",
            )

        search_query: Any = query
        if should_expand and self.expander:
            search_query = self.expander.expand(query)

        if sources:
            searcher = ResearchSearcher(
                sources=sources,
                max_results=max_results or self.config.research_max_results,
                timeout=self.config.research_search_timeout,
                semantic_scholar_api_key=self.config.semantic_scholar_api_key,
                crossref_email=self.config.crossref_email,
                pubmed_api_key=self.config.pubmed_api_key,
                github_token=self.config.github_token,
                openalex_email=self.config.openalex_email,
            )
            return searcher.search(search_query, max_results=max_results)

        return self.searcher.search(search_query, max_results=max_results)

    def download_and_process(
        self,
        paper: PaperMetadata,
        rename: Optional[bool] = None,
        convert: Optional[bool] = None,
        index_to_kb: Optional[str] = None,
    ) -> PaperRecord:
        """Download PDF, optionally rename and convert, optionally index to KB.

        Parameters
        ----------
        paper : PaperMetadata
            Paper metadata from search.
        rename : bool or None
            Whether to rename PDF. None uses config default.
        convert : bool or None
            Whether to convert to Markdown. None uses config default.
        index_to_kb : str or None
            Knowledge base collection name. None skips indexing.

        Returns
        -------
        PaperRecord
            Complete record of the processed paper.
        """
        should_rename = rename if rename is not None else self.config.research_pipeline_rename
        should_convert = convert if convert is not None else self.config.research_pipeline_convert

        download_result = self.downloader.download_pdf(paper)
        if not download_result.success:
            logger.error("[Pipeline] Download failed for '%s': %s", paper.title, download_result.error)
            return PaperRecord(
                metadata=paper,
                local_pdf="",
                notes=download_result.error,
            )

        pdf_path = Path(download_result.pdf_path)
        citation_filename = pdf_path.name

        if should_rename:
            new_path = self.renamer.rename(pdf_path, metadata=paper)
            citation_filename = new_path.name
            pdf_path = new_path

        markdown_path = ""
        if should_convert:
            conversion_result = self.converter.convert(pdf_path)
            if conversion_result.success:
                markdown_path = conversion_result.markdown_path
                logger.info("[Pipeline] Converted '%s' to Markdown", paper.title)
            else:
                logger.warning("[Pipeline] Conversion failed for '%s': %s", paper.title, conversion_result.error)

        record = PaperRecord(
            metadata=paper,
            local_pdf=str(pdf_path),
            citation_filename=citation_filename,
            markdown_path=markdown_path,
            download_date=datetime.now().isoformat(),
            kb_collection=index_to_kb or "",
        )

        if index_to_kb and markdown_path:
            self._index_to_kb(markdown_path, index_to_kb)

        return record

    def get_paper_details(self, paper_id: str) -> Optional[PaperMetadata]:
        """Get detailed metadata for a paper.

        Parameters
        ----------
        paper_id : str
            Paper identifier (DOI, arXiv ID, or S2 ID).

        Returns
        -------
        PaperMetadata or None
            Paper metadata if found.
        """
        from gangdan.core.research_searcher import SemanticScholarFetcher

        fetcher = SemanticScholarFetcher(
            api_key=self.config.semantic_scholar_api_key,
        )
        return fetcher.get_paper(paper_id)

    def get_related_papers(
        self, paper_id: str, relation: str = "citations", limit: int = 20
    ) -> List[PaperMetadata]:
        """Get related papers (citations, references, recommendations).

        Parameters
        ----------
        paper_id : str
            Paper identifier.
        relation : str
            Relation type: 'citations', 'references', or 'recommendations'.
        limit : int
            Maximum number of related papers.

        Returns
        -------
        List[PaperMetadata]
            List of related papers.
        """
        from gangdan.core.research_searcher import SemanticScholarFetcher

        fetcher = SemanticScholarFetcher(
            api_key=self.config.semantic_scholar_api_key,
        )

        if relation == "citations":
            return fetcher.get_citations(paper_id, limit=limit)
        elif relation == "references":
            return fetcher.get_references(paper_id, limit=limit)
        elif relation == "recommendations":
            return fetcher.get_recommendations(paper_id, limit=limit)
        else:
            logger.error("[Pipeline] Unknown relation type: %s", relation)
            return []

    def save_manifest(self, records: List[PaperRecord]) -> None:
        """Save paper records to manifest.json.

        Parameters
        ----------
        records : List[PaperRecord]
            Paper records to save (replaces existing manifest).
        """
        manifest_path = self.papers_dir / "manifest.json"

        data = {
            "version": 1,
            "papers": [r.to_dict() for r in records],
        }

        try:
            manifest_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            logger.info("[Pipeline] Saved manifest with %d papers", len(records))
        except OSError as e:
            logger.error("[Pipeline] Failed to save manifest: %s", e)

    def load_manifest(self) -> List[PaperRecord]:
        """Load paper records from manifest.json.

        Returns
        -------
        List[PaperRecord]
            List of paper records.
        """
        manifest_path = self.papers_dir / "manifest.json"
        if not manifest_path.exists():
            return []

        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            papers = data.get("papers", [])
            return [PaperRecord.from_dict(p) for p in papers]
        except (json.JSONDecodeError, OSError) as e:
            logger.error("[Pipeline] Failed to load manifest: %s", e)
            return []

    def delete_paper(self, paper_id: str) -> bool:
        """Delete a paper record and its local files.

        Parameters
        ----------
        paper_id : str
            Paper record ID.

        Returns
        -------
        bool
            True if deleted successfully.
        """
        records = self.load_manifest()
        target = None
        for r in records:
            if r.paper_id == paper_id:
                target = r
                break

        if target is None:
            return False

        if target.local_pdf:
            Path(target.local_pdf).unlink(missing_ok=True)
        if target.markdown_path:
            Path(target.markdown_path).unlink(missing_ok=True)

        records = [r for r in records if r.paper_id != paper_id]
        self.save_manifest(records)
        return True

    @staticmethod
    def _parse_sources(sources_str: str) -> List[str]:
        """Parse comma-separated sources string.

        Parameters
        ----------
        sources_str : str
            Comma-separated source names.

        Returns
        -------
        List[str]
            List of source names.
        """
        if not sources_str:
            return ["arxiv", "semantic_scholar", "crossref"]
        return [s.strip() for s in sources_str.split(",") if s.strip()]

    @staticmethod
    def _index_to_kb(markdown_path: str, collection: str) -> None:
        """Index a Markdown file into ChromaDB.

        Parameters
        ----------
        markdown_path : str
            Path to the Markdown file.
        collection : str
            ChromaDB collection name.
        """
        try:
            from gangdan.core.chroma_manager import ChromaManager
            from gangdan.core.ollama_client import OllamaClient

            chroma = ChromaManager(str(DATA_DIR / "chroma"), collection)
            ollama = OllamaClient(base_url=CONFIG.ollama_url)

            content = Path(markdown_path).read_text(encoding="utf-8")
            chunks = ResearchPipeline._chunk_text(content, CONFIG.chunk_size, CONFIG.chunk_overlap)

            documents = []
            embeddings = []
            metadatas = []
            ids = []

            for i, chunk in enumerate(chunks):
                if len(chunk.strip()) < 50:
                    continue
                try:
                    emb = ollama.embed(chunk, CONFIG.embedding_model)
                    import hashlib
                    doc_id = hashlib.md5(f"{markdown_path}_{i}".encode()).hexdigest()
                    documents.append(chunk)
                    embeddings.append(emb)
                    metadatas.append({"source": collection, "file": markdown_path, "chunk": i})
                    ids.append(doc_id)
                except Exception as e:
                    logger.debug("[Pipeline] Embedding chunk %d failed: %s", i, e)

            if documents:
                chroma.add_documents(collection, documents, embeddings, metadatas, ids)
                logger.info("[Pipeline] Indexed %d chunks to '%s'", len(documents), collection)
        except Exception as e:
            logger.error("[Pipeline] KB indexing failed: %s", e)

    @staticmethod
    def _chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
        """Split text into overlapping chunks.

        Parameters
        ----------
        text : str
            Text to chunk.
        chunk_size : int
            Size of each chunk in characters.
        overlap : int
            Number of overlapping characters.

        Returns
        -------
        List[str]
            List of text chunks.
        """
        if overlap >= chunk_size:
            overlap = max(0, chunk_size - 1)

        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk)
            start = end - overlap
        return chunks
