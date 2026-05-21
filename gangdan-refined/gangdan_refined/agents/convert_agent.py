"""Convert agent — convert PDF/CAJ files to Markdown."""

from __future__ import annotations

from pathlib import Path
from .base import BaseAgent, AgentInput, AgentOutput, AgentMetadata


class ConvertAgent(BaseAgent):
    name = "gd-convert"
    description = "Convert PDF/CAJ files to Markdown"
    version = "2.0.0"

    def run(self, input: AgentInput) -> AgentOutput:
        file_path = input.file_path or input.options.get("file_path", "")
        engine = input.options.get("engine", "auto")

        if not file_path:
            text = input.text or input.query or ""
            if text and Path(text).exists():
                file_path = text
            else:
                return AgentOutput(success=False, error="File path required", metadata=AgentMetadata(agent=self.name, version=self.version))

        path = Path(file_path)
        if not path.exists():
            return AgentOutput(success=False, error=f"File not found: {file_path}", metadata=AgentMetadata(agent=self.name, version=self.version))

        try:
            from ..document.pdf_converter import PDFConverter, CAJConverter

            suffix = path.suffix.lower()
            if suffix == ".caj":
                converter = CAJConverter()
                if not converter.is_available():
                    return AgentOutput(success=False, error="CAJ conversion not available (missing cajparser)", metadata=AgentMetadata(agent=self.name, version=self.version))
                result = converter.convert(str(path))
            else:
                converter = PDFConverter(engine=engine)
                result = converter.convert(str(path))

            if isinstance(result, str):
                markdown = result
                pages = None
            elif isinstance(result, dict):
                markdown = result.get("markdown", result.get("text", str(result)))
                pages = result.get("pages")
            else:
                markdown = str(result)
                pages = None

            return AgentOutput(
                success=True,
                data={"markdown": markdown, "file": str(path), "engine": engine, "pages": pages, "size": len(markdown)},
                metadata=AgentMetadata(agent=self.name, version=self.version),
            )
        except Exception as e:
            return AgentOutput(success=False, error=str(e), metadata=AgentMetadata(agent=self.name, version=self.version))

    def add_arguments(self, parser) -> None:
        self.add_common_args(parser)
        parser.add_argument("file", nargs="?", default="", help="PDF/CAJ file path")
        parser.add_argument("--stdin", action="store_true", help="Read file path from stdin")
        parser.add_argument("--engine", "-e", default="auto", choices=["auto", "nuoyi", "docling", "pymupdf", "pdfplumber", "fallback"], help="Conversion engine")

    def build_input(self, args) -> AgentInput:
        return AgentInput(
            file_path=args.file,
            options={"engine": args.engine},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )