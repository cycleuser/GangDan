"""Preprint content converter: HTML/TeX to Markdown.

Converts preprint full-text content to clean Markdown for knowledge base
indexing. Supports multiple source formats with priority fallback:

1. HTML (ar5iv format) - best quality, formulas preserved as LaTeX
2. TeX/LaTeX source - can be parsed for structure and formulas
3. JATS XML (bioRxiv/medRxiv) - structured XML with formulas
4. PDF - fallback using existing PDFConverter

The converter prefers HTML/TeX over PDF because:
- HTML from ar5iv preserves math formulas as LaTeX
- TeX source has full structure information
- PDF conversion often loses formula quality
"""

from __future__ import annotations

import logging
import re
import tarfile
import tempfile
from pathlib import Path
from typing import Optional

from gangdan.core.research_models import ConversionResult

logger = logging.getLogger(__name__)


class PreprintConverter:
    """Convert preprint content (HTML/TeX/XML) to Markdown.

    Priority chain:
    1. HTML → Markdown (ar5iv format, formulas preserved)
    2. TeX → Markdown (LaTeX source parsing)
    3. JATS XML → Markdown (bioRxiv/medRxiv)
    4. PDF → Markdown (fallback via PDFConverter)

    Parameters
    ----------
    fallback_to_pdf : bool
        Whether to fall back to PDF conversion if HTML/TeX fails.
    """

    def __init__(self, fallback_to_pdf: bool = True) -> None:
        self.fallback_to_pdf = fallback_to_pdf

    def convert_from_url(
        self,
        url: str,
        content_type: str = "html",
        output_dir: Optional[Path] = None,
        preprint_id: str = "",
    ) -> ConversionResult:
        """Download and convert content from a URL.

        Parameters
        ----------
        url : str
            URL of the content (HTML page, TeX tarball, etc.).
        content_type : str
            Content type: 'html', 'tex', 'xml', 'pdf'.
        output_dir : Path or None
            Output directory. If None, uses temp directory.
        preprint_id : str
            Preprint identifier for naming output files.

        Returns
        -------
        ConversionResult
            Conversion result with paths and metadata.
        """
        import requests

        from gangdan.core.config import get_proxies

        try:
            resp = requests.get(
                url, timeout=60, proxies=get_proxies(),
                headers={"User-Agent": "GangDan/1.0 (https://github.com/cycleuser/GangDan)"}
            )
            resp.raise_for_status()

            if output_dir is None:
                output_dir = Path(tempfile.mkdtemp(prefix="gangdan_preprint_"))
            output_dir.mkdir(parents=True, exist_ok=True)

            if content_type == "html":
                return self.convert_html(resp.text, output_dir, preprint_id)
            elif content_type == "tex":
                return self.convert_tex_from_bytes(resp.content, output_dir, preprint_id)
            elif content_type == "xml":
                return self.convert_jats_xml(resp.text, output_dir, preprint_id)
            elif content_type == "pdf":
                return self._convert_pdf_fallback(url, output_dir, preprint_id)
            else:
                return ConversionResult(error=f"Unsupported content type: {content_type}")
        except Exception as e:
            logger.error("[PreprintConverter] Download failed: %s", e)
            return ConversionResult(error=f"Download failed: {e}")

    def convert_html(
        self,
        html_content: str,
        output_dir: Path,
        preprint_id: str = "",
    ) -> ConversionResult:
        """Convert HTML content (ar5iv format) to Markdown.

        ar5iv HTML preserves math formulas as LaTeX in <math> or <span> tags.
        This converter extracts and preserves formulas while converting
        the rest to clean Markdown.

        Parameters
        ----------
        html_content : str
            Raw HTML content from ar5iv or similar source.
        output_dir : Path
            Output directory for the Markdown file.
        preprint_id : str
            Preprint identifier for naming.

        Returns
        -------
        ConversionResult
            Conversion result.
        """
        try:
            markdown_text = self._html_to_markdown(html_content)
            filename = f"{preprint_id}.md" if preprint_id else "preprint.md"
            md_path = output_dir / filename
            md_path.write_text(markdown_text, encoding="utf-8")

            return ConversionResult(
                success=True,
                markdown_path=str(md_path),
                engine="html-to-markdown",
                page_count=1,
            )
        except Exception as e:
            logger.error("[PreprintConverter] HTML conversion failed: %s", e)
            return ConversionResult(error=f"HTML conversion failed: {e}")

    def convert_tex_from_bytes(
        self,
        tex_bytes: bytes,
        output_dir: Path,
        preprint_id: str = "",
    ) -> ConversionResult:
        """Convert TeX source tarball to Markdown.

        arXiv e-print is a gzipped tarball containing .tex files.
        This extracts the main .tex file and converts it to Markdown.

        Parameters
        ----------
        tex_bytes : bytes
            Raw tarball bytes from arXiv e-print.
        output_dir : Path
            Output directory.
        preprint_id : str
            Preprint identifier for naming.

        Returns
        -------
        ConversionResult
            Conversion result.
        """
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tar_path = Path(tmpdir) / "source.tar.gz"
                tar_path.write_bytes(tex_bytes)

                with tarfile.open(tar_path, "r:gz") as tar:
                    tar.extractall(tmpdir, filter="data")

                tex_file = self._find_main_tex_file(Path(tmpdir))
                if tex_file is None:
                    return ConversionResult(error="No .tex file found in tarball")

                tex_content = tex_file.read_text(encoding="utf-8", errors="replace")
                return self.convert_tex(tex_content, output_dir, preprint_id)
        except tarfile.TarError as e:
            logger.error("[PreprintConverter] Tar extraction failed: %s", e)
            return ConversionResult(error=f"Tar extraction failed: {e}")
        except Exception as e:
            logger.error("[PreprintConverter] TeX conversion failed: %s", e)
            return ConversionResult(error=f"TeX conversion failed: {e}")

    def convert_tex(
        self,
        tex_content: str,
        output_dir: Path,
        preprint_id: str = "",
    ) -> ConversionResult:
        """Convert LaTeX source content to Markdown.

        Handles:
        - Section commands (\\section, \\subsection, etc.)
        - Math environments ($...$, \\[...\\], \\begin{equation})
        - Basic formatting (\\textbf, \\textit, \\emph)
        - References and citations
        - Figures and tables (metadata only)

        Parameters
        ----------
        tex_content : str
            Raw LaTeX source content.
        output_dir : Path
            Output directory.
        preprint_id : str
            Preprint identifier for naming.

        Returns
        -------
        ConversionResult
            Conversion result.
        """
        try:
            markdown_text = self._tex_to_markdown(tex_content)
            filename = f"{preprint_id}.md" if preprint_id else "preprint.md"
            md_path = output_dir / filename
            md_path.write_text(markdown_text, encoding="utf-8")

            return ConversionResult(
                success=True,
                markdown_path=str(md_path),
                engine="tex-to-markdown",
                page_count=1,
            )
        except Exception as e:
            logger.error("[PreprintConverter] TeX conversion failed: %s", e)
            return ConversionResult(error=f"TeX conversion failed: {e}")

    def convert_jats_xml(
        self,
        xml_content: str,
        output_dir: Path,
        preprint_id: str = "",
    ) -> ConversionResult:
        """Convert JATS XML (bioRxiv/medRxiv) to Markdown.

        JATS XML is the standard format for bioRxiv/medRxiv full text.
        This extracts sections, paragraphs, formulas, and references.

        Parameters
        ----------
        xml_content : str
            Raw JATS XML content.
        output_dir : Path
            Output directory.
        preprint_id : str
            Preprint identifier for naming.

        Returns
        -------
        ConversionResult
            Conversion result.
        """
        try:
            import xml.etree.ElementTree as ET

            root = ET.fromstring(xml_content)
            markdown_text = self._jats_to_markdown(root)

            filename = f"{preprint_id}.md" if preprint_id else "preprint.md"
            md_path = output_dir / filename
            md_path.write_text(markdown_text, encoding="utf-8")

            return ConversionResult(
                success=True,
                markdown_path=str(md_path),
                engine="jats-to-markdown",
                page_count=1,
            )
        except Exception as e:
            logger.error("[PreprintConverter] JATS XML conversion failed: %s", e)
            return ConversionResult(error=f"JATS XML conversion failed: {e}")

    def _html_to_markdown(self, html: str) -> str:
        """Convert ar5iv-style HTML to Markdown.

        Preserves math formulas as LaTeX while converting structure.

        Parameters
        ----------
        html : str
            Raw HTML content.

        Returns
        -------
        str
            Converted Markdown.
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return self._basic_html_to_markdown(html)

        soup = BeautifulSoup(html, "html.parser")

        self._preserve_math_formulas(soup)
        self._convert_headings(soup)
        self._convert_lists(soup)
        self._convert_links(soup)
        self._convert_images(soup)
        self._convert_tables(soup)

        text = soup.get_text("\n", strip=True)
        return self._clean_markdown(text)

    def _preserve_math_formulas(self, soup) -> None:
        """Convert math elements to LaTeX format."""
        for math_elem in soup.find_all(["math", "span"], class_=re.compile(r"ltx_Math|math")):
            latex = math_elem.get("alttext", "") or math_elem.get_text()
            if latex:
                is_display = math_elem.get("display", "") == "block"
                if is_display:
                    math_elem.replace_with(f"\n\n$${latex}$$\n\n")
                else:
                    math_elem.replace_with(f"${latex}$")

        for eq_elem in soup.find_all(["div", "span"], class_=re.compile(r"ltx_equation")):
            latex = eq_elem.get("alttext", "") or eq_elem.get_text()
            if latex:
                eq_elem.replace_with(f"\n\n$${latex}$$\n\n")

    def _convert_headings(self, soup) -> None:
        """Convert HTML headings to Markdown."""
        for i in range(1, 7):
            for tag in soup.find_all(f"h{i}"):
                prefix = "#" * i
                tag.replace_with(f"\n\n{prefix} {tag.get_text()}\n\n")

    def _convert_lists(self, soup) -> None:
        """Convert HTML lists to Markdown."""
        for ul in soup.find_all("ul"):
            for li in ul.find_all("li"):
                li.replace_with(f"- {li.get_text()}\n")
            ul.replace_with(ul.get_text())

        for ol in soup.find_all("ol"):
            for idx, li in enumerate(ol.find_all("li"), 1):
                li.replace_with(f"{idx}. {li.get_text()}\n")
            ol.replace_with(ol.get_text())

    def _convert_links(self, soup) -> None:
        """Convert HTML links to Markdown."""
        for a in soup.find_all("a", href=True):
            text = a.get_text().strip()
            href = a["href"]
            if text and href:
                a.replace_with(f"[{text}]({href})")

    def _convert_images(self, soup) -> None:
        """Convert HTML images to Markdown."""
        for img in soup.find_all("img", src=True):
            alt = img.get("alt", "")
            src = img["src"]
            img.replace_with(f"![{alt}]({src})")

    def _convert_tables(self, soup) -> None:
        """Convert HTML tables to Markdown table format."""
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if not rows:
                continue

            md_rows = []
            for row in rows:
                cells = row.find_all(["td", "th"])
                cell_text = "|".join(c.get_text().strip() for c in cells)
                md_rows.append(f"|{cell_text}|")

                if row.find_all("th"):
                    header_sep = "|".join("---" for _ in cells)
                    md_rows.insert(-1, f"|{header_sep}|")

            table.replace_with("\n\n" + "\n".join(md_rows) + "\n\n")

    def _basic_html_to_markdown(self, html: str) -> str:
        """Basic HTML to Markdown conversion without BeautifulSoup."""
        text = html

        text = re.sub(r"<h([1-6])[^>]*>(.*?)</h\1>", r"\n\n#{1} \2\n\n", text)
        text = re.sub(r"<h([1-6])[^>]*>(.*?)</h\1>", lambda m: f"\n\n{'#' * int(m.group(1))} {m.group(2)}\n\n", text)
        text = re.sub(r"<strong[^>]*>(.*?)</strong>", r"**\1**", text)
        text = re.sub(r"<em[^>]*>(.*?)</em>", r"*\1*", text)
        text = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", text)
        text = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r"[\2](\1)", text)
        text = re.sub(r"<br\s*/?>", "\n", text)
        text = re.sub(r"<p[^>]*>", "\n\n", text)
        text = re.sub(r"</p>", "\n\n", text)
        text = re.sub(r"<[^>]+>", "", text)

        return self._clean_markdown(text)

    def _tex_to_markdown(self, tex: str) -> str:
        """Convert LaTeX source to Markdown.

        Parameters
        ----------
        tex : str
            Raw LaTeX source.

        Returns
        -------
        str
            Converted Markdown.
        """
        md = tex

        md = self._remove_comments(md)
        md = self._remove_preamble(md)
        md = self._convert_sections(md)
        md = self._convert_bold_italic(md)
        md = self._convert_lists_tex(md)
        md = self._convert_equations(md)
        md = self._convert_citations(md)
        md = self._convert_references(md)
        md = self._convert_figures_tables(md)
        md = self._clean_tex(md)

        return md

    def _remove_comments(self, tex: str) -> str:
        """Remove LaTeX comments."""
        lines = tex.split("\n")
        cleaned = []
        for line in lines:
            in_math = False
            result = []
            for i, char in enumerate(line):
                if char == "%" and (i == 0 or line[i - 1] != "\\"):
                    break
                result.append(char)
            cleaned.append("".join(result).rstrip())
        return "\n".join(cleaned)

    def _remove_preamble(self, tex: str) -> str:
        """Remove LaTeX preamble (before \\begin{document})."""
        match = re.search(r"\\begin\{document\}", tex)
        if match:
            tex = tex[match.end():]
        tex = re.sub(r"\\end\{document\}.*$", "", tex, flags=re.DOTALL)
        return tex

    def _convert_sections(self, tex: str) -> str:
        """Convert LaTeX section commands to Markdown headings."""
        tex = re.sub(r"\\part\*?\{(.*?)\}", r"\n\n# \1\n\n", tex)
        tex = re.sub(r"\\chapter\*?\{(.*?)\}", r"\n\n# \1\n\n", tex)
        tex = re.sub(r"\\section\*?\{(.*?)\}", r"\n\n## \1\n\n", tex)
        tex = re.sub(r"\\subsection\*?\{(.*?)\}", r"\n\n### \1\n\n", tex)
        tex = re.sub(r"\\subsubsection\*?\{(.*?)\}", r"\n\n#### \1\n\n", tex)
        return tex

    def _convert_bold_italic(self, tex: str) -> str:
        """Convert LaTeX formatting to Markdown."""
        tex = re.sub(r"\\textbf\{(.*?)\}", r"**\1**", tex)
        tex = re.sub(r"\\textit\{(.*?)\}", r"*\1*", tex)
        tex = re.sub(r"\\emph\{(.*?)\}", r"*\1*", tex)
        tex = re.sub(r"\\texttt\{(.*?)\}", r"`\1`", tex)
        tex = re.sub(r"\\verb\|([^|]*)\|", r"`\1`", tex)
        return tex

    def _convert_lists_tex(self, tex: str) -> str:
        """Convert LaTeX lists to Markdown."""
        def replace_itemize(match: re.Match) -> str:
            content = match.group(1)
            items = re.split(r"\\item\s*", content)
            items = [f"- {item.strip()}" for item in items if item.strip()]
            return "\n" + "\n".join(items) + "\n"

        tex = re.sub(r"\\begin\{itemize\}(.*?)\\end\{itemize\}", replace_itemize, tex, flags=re.DOTALL)

        def replace_enumerate(match: re.Match) -> str:
            content = match.group(1)
            items = re.split(r"\\item\s*", content)
            items = [f"{idx}. {item.strip()}" for idx, item in enumerate(items, 1) if item.strip()]
            return "\n" + "\n".join(items) + "\n"

        tex = re.sub(r"\\begin\{enumerate\}(.*?)\\end\{enumerate\}", replace_enumerate, tex, flags=re.DOTALL)
        return tex

    def _convert_equations(self, tex: str) -> str:
        """Convert LaTeX equations to Markdown math."""
        tex = re.sub(r"\$\$(.*?)\$\$", r"\n\n$$\1$$\n\n", tex, flags=re.DOTALL)
        tex = re.sub(r"\\\[(.*?)\\\]", r"\n\n$$\1$$\n\n", tex, flags=re.DOTALL)

        def replace_equation(match: re.Match) -> str:
            content = match.group(1)
            return f"\n\n$${content}$$\n\n"

        tex = re.sub(r"\\begin\{equation\}(.*?)\\end\{equation\}", replace_equation, tex, flags=re.DOTALL)
        tex = re.sub(r"\\begin\{align\}(.*?)\\end\{align\}", replace_equation, tex, flags=re.DOTALL)
        return tex

    def _convert_citations(self, tex: str) -> str:
        """Convert LaTeX citations to Markdown."""
        tex = re.sub(r"\\cite\{(.*?)\}", r"[\1]", tex)
        tex = re.sub(r"\\citep\{(.*?)\}", r"[\1]", tex)
        tex = re.sub(r"\\citet\{(.*?)\}", r"[\1]", tex)
        return tex

    def _convert_references(self, tex: str) -> str:
        """Convert LaTeX bibliography to Markdown heading."""
        tex = re.sub(r"\\bibliography\{.*?\}", "\n\n## References\n", tex)
        tex = re.sub(r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}", "\n\n## References\n", tex, flags=re.DOTALL)
        tex = re.sub(r"\\bibitem\{(.*?)\}", r"\n- **[\1]** ", tex)
        return tex

    def _convert_figures_tables(self, tex: str) -> str:
        """Convert LaTeX figures and tables to Markdown placeholders."""
        def replace_figure(match: re.Match) -> str:
            content = match.group(1)
            caption = re.search(r"\\caption\{(.*?)\}", content)
            caption_text = caption.group(1) if caption else ""
            include = re.search(r"\\includegraphics.*?\{(.*?)\}", content)
            img_path = include.group(1) if include else ""
            result = f"\n\n![{caption_text}]({img_path})\n\n"
            return result

        tex = re.sub(r"\\begin\{figure\}(.*?)\\end\{figure\}", replace_figure, tex, flags=re.DOTALL)
        tex = re.sub(r"\\begin\{table\}.*?\\end\{table\}", "\n\n[Table]\n\n", tex, flags=re.DOTALL)
        return tex

    def _clean_tex(self, tex: str) -> str:
        """Clean up remaining LaTeX commands."""
        tex = re.sub(r"\\[a-zA-Z]+\*?\{", "", tex)
        tex = re.sub(r"\\[a-zA-Z]+\*?", "", tex)
        tex = re.sub(r"\{", "", tex)
        tex = re.sub(r"\}", "", tex)
        tex = re.sub(r"\n{3,}", "\n\n", tex)
        return tex.strip()

    def _jats_to_markdown(self, root) -> str:
        """Convert JATS XML tree to Markdown.

        Parameters
        ----------
        root : Element
            XML root element.

        Returns
        -------
        str
            Converted Markdown.
        """
        parts = []

        title = root.find(".//article-title")
        if title is not None and title.text:
            parts.append(f"# {title.text.strip()}\n")

        abstract = root.find(".//abstract")
        if abstract is not None:
            abs_text = self._extract_text(abstract)
            if abs_text:
                parts.append("## Abstract\n")
                parts.append(abs_text.strip() + "\n")

        body = root.find(".//body")
        if body is not None:
            for sec in body.findall(".//sec"):
                title_elem = sec.find("title")
                if title_elem is not None and title_elem.text:
                    parts.append(f"\n## {title_elem.text.strip()}\n")

                for p in sec.findall(".//p"):
                    text = self._extract_text(p)
                    if text:
                        parts.append(text.strip() + "\n")

        return "\n".join(parts)

    def _extract_text(self, elem) -> str:
        """Extract text from XML element, preserving some structure."""
        parts = []
        if elem.text:
            parts.append(elem.text.strip())

        for child in elem:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

            if tag == "italic":
                text = child.text or ""
                if child.tail:
                    text += child.tail
                parts.append(f"*{text.strip()}*")
            elif tag == "bold":
                text = child.text or ""
                if child.tail:
                    text += child.tail
                parts.append(f"**{text.strip()}**")
            elif tag == "disp-formula":
                latex = child.get("alttext", "") or "".join(child.itertext())
                parts.append(f"\n\n$${latex}$$\n\n")
            elif tag == "inline-formula":
                latex = child.get("alttext", "") or "".join(child.itertext())
                parts.append(f"${latex}$")
            elif tag == "xref":
                ref_text = child.text or ""
                parts.append(f"[{ref_text}]")
            else:
                child_text = self._extract_text(child)
                if child_text:
                    parts.append(child_text)

            if child.tail:
                parts.append(child.tail.strip())

        return " ".join(p for p in parts if p)

    def _clean_markdown(self, text: str) -> str:
        """Clean up Markdown text."""
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _find_main_tex_file(self, directory: Path) -> Optional[Path]:
        """Find the main .tex file in extracted tarball.

        Looks for files that contain \\begin{document}.

        Parameters
        ----------
        directory : Path
            Directory containing extracted files.

        Returns
        -------
        Path or None
            Path to main .tex file, or None if not found.
        """
        tex_files = list(directory.rglob("*.tex"))

        for tex_file in tex_files:
            try:
                content = tex_file.read_text(encoding="utf-8", errors="replace")
                if "\\begin{document}" in content:
                    return tex_file
            except Exception:
                continue

        if tex_files:
            return tex_files[0]

        return None

    def _convert_pdf_fallback(
        self,
        url: str,
        output_dir: Path,
        preprint_id: str,
    ) -> ConversionResult:
        """Fallback to PDF conversion via PDFConverter.

        Parameters
        ----------
        url : str
            PDF URL.
        output_dir : Path
            Output directory.
        preprint_id : str
            Preprint identifier.

        Returns
        -------
        ConversionResult
            Conversion result.
        """
        import requests

        from gangdan.core.config import get_proxies
        from gangdan.core.pdf_converter import PDFConverter

        try:
            resp = requests.get(url, timeout=120, proxies=get_proxies())
            resp.raise_for_status()

            pdf_path = output_dir / f"{preprint_id}.pdf"
            pdf_path.write_bytes(resp.content)

            converter = PDFConverter()
            return converter.convert(pdf_path, output_dir)
        except Exception as e:
            logger.error("[PreprintConverter] PDF fallback failed: %s", e)
            return ConversionResult(error=f"PDF fallback failed: {e}")
