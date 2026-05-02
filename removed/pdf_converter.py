"""PDF to Markdown conversion using NuoYi.

Integrates the NuoYi library for high-quality PDF-to-Markdown conversion
with formula (LaTeX), image, and table preservation.

When NuoYi is not installed, falls back to a basic pymupdf4llm-based
conversion or simple text extraction.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional

from gangdan.core.research_models import ConversionResult

logger = logging.getLogger(__name__)


class PDFConverter:
    """Convert PDF files to Markdown with formula and image preservation.

    Uses NuoYi when available for best quality, falls back to simpler
    extraction methods otherwise.

    Parameters
    ----------
    engine : str
        Conversion engine: 'auto', 'marker', 'pymupdf', 'pdfplumber',
        'docling', 'mineru', or cloud services.
    device : str
        Device for model-based engines: 'auto', 'cuda', 'cpu'.
    low_vram : bool
        Enable low VRAM mode for GPU-constrained environments.
    """

    ENGINE_PRIORITY = ["marker", "pymupdf", "docling", "mineru", "pdfplumber"]

    def __init__(
        self,
        engine: str = "auto",
        device: str = "auto",
        low_vram: bool = False,
    ) -> None:
        self.engine = engine
        self.device = device
        self.low_vram = low_vram

    def convert(
        self,
        pdf_path: Path,
        output_dir: Optional[Path] = None,
    ) -> ConversionResult:
        """Convert a PDF file to Markdown.

        Parameters
        ----------
        pdf_path : Path
            Path to the PDF file.
        output_dir : Path or None
            Output directory. If None, same directory as PDF.

        Returns
        -------
        ConversionResult
            Conversion result with paths and metadata.
        """
        if not pdf_path.exists():
            return ConversionResult(error=f"PDF not found: {pdf_path}")

        if output_dir is None:
            output_dir = pdf_path.parent

        output_dir.mkdir(parents=True, exist_ok=True)

        engine = self._resolve_engine()

        try:
            if engine in ("marker", "docling", "mineru", "pymupdf", "pdfplumber", "llamaparse", "mathpix", "doc2x"):
                return self._convert_with_nuoyi(pdf_path, output_dir, engine)
            else:
                return self._convert_fallback(pdf_path, output_dir)
        except Exception as e:
            logger.error("[PDFConverter] Conversion failed: %s", e)
            return ConversionResult(error=str(e))

    def _resolve_engine(self) -> str:
        """Determine which conversion engine to use.

        Returns
        -------
        str
            Engine name to use.
        """
        if self.engine != "auto":
            return self.engine

        try:
            import nuoyi
            return "marker"
        except ImportError:
            pass

        try:
            import pymupdf4llm
            return "pymupdf"
        except ImportError:
            pass

        try:
            import pdfplumber
            return "pdfplumber"
        except ImportError:
            pass

        return "basic"

    def _convert_with_nuoyi(
        self,
        pdf_path: Path,
        output_dir: Path,
        engine: str,
    ) -> ConversionResult:
        """Convert PDF using NuoYi library.

        Parameters
        ----------
        pdf_path : Path
            Path to the PDF file.
        output_dir : Path
            Output directory.
        engine : str
            NuoYi engine name.

        Returns
        -------
        ConversionResult
            Conversion result.
        """
        try:
            from nuoyi.api import convert_file

            result = convert_file(
                str(pdf_path),
                engine=engine,
                device=self.device,
                low_vram=self.low_vram,
            )

            if not result.success:
                return ConversionResult(error=result.error or "NuoYi conversion failed")

            markdown_text = result.data.get("markdown", "")
            output_path = result.data.get("output_path", "")

            if output_path:
                md_path = Path(output_path)
            else:
                md_path = output_dir / pdf_path.with_suffix(".md").name
                md_path.write_text(markdown_text, encoding="utf-8")

            page_count = 0
            try:
                import fitz
                doc = fitz.open(str(pdf_path))
                page_count = len(doc)
                doc.close()
            except Exception:
                pass

            return ConversionResult(
                success=True,
                markdown_path=str(md_path),
                images_dir=str(output_dir / pdf_path.stem / "images"),
                engine=f"nuoyi-{engine}",
                page_count=page_count,
            )

        except ImportError:
            logger.info("[PDFConverter] NuoYi not available, falling back")
            return self._convert_fallback(pdf_path, output_dir)

    def _convert_fallback(
        self,
        pdf_path: Path,
        output_dir: Path,
    ) -> ConversionResult:
        """Fallback PDF conversion using available libraries.

        Tries pymupdf4llm first, then basic PDF text extraction.

        Parameters
        ----------
        pdf_path : Path
            Path to the PDF file.
        output_dir : Path
            Output directory.

        Returns
        -------
        ConversionResult
            Conversion result.
        """
        md_path = output_dir / pdf_path.with_suffix(".md").name

        try:
            import pymupdf4llm

            md_text = pymupdf4llm.to_markdown(str(pdf_path))
            md_path.write_text(md_text, encoding="utf-8")

            page_count = 0
            try:
                import fitz

                doc = fitz.open(str(pdf_path))
                page_count = len(doc)
                doc.close()
            except Exception:
                pass

            return ConversionResult(
                success=True,
                markdown_path=str(md_path),
                engine="pymupdf4llm",
                page_count=page_count,
            )
        except ImportError:
            pass

        try:
            import fitz

            doc = fitz.open(str(pdf_path))
            page_count = len(doc)
            text_parts = []

            for page in doc:
                text_parts.append(page.get_text("text"))

            doc.close()

            md_text = "\n\n".join(text_parts)
            md_path.write_text(md_text, encoding="utf-8")

            return ConversionResult(
                success=True,
                markdown_path=str(md_path),
                engine="pymupdf_basic",
                page_count=page_count,
            )
        except ImportError:
            return ConversionResult(
                error="No PDF conversion library available. Install nuoyi, pymupdf4llm, or pymupdf."
            )