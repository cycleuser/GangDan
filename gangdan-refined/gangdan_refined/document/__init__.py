"""Document processing for GangDan Refined.

Provides:
- PDF/CAJ to Markdown conversion
- Multi-source OA PDF discovery and download
- Citation-style PDF renaming
- Image extraction and processing
- Documentation downloader/indexer (re-exported from storage)
- Preprint intelligence (fetching, conversion, scheduling)
"""

from .pdf_converter import PDFConverter, CAJConverter
from .pdf_downloader import PDFDownloadManager
from .pdf_renamer import PDFRenamer
from ..storage.doc_manager import DocManager, DOC_SOURCES

__all__ = [
    "PDFConverter",
    "CAJConverter",
    "PDFDownloadManager",
    "PDFRenamer",
    "DocManager",
    "DOC_SOURCES",
]