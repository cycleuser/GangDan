"""Research pipeline for GangDan Refined.

Provides end-to-end research workflow:
- Paper search across multiple academic sources
- PDF download, rename, and conversion
- Knowledge base indexing
- Batch export and report generation
"""

from .models import (
    PaperMetadata,
    SearchResult,
    DownloadResult,
    ConversionResult,
    PaperRecord,
    ArxivFullText,
)


def __getattr__(name):
    """Lazy imports to avoid circular dependency with search module."""
    if name == "ResearchPipeline":
        from .pipeline import ResearchPipeline
        return ResearchPipeline
    if name == "ExportManager":
        from .export import ExportManager
        return ExportManager
    if name == "BatchConvertItem":
        from .export import BatchConvertItem
        return BatchConvertItem
    if name == "BatchConvertResult":
        from .export import BatchConvertResult
        return BatchConvertResult
    if name == "BatchConvertReport":
        from .export import BatchConvertReport
        return BatchConvertReport
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "PaperMetadata",
    "SearchResult",
    "DownloadResult",
    "ConversionResult",
    "PaperRecord",
    "ArxivFullText",
    "ResearchPipeline",
    "ExportManager",
    "BatchConvertItem",
    "BatchConvertResult",
    "BatchConvertReport",
]