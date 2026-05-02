"""Tests for preprint_converter module."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gangdan.core.preprint_converter import PreprintConverter
from gangdan.core.research_models import ConversionResult


class TestPreprintConverter:
    """Test PreprintConverter."""

    def test_init_defaults(self) -> None:
        converter = PreprintConverter()
        assert converter.fallback_to_pdf is True

    def test_init_no_fallback(self) -> None:
        converter = PreprintConverter(fallback_to_pdf=False)
        assert converter.fallback_to_pdf is False


class TestHtmlToMarkdown:
    """Test HTML to Markdown conversion."""

    def test_basic_html(self) -> None:
        converter = PreprintConverter()
        html = "<h1>Title</h1><p>Paragraph text.</p>"
        result = converter.convert_html(html, Path(tempfile.mkdtemp()), "test123")

        assert result.success is True
        assert result.engine == "html-to-markdown"
        md_path = Path(result.markdown_path)
        assert md_path.exists()
        content = md_path.read_text()
        assert "Title" in content

    def test_html_with_math(self) -> None:
        converter = PreprintConverter()
        html = '<span class="ltx_Math" alttext="E = mc^2">E = mc²</span>'
        result = converter.convert_html(html, Path(tempfile.mkdtemp()), "test456")

        assert result.success is True
        md_path = Path(result.markdown_path)
        content = md_path.read_text()
        assert "E = mc^2" in content or "E = mc²" in content

    def test_html_with_headings(self) -> None:
        converter = PreprintConverter()
        html = "<h2>Section</h2><h3>Subsection</h3>"
        result = converter.convert_html(html, Path(tempfile.mkdtemp()), "test789")

        assert result.success is True
        md_path = Path(result.markdown_path)
        content = md_path.read_text()
        assert "## Section" in content
        assert "### Subsection" in content

    def test_html_with_links(self) -> None:
        converter = PreprintConverter()
        html = '<a href="https://example.com">Example</a>'
        result = converter.convert_html(html, Path(tempfile.mkdtemp()), "test_links")

        assert result.success is True
        md_path = Path(result.markdown_path)
        content = md_path.read_text()
        assert "[Example](https://example.com)" in content


class TestTexToMarkdown:
    """Test TeX to Markdown conversion."""

    def test_basic_tex(self) -> None:
        converter = PreprintConverter()
        tex = r"""
        \documentclass{article}
        \begin{document}
        \section{Introduction}
        This is the introduction.
        \end{document}
        """
        result = converter.convert_tex(tex, Path(tempfile.mkdtemp()), "tex_test")

        assert result.success is True
        assert result.engine == "tex-to-markdown"
        md_path = Path(result.markdown_path)
        content = md_path.read_text()
        assert "## Introduction" in content

    def test_tex_equations(self) -> None:
        converter = PreprintConverter()
        tex = r"""
        \begin{document}
        \begin{equation}
        E = mc^2
        \end{equation}
        \end{document}
        """
        result = converter.convert_tex(tex, Path(tempfile.mkdtemp()), "eq_test")

        assert result.success is True
        md_path = Path(result.markdown_path)
        content = md_path.read_text()
        assert "$$" in content
        assert "E = mc^2" in content

    def test_tex_bold_italic(self) -> None:
        converter = PreprintConverter()
        tex = r"\textbf{bold} and \textit{italic}"
        result = converter.convert_tex(tex, Path(tempfile.mkdtemp()), "fmt_test")

        assert result.success is True
        md_path = Path(result.markdown_path)
        content = md_path.read_text()
        assert "**bold**" in content
        assert "*italic*" in content

    def test_tex_citations(self) -> None:
        converter = PreprintConverter()
        tex = r"As shown in \cite{smith2023} and \citep{jones2024}."
        result = converter.convert_tex(tex, Path(tempfile.mkdtemp()), "cite_test")

        assert result.success is True
        md_path = Path(result.markdown_path)
        content = md_path.read_text()
        assert "[smith2023]" in content
        assert "[jones2024]" in content

    def test_tex_lists(self) -> None:
        converter = PreprintConverter()
        tex = r"""
        \begin{itemize}
        \item First item
        \item Second item
        \end{itemize}
        """
        result = converter.convert_tex(tex, Path(tempfile.mkdtemp()), "list_test")

        assert result.success is True
        md_path = Path(result.markdown_path)
        content = md_path.read_text()
        assert "- First item" in content
        assert "- Second item" in content

    def test_tex_remove_comments(self) -> None:
        converter = PreprintConverter()
        tex = r"Hello % this is a comment"
        result = converter._remove_comments(tex)
        assert "comment" not in result
        assert "Hello" in result

    def test_tex_remove_preamble(self) -> None:
        converter = PreprintConverter()
        tex = r"""\documentclass{article}
        \begin{document}
        Content here
        \end{document}
        """
        result = converter._remove_preamble(tex)
        assert "documentclass" not in result
        assert "Content here" in result


class TestJatsXmlToMarkdown:
    """Test JATS XML to Markdown conversion."""

    def test_basic_jats(self) -> None:
        import xml.etree.ElementTree as ET

        converter = PreprintConverter()
        xml_content = """<?xml version="1.0"?>
        <article>
            <front>
                <article-meta>
                    <title-group>
                        <article-title>Test Paper Title</article-title>
                    </title-group>
                </article-meta>
            </front>
            <body>
                <sec>
                    <title>Introduction</title>
                    <p>This is the introduction paragraph.</p>
                </sec>
            </body>
        </article>
        """
        root = ET.fromstring(xml_content)
        md = converter._jats_to_markdown(root)

        assert "# Test Paper Title" in md
        assert "## Introduction" in md
        assert "introduction paragraph" in md

    def test_jats_with_formula(self) -> None:
        import xml.etree.ElementTree as ET

        converter = PreprintConverter()
        xml_content = """<?xml version="1.0"?>
        <article>
            <body>
                <sec>
                    <title>Methods</title>
                    <p>We used the formula <inline-formula><alttext>E = mc^2</alttext></inline-formula>.</p>
                </sec>
            </body>
        </article>
        """
        root = ET.fromstring(xml_content)
        md = converter._jats_to_markdown(root)

        assert "$E = mc^2$" in md


class TestTexFileDetection:
    """Test main .tex file detection."""

    def test_find_main_tex_file(self) -> None:
        converter = PreprintConverter()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            main_tex = tmp_path / "main.tex"
            main_tex.write_text(r"\documentclass{article}\begin{document}Hello\end{document}")

            other_tex = tmp_path / "other.tex"
            other_tex.write_text(r"\usepackage{amsmath}")

            result = converter._find_main_tex_file(tmp_path)
            assert result == main_tex

    def test_find_main_tex_file_no_document(self) -> None:
        converter = PreprintConverter()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            tex_file = tmp_path / "paper.tex"
            tex_file.write_text(r"\usepackage{amsmath}")

            result = converter._find_main_tex_file(tmp_path)
            assert result == tex_file

    def test_find_main_tex_file_empty(self) -> None:
        converter = PreprintConverter()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            result = converter._find_main_tex_file(tmp_path)
            assert result is None


class TestCleanMarkdown:
    """Test Markdown cleaning."""

    def test_clean_markdown(self) -> None:
        converter = PreprintConverter()
        text = "Hello\n\n\n\nWorld"
        result = converter._clean_markdown(text)
        assert "\n\n\n" not in result
        assert "Hello" in result
        assert "World" in result
