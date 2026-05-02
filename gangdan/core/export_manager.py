"""Batch conversion and export manager.

Handles:
- Batch conversion of preprints (HTML/TeX/XML) to Markdown
- Batch conversion of research papers (PDF) to Markdown
- ZIP export of Markdown files
- Progress tracking for batch operations
"""

from __future__ import annotations

import logging
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class BatchConvertItem:
    """A single item in a batch conversion.

    Attributes
    ----------
    item_id : str
        Unique identifier.
    title : str
        Document title.
    source_type : str
        'preprint' or 'paper'.
    content_url : str
        URL or path to source content.
    content_type : str
        'html', 'tex', 'xml', or 'pdf'.
    preprint_id : str
        Preprint ID (for preprints).
    """

    item_id: str = ""
    title: str = ""
    source_type: str = ""
    content_url: str = ""
    content_type: str = ""
    preprint_id: str = ""


@dataclass
class BatchConvertResult:
    """Result of a single item in batch conversion.

    Attributes
    ----------
    item_id : str
        Item identifier.
    title : str
        Document title.
    success : bool
        Whether conversion succeeded.
    markdown_path : str
        Path to output Markdown.
    markdown_content : str
        Markdown content (truncated).
    engine : str
        Conversion engine used.
    error : str
        Error message if failed.
    """

    item_id: str = ""
    title: str = ""
    success: bool = False
    markdown_path: str = ""
    markdown_content: str = ""
    engine: str = ""
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "item_id": self.item_id,
            "title": self.title,
            "success": self.success,
            "markdown_path": self.markdown_path,
            "markdown_content": self.markdown_content[:5000],
            "engine": self.engine,
            "error": self.error,
        }


@dataclass
class BatchConvertReport:
    """Full report of a batch conversion.

    Attributes
    ----------
    total : int
        Total items.
    success_count : int
        Successful conversions.
    fail_count : int
        Failed conversions.
    results : List[BatchConvertResult]
        Per-item results.
    zip_path : str
        Path to ZIP export (if created).
    """

    total: int = 0
    success_count: int = 0
    fail_count: int = 0
    results: List[BatchConvertResult] = field(default_factory=list)
    zip_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total": self.total,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "results": [r.to_dict() for r in self.results],
            "zip_path": self.zip_path,
        }


