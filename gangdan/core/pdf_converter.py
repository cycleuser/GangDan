"""PDF to Markdown conversion with multiple engine support.

Integrates multiple libraries for high-quality PDF-to-Markdown conversion
with formula (LaTeX), image, and table preservation:

1. NuoYi (wrapper for marker/docling/mineru/etc.)
2. Docling (direct IBM docling integration)
3. PyMuPDF4LLM (fast, lightweight)
4. PyMuPDF basic text extraction (fallback)

Engines are tried in priority order with automatic fallback.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from gangdan.core.research_models import ConversionResult

logger = logging.getLogger(__name__)


class PDFConverter:
    """Convert PDF files to Markdown with formula and image preservation.

    Uses the best available engine in priority order:
    1. NuoYi (if installed) - supports marker/docling/mineru/etc.
    2. Docling (direct) - IBM's document understanding
    3. PyMuPDF4LLM - fast, lightweight
    4. PyMuPDF basic - text-only fallback

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

    ENGINE_PRIORITY = ["marker", "docling", "pymupdf", "mineru", "pdfplumber"]

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
            if engine in ("marker", "mineru", "llamaparse", "mathpix", "doc2x"):
                return self._convert_with_nuoyi(pdf_path, output_dir, engine)
            elif engine == "docling":
                return self._convert_with_docling(pdf_path, output_dir)
            elif engine == "pymupdf":
                return self._convert_with_pymupdf4llm(pdf_path, output_dir)
            elif engine == "pdfplumber":
                return self._convert_with_pdfplumber(pdf_path, output_dir)
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

        # Try NuoYi first (supports multiple engines)
        try:
            import nuoyi
            return "marker"
        except ImportError:
            pass

        # Try direct docling
        try:
            from docling.document_converter import DocumentConverter
            return "docling"
        except ImportError:
            pass

        # Try pymupdf4llm
        try:
            import pymupdf4llm
            return "pymupdf"
        except ImportError:
            pass

        # Try pdfplumber
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

            page_count = self._get_page_count(pdf_path)

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

    def _convert_with_docling(
        self,
        pdf_path: Path,
        output_dir: Path,
    ) -> ConversionResult:
        """Convert PDF using direct docling integration.

        Reference: IBM Docling's DocumentConverter API.

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
        try:
            from docling.document_converter import DocumentConverter

            converter = DocumentConverter()
            result = converter.convert(str(pdf_path))

            markdown_text = result.document.export_to_markdown()
            md_path = output_dir / pdf_path.with_suffix(".md").name
            md_path.write_text(markdown_text, encoding="utf-8")

            page_count = len(result.pages) if hasattr(result, 'pages') else self._get_page_count(pdf_path)

            return ConversionResult(
                success=True,
                markdown_path=str(md_path),
                images_dir=str(output_dir / pdf_path.stem / "images"),
                engine="docling",
                page_count=page_count,
            )

        except ImportError:
            logger.info("[PDFConverter] Docling not available, falling back")
            return self._convert_fallback(pdf_path, output_dir)
        except Exception as e:
            logger.error("[PDFConverter] Docling conversion failed: %s", e)
            return self._convert_fallback(pdf_path, output_dir)

    def _convert_with_pymupdf4llm(
        self,
        pdf_path: Path,
        output_dir: Path,
    ) -> ConversionResult:
        """Convert PDF using pymupdf4llm.

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
        try:
            import pymupdf4llm

            md_text = pymupdf4llm.to_markdown(str(pdf_path))
            md_path = output_dir / pdf_path.with_suffix(".md").name
            md_path.write_text(md_text, encoding="utf-8")

            page_count = self._get_page_count(pdf_path)

            return ConversionResult(
                success=True,
                markdown_path=str(md_path),
                engine="pymupdf4llm",
                page_count=page_count,
            )

        except ImportError:
            logger.info("[PDFConverter] pymupdf4llm not available, falling back")
            return self._convert_fallback(pdf_path, output_dir)

    def _convert_with_pdfplumber(
        self,
        pdf_path: Path,
        output_dir: Path,
    ) -> ConversionResult:
        """Convert PDF using pdfplumber.

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
        try:
            import pdfplumber

            md_parts = []
            with pdfplumber.open(str(pdf_path)) as pdf:
                page_count = len(pdf.pages)
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        md_parts.append(text)

            md_text = "\n\n".join(md_parts)
            md_path = output_dir / pdf_path.with_suffix(".md").name
            md_path.write_text(md_text, encoding="utf-8")

            return ConversionResult(
                success=True,
                markdown_path=str(md_path),
                engine="pdfplumber",
                page_count=page_count,
            )

        except ImportError:
            logger.info("[PDFConverter] pdfplumber not available, falling back")
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
        # Try pymupdf4llm
        try:
            import pymupdf4llm

            md_text = pymupdf4llm.to_markdown(str(pdf_path))
            md_path = output_dir / pdf_path.with_suffix(".md").name
            md_path.write_text(md_text, encoding="utf-8")

            return ConversionResult(
                success=True,
                markdown_path=str(md_path),
                engine="pymupdf4llm",
                page_count=self._get_page_count(pdf_path),
            )
        except ImportError:
            pass

        # Try basic PyMuPDF
        try:
            import fitz

            doc = fitz.open(str(pdf_path))
            page_count = len(doc)
            text_parts = [page.get_text("text") for page in doc]
            doc.close()

            md_text = "\n\n".join(text_parts)
            md_path = output_dir / pdf_path.with_suffix(".md").name
            md_path.write_text(md_text, encoding="utf-8")

            return ConversionResult(
                success=True,
                markdown_path=str(md_path),
                engine="pymupdf_basic",
                page_count=page_count,
            )
        except ImportError:
            pass

        return ConversionResult(
            error="No PDF conversion library available. Install nuoyi, docling, pymupdf4llm, or pymupdf."
        )

    @staticmethod
    def _get_page_count(pdf_path: Path) -> int:
        """Get the number of pages in a PDF file.

        Parameters
        ----------
        pdf_path : Path
            Path to the PDF file.

        Returns
        -------
        int
            Number of pages, or 0 if unable to determine.
        """
        try:
            import fitz
            doc = fitz.open(str(pdf_path))
            count = len(doc)
            doc.close()
            return count
        except Exception:
            return 0