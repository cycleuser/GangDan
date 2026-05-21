"""gd-convert - Convert PDF/CAJ files to Markdown.

Usage:
    gd-convert paper.pdf                      # Convert PDF to Markdown
    gd-convert paper.pdf --output ./out       # Specify output directory
    gd-convert paper.caj                      # Convert CAJ to Markdown
    gd-convert paper.pdf --engine marker      # Use marker engine
    ls *.pdf | gd-convert --stdin             # Convert all piped PDFs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(args=None) -> None:
    parser = argparse.ArgumentParser(
        prog="gd-convert",
        description="Convert PDF/CAJ files to Markdown",
    )
    parser.add_argument("file", nargs="?", help="Path to PDF/CAJ file")
    parser.add_argument("--stdin", action="store_true", help="Read file paths from stdin (one per line)")
    parser.add_argument("--output", "-o", default="", help="Output directory (default: same as input)")
    parser.add_argument("--engine", "-e", default="auto",
                        choices=["auto", "marker", "docling", "pymupdf"],
                        help="Conversion engine")
    from .common import add_common_args, init_env, output, output_error
    add_common_args(parser)
    parsed = parser.parse_args(args)
    init_env(parsed)

    if parsed.stdin:
        files = [Path(line.strip()) for line in sys.stdin if line.strip()]
    elif parsed.file:
        files = [Path(parsed.file)]
    else:
        output_error("File path required. Use positional arg or --stdin", parsed)

    from ..document.pdf_converter import PDFConverter
    from ..core.config import CONFIG

    output_dir = Path(parsed.output) if parsed.output else None
    converter = PDFConverter(engine=parsed.engine or CONFIG.document.pdf_convert_engine)

    results = []
    for filepath in files:
        if not filepath.exists():
            results.append({"file": str(filepath), "success": False, "error": "File not found"})
            continue

        try:
            is_caj = filepath.suffix.lower() == ".caj"
            if is_caj:
                from ..document.pdf_converter import CAJConverter
                caj_converter = CAJConverter()
                result = caj_converter.convert(str(filepath), output_dir=str(output_dir) if output_dir else None)
            else:
                result = converter.convert(str(filepath), output_dir=str(output_dir) if output_dir else None)

            out_path = output_dir / filepath.with_suffix(".md").name if output_dir else filepath.with_suffix(".md")
            results.append({
                "file": str(filepath),
                "success": True,
                "output": str(out_path) if out_path.exists() else str(result) if result else "converted",
            })
        except Exception as e:
            results.append({"file": str(filepath), "success": False, "error": str(e)})

    output({"success": all(r["success"] for r in results), "results": results, "count": len(results)}, parsed)