class ExportManager:
    """Manages batch conversion and export operations.

    Parameters
    ----------
    output_dir : Path or None
        Base output directory. Uses temp dir if None.
    """

    def __init__(self, output_dir: Optional[Path] = None) -> None:
        self.output_dir = output_dir or Path(tempfile.mkdtemp(prefix="gangdan_export_"))
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def batch_convert_preprints(
        self,
        items: List[Dict[str, str]],
        create_zip: bool = True,
    ) -> BatchConvertReport:
        """Batch convert preprints to Markdown.

        Parameters
        ----------
        items : List[Dict]
            Each dict has: item_id, title, url, content_type, preprint_id.
        create_zip : bool
            Whether to create a ZIP export.

        Returns
        -------
        BatchConvertReport
            Conversion report.
        """
        report = BatchConvertReport(total=len(items))

        for item_data in items:
            item_id = item_data.get("item_id", "")
            title = item_data.get("title", "")
            url = item_data.get("url", "")
            content_type = item_data.get("content_type", "html")
            preprint_id = item_data.get("preprint_id", "")

            result = self._convert_preprint_item(
                item_id=item_id,
                title=title,
                url=url,
                content_type=content_type,
                preprint_id=preprint_id,
            )
            report.results.append(result)

            if result.success:
                report.success_count += 1
            else:
                report.fail_count += 1

        if create_zip and report.success_count > 0:
            report.zip_path = self._create_zip(report.results, "preprints")

        return report

    def batch_convert_papers(
        self,
        items: List[Dict[str, str]],
        create_zip: bool = True,
    ) -> BatchConvertReport:
        """Batch convert research papers (PDF) to Markdown.

        Parameters
        ----------
        items : List[Dict]
            Each dict has: item_id, title, pdf_path.
        create_zip : bool
            Whether to create a ZIP export.

        Returns
        -------
        BatchConvertReport
            Conversion report.
        """
        report = BatchConvertReport(total=len(items))

        for item_data in items:
            item_id = item_data.get("item_id", "")
            title = item_data.get("title", "")
            pdf_path = item_data.get("pdf_path", "")

            result = self._convert_paper_item(
                item_id=item_id,
                title=title,
                pdf_path=pdf_path,
            )
            report.results.append(result)

            if result.success:
                report.success_count += 1
            else:
                report.fail_count += 1

        if create_zip and report.success_count > 0:
            report.zip_path = self._create_zip(report.results, "papers")

        return report

    def batch_convert_mixed(
        self,
        preprint_items: Optional[List[Dict[str, str]]] = None,
        paper_items: Optional[List[Dict[str, str]]] = None,
        markdown_items: Optional[List[Dict[str, str]]] = None,
        create_zip: bool = True,
    ) -> BatchConvertReport:
        """Batch convert mixed sources (preprints + papers + existing Markdown).

        Parameters
        ----------
        preprint_items : List[Dict] or None
            Preprint items with url, content_type, preprint_id.
        paper_items : List[Dict] or None
            Paper items with pdf_path.
        markdown_items : List[Dict] or None
            Existing Markdown items with md_path.
        create_zip : bool
            Whether to create a ZIP export.

        Returns
        -------
        BatchConvertReport
            Combined conversion report.
        """
        all_results: List[BatchConvertResult] = []

        if preprint_items:
            for item_data in preprint_items:
                result = self._convert_preprint_item(
                    item_id=item_data.get("item_id", ""),
                    title=item_data.get("title", ""),
                    url=item_data.get("url", ""),
                    content_type=item_data.get("content_type", "html"),
                    preprint_id=item_data.get("preprint_id", ""),
                )
                all_results.append(result)

        if paper_items:
            for item_data in paper_items:
                result = self._convert_paper_item(
                    item_id=item_data.get("item_id", ""),
                    title=item_data.get("title", ""),
                    pdf_path=item_data.get("pdf_path", ""),
                )
                all_results.append(result)

        if markdown_items:
            for item_data in markdown_items:
                result = self._collect_markdown_item(
                    item_id=item_data.get("item_id", ""),
                    title=item_data.get("title", ""),
                    md_path=item_data.get("md_path", ""),
                )
                all_results.append(result)

        success_count = sum(1 for r in all_results if r.success)
        fail_count = len(all_results) - success_count

        report = BatchConvertReport(
            total=len(all_results),
            success_count=success_count,
            fail_count=fail_count,
            results=all_results,
        )

        if create_zip and success_count > 0:
            report.zip_path = self._create_zip(all_results, "mixed")

        return report

    def export_kb_to_zip(
        self,
        markdown_paths: List[str],
        kb_name: str = "knowledge_base",
    ) -> str:
        """Export KB Markdown files to a ZIP.

        Parameters
        ----------
        markdown_paths : List[str]
            Paths to Markdown files.
        kb_name : str
            Name for the ZIP file.

        Returns
        -------
        str
            Path to the ZIP file.
        """
        zip_dir = self.output_dir / "kb_exports"
        zip_dir.mkdir(parents=True, exist_ok=True)

        zip_path = zip_dir / f"{kb_name}.zip"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for md_path in markdown_paths:
                path = Path(md_path)
                if path.exists():
                    zf.write(path, arcname=path.name)

        logger.info("[ExportManager] Exported KB '%s' to %s", kb_name, zip_path)
        return str(zip_path)

    def _convert_preprint_item(
        self,
        item_id: str,
        title: str,
        url: str,
        content_type: str,
        preprint_id: str,
    ) -> BatchConvertResult:
        """Convert a single preprint item."""
        result = BatchConvertResult(item_id=item_id, title=title)

        if not url:
            result.error = "No URL provided"
            return result

        try:
            from gangdan.core.preprint_converter import PreprintConverter

            out_dir = self.output_dir / "preprints" / item_id
            out_dir.mkdir(parents=True, exist_ok=True)

            converter = PreprintConverter(fallback_to_pdf=True)
            conv_result = converter.convert_from_url(
                url,
                content_type=content_type,
                output_dir=out_dir,
                preprint_id=preprint_id or item_id,
            )

            if conv_result.success:
                result.success = True
                result.markdown_path = conv_result.markdown_path
                result.engine = conv_result.engine

                md_path = Path(conv_result.markdown_path)
                if md_path.exists():
                    result.markdown_content = md_path.read_text(encoding="utf-8")
            else:
                result.error = conv_result.error
        except Exception as e:
            logger.error("[ExportManager] Preprint convert failed for '%s': %s", item_id, e)
            result.error = str(e)

        return result

    def _convert_paper_item(
        self,
        item_id: str,
        title: str,
        pdf_path: str,
    ) -> BatchConvertResult:
        """Convert a single paper (PDF) item."""
        result = BatchConvertResult(item_id=item_id, title=title)

        if not pdf_path:
            result.error = "No PDF path provided"
            return result

        try:
            from gangdan.core.pdf_converter import PDFConverter

            pdf = Path(pdf_path)
            if not pdf.exists():
                result.error = f"PDF not found: {pdf_path}"
                return result

            out_dir = self.output_dir / "papers" / item_id
            out_dir.mkdir(parents=True, exist_ok=True)

            converter = PDFConverter()
            conv_result = converter.convert(pdf, output_dir=out_dir)

            if conv_result.success:
                result.success = True
                result.markdown_path = conv_result.markdown_path
                result.engine = conv_result.engine

                md_path = Path(conv_result.markdown_path)
                if md_path.exists():
                    result.markdown_content = md_path.read_text(encoding="utf-8")
            else:
                result.error = conv_result.error
        except Exception as e:
            logger.error("[ExportManager] Paper convert failed for '%s': %s", item_id, e)
            result.error = str(e)

        return result

    def _collect_markdown_item(
        self,
        item_id: str,
        title: str,
        md_path: str,
    ) -> BatchConvertResult:
        """Collect an existing Markdown file."""
        result = BatchConvertResult(item_id=item_id, title=title)

        if not md_path:
            result.error = "No Markdown path provided"
            return result

        try:
            path = Path(md_path)
            if not path.exists():
                result.error = f"Markdown not found: {md_path}"
                return result

            out_dir = self.output_dir / "markdown" / item_id
            out_dir.mkdir(parents=True, exist_ok=True)

            import shutil
            dest = out_dir / path.name
            shutil.copy2(path, dest)

            result.success = True
            result.markdown_path = str(dest)
            result.engine = "copy"
            result.markdown_content = path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error("[ExportManager] Markdown collect failed for '%s': %s", item_id, e)
            result.error = str(e)

        return result

    def _create_zip(
        self,
        results: List[BatchConvertResult],
        prefix: str = "export",
    ) -> str:
        """Create a ZIP file from successful conversion results.

        Parameters
        ----------
        results : List[BatchConvertResult]
            Conversion results.
        prefix : str
            ZIP filename prefix.

        Returns
        -------
        str
            Path to the ZIP file.
        """
        import datetime

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_dir = self.output_dir / "zip_exports"
        zip_dir.mkdir(parents=True, exist_ok=True)
        zip_path = zip_dir / f"{prefix}_{timestamp}.zip"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for r in results:
                if r.success and r.markdown_path:
                    md_path = Path(r.markdown_path)
                    if md_path.exists():
                        safe_name = self._safe_filename(r.title, r.item_id)
                        zf.write(md_path, arcname=f"{safe_name}.md")

                        images_dir = md_path.parent / "images"
                        if images_dir.exists():
                            for img in images_dir.rglob("*"):
                                if img.is_file():
                                    arcname = f"{safe_name}_images/{img.relative_to(images_dir)}"
                                    zf.write(img, arcname=arcname)

        logger.info("[ExportManager] Created ZIP: %s", zip_path)
        return str(zip_path)

    @staticmethod
    def _safe_filename(title: str, item_id: str) -> str:
        """Generate a safe filename from title."""
        import re

        safe = re.sub(r"[^\w\s-]", "", title.strip())
        safe = re.sub(r"[\s-]+", "_", safe)
        safe = safe[:80]

        if not safe:
            safe = item_id

        return safe
