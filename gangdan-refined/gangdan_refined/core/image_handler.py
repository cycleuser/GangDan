"""Image handling for knowledge base documents."""

from __future__ import annotations

import base64
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class ImageProcessResult:
    """Result of processing images in a document."""
    updated_content: str
    copied_count: int
    errors: List[str]


class ImageHandler:
    """Handles image extraction and processing in markdown documents."""

    def __init__(self, kb_dir: Path):
        self.kb_dir = kb_dir
        self.images_dir = kb_dir / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def process_document(self, content: str, source_path: Path,
                         embed_mode: str = "copy") -> ImageProcessResult:
        """Process all images referenced in a markdown document.

        Parameters
        ----------
        content : str
            Markdown content with image references.
        source_path : Path
            Path to the source markdown file.
        embed_mode : str
            How to handle images: 'copy', 'base64', or 'reference'.

        Returns
        -------
        ImageProcessResult
            Processing result with updated content.
        """
        pattern = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
        copied_count = 0
        errors = []

        def replace_image(match):
            nonlocal copied_count
            alt_text = match.group(1)
            img_path = match.group(2)
            try:
                if embed_mode == "base64":
                    return self._embed_base64(alt_text, img_path, source_path)
                elif embed_mode == "copy":
                    new_path = self._copy_image(img_path, source_path)
                    if new_path:
                        copied_count += 1
                        return f"![{alt_text}]({new_path})"
                return match.group(0)
            except Exception as e:
                errors.append(str(e))
                return match.group(0)

        updated_content = pattern.sub(replace_image, content)
        return ImageProcessResult(updated_content=updated_content, copied_count=copied_count, errors=errors)

    def _embed_base64(self, alt_text: str, img_path: str, source_path: Path) -> str:
        """Embed image as base64 data URI."""
        full_path = self._resolve_image_path(img_path, source_path)
        if full_path and full_path.exists():
            with open(full_path, "rb") as f:
                data = base64.b64encode(f.read()).decode("utf-8")
            ext = full_path.suffix.lower().lstrip(".")
            mime = f"image/{ext}" if ext in ("png", "jpg", "jpeg", "gif", "webp", "svg") else "image/png"
            return f"![{alt_text}](data:{mime};base64,{data})"
        return f"![{alt_text}]({img_path})"

    def _copy_image(self, img_path: str, source_path: Path) -> Optional[str]:
        """Copy image to KB images directory."""
        full_path = self._resolve_image_path(img_path, source_path)
        if full_path and full_path.exists():
            dest = self.images_dir / full_path.name
            if not dest.exists():
                shutil.copy2(full_path, dest)
            return f"images/{full_path.name}"
        return None

    def _resolve_image_path(self, img_path: str, source_path: Path) -> Optional[Path]:
        """Resolve image path relative to source file or absolute."""
        if img_path.startswith(("http://", "https://", "data:")):
            return None
        if Path(img_path).is_absolute():
            return Path(img_path)
        source_dir = source_path.parent
        resolved = source_dir / img_path
        if resolved.exists():
            return resolved
        return None

    def list_images(self) -> List[Dict]:
        """List all images in the KB images directory."""
        images = []
        if self.images_dir.exists():
            for img in self.images_dir.iterdir():
                if img.is_file() and img.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
                    images.append({"name": img.name, "size": img.stat().st_size, "path": str(img)})
        return images
