"""Image handler for Markdown documents in knowledge base.

This module provides elegant image support for Markdown documents:
1. Parse image references from Markdown
2. Copy images to KB's images/ directory
3. Update image paths in metadata
4. Provide image access via API
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}

IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".bmp": "image/bmp",
    ".ico": "image/x-icon",
}


@dataclass
class ImageRef:
    """Represents an image reference in a Markdown document."""

    original_text: str
    alt_text: str
    original_path: str
    new_path: Optional[str] = None
    is_external: bool = False
    is_base64: bool = False
    base64_data: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ImageProcessResult:
    """Result of processing images in a document."""

    images: List[ImageRef] = field(default_factory=list)
    updated_content: str = ""
    image_count: int = 0
    copied_count: int = 0
    error_count: int = 0

    def get_image_metadata(self) -> List[Dict]:
        """Get image metadata for storage."""
        result = []
        for img in self.images:
            if img.new_path and not img.error:
                result.append(
                    {
                        "original_path": img.original_path,
                        "new_path": img.new_path,
                        "alt_text": img.alt_text,
                        "is_external": img.is_external,
                        "is_base64": img.is_base64,
                    }
                )
        return result

    def get_image_manifest(self, source_file: str) -> Dict:
        """Get complete image manifest for a source file."""
        return {
            "source_file": source_file,
            "images": self.get_image_metadata(),
            "image_count": len(self.images),
        }


class ImageHandler:
    """Handle images in Markdown documents for knowledge base."""

    MD_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
    HTML_IMG_PATTERN = re.compile(
        r'<img[^>]+src=["\']([^"\']+)["\'][^>]*alt=["\']([^"\']*)["\'][^>]*>',
        re.IGNORECASE,
    )
    HTML_IMG_PATTERN2 = re.compile(
        r'<img[^>]+alt=["\']([^"\']*)["\'][^>]+src=["\']([^"\']+)["\'][^>]*>',
        re.IGNORECASE,
    )
    DATA_URI_PATTERN = re.compile(r"^data:image/([a-z]+);base64,(.+)$", re.IGNORECASE)

    def __init__(self, kb_dir: Path):
        self.kb_dir = Path(kb_dir)
        self.images_dir = self.kb_dir / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def process_document(
        self,
        content: str,
        source_path: Path,
        embed_mode: str = "copy",
    ) -> ImageProcessResult:
        """Process images in a Markdown document.

        Parameters
        ----------
        content : str
            Markdown content.
        source_path : Path
            Source document path.
        embed_mode : str
            Image processing mode: "copy", "base64", or "reference".

        Returns
        -------
        ImageProcessResult
            Processed result with updated content.
        """
        result = ImageProcessResult()
        result.updated_content = content

        # Find all markdown images
        for match in self.MD_IMAGE_PATTERN.finditer(content):
            alt_text = match.group(1)
            image_path = match.group(2)

            img_ref = ImageRef(
                original_text=match.group(0),
                alt_text=alt_text,
                original_path=image_path,
            )

            # Check if it's base64
            base64_match = self.DATA_URI_PATTERN.match(image_path)
            if base64_match:
                img_ref.is_base64 = True
                img_ref.base64_data = base64_match.group(2)

                if embed_mode == "copy":
                    # Save base64 image to file
                    try:
                        import base64

                        ext = base64_match.group(1).lower()
                        if ext not in ["png", "jpg", "jpeg", "gif", "webp"]:
                            ext = "png"

                        img_data = base64.b64decode(img_ref.base64_data)
                        img_hash = hashlib.md5(img_data).hexdigest()[:16]
                        new_filename = f"base64_{img_hash}.{ext}"
                        new_path = self.images_dir / new_filename

                        new_path.write_bytes(img_data)
                        img_ref.new_path = f"images/{new_filename}"
                        img_ref.copied_count = 1

                        # Update content
                        new_img_tag = f"![{alt_text}]({img_ref.new_path})"
                        result.updated_content = result.updated_content.replace(
                            match.group(0), new_img_tag
                        )
                    except Exception as e:
                        img_ref.error = str(e)
                        result.error_count += 1

            # Check if it's external URL (http/https)
            elif image_path.startswith(("http://", "https://")):
                img_ref.is_external = True

                if embed_mode == "copy":
                    # Download external image
                    try:
                        import requests

                        response = requests.get(image_path, timeout=10)
                        if response.status_code == 200:
                            # Get extension from URL or content-type
                            ext = Path(image_path).suffix.lower()
                            if ext not in IMAGE_EXTENSIONS:
                                ext = ".jpg"

                            img_hash = hashlib.md5(response.content).hexdigest()[:16]
                            new_filename = f"external_{img_hash}{ext}"
                            new_path = self.images_dir / new_filename

                            new_path.write_bytes(response.content)
                            img_ref.new_path = f"images/{new_filename}"
                            img_ref.copied_count = 1

                            # Update content
                            new_img_tag = f"![{alt_text}]({img_ref.new_path})"
                            result.updated_content = result.updated_content.replace(
                                match.group(0), new_img_tag
                            )
                        else:
                            img_ref.error = f"HTTP {response.status_code}"
                            result.error_count += 1
                    except Exception as e:
                        img_ref.error = str(e)
                        result.error_count += 1

            # Local file
            else:
                # Resolve relative path
                if source_path.parent.exists():
                    local_path = source_path.parent / image_path
                    if local_path.exists():
                        try:
                            ext = local_path.suffix.lower()
                            if ext in IMAGE_EXTENSIONS:
                                img_data = local_path.read_bytes()
                                img_hash = hashlib.md5(img_data).hexdigest()[:16]
                                new_filename = f"{local_path.stem}_{img_hash}{ext}"
                                new_path = self.images_dir / new_filename

                                # Copy image
                                shutil.copy2(local_path, new_path)
                                img_ref.new_path = f"images/{new_filename}"
                                img_ref.copied_count = 1

                                # Update content
                                new_img_tag = f"![{alt_text}]({img_ref.new_path})"
                                result.updated_content = result.updated_content.replace(
                                    match.group(0), new_img_tag
                                )
                            else:
                                img_ref.error = f"Invalid extension: {ext}"
                                result.error_count += 1
                        except Exception as e:
                            img_ref.error = str(e)
                            result.error_count += 1
                    else:
                        img_ref.error = "File not found"
                        result.error_count += 1

            result.images.append(img_ref)
            if img_ref.new_path and not img_ref.error:
                result.image_count += 1
                if img_ref.copied_count > 0:
                    result.copied_count += img_ref.copied_count

        return result

    def _is_external_url(self, path: str) -> bool:
        """Check if path is an external URL."""
        parsed = urlparse(path)
        return parsed.scheme in ("http", "https", "ftp")

    def _resolve_relative_path(self, img_path: str, source_dir: Path) -> Optional[Path]:
        """Resolve a relative image path from source directory."""
        try:
            if img_path.startswith("/"):
                potential = Path(img_path)
            else:
                potential = (source_dir / img_path).resolve()

            if potential.exists() and potential.suffix.lower() in IMAGE_EXTENSIONS:
                return potential
        except Exception:
            pass
        return None

    def _copy_image(self, source_path: Path) -> Optional[str]:
        """Copy image to images directory with a unique name.

        Returns the relative path to use in Markdown.
        """
        try:
            ext = source_path.suffix.lower()
            content_hash = hashlib.md5(source_path.read_bytes()).hexdigest()[:12]
            new_name = f"{source_path.stem}_{content_hash}{ext}"
            dest_path = self.images_dir / new_name

            if not dest_path.exists():
                shutil.copy2(source_path, dest_path)
                print(
                    f"[ImageHandler] Copied: {source_path.name} -> images/{new_name}",
                    file=sys.stderr,
                )

            return f"images/{new_name}"
        except Exception as e:
            print(f"[ImageHandler] Error copying image: {e}", file=sys.stderr)
            return None

    def _image_to_base64(self, image_path: Path) -> Optional[str]:
        """Convert image file to base64 data URI."""
        try:
            ext = image_path.suffix.lower()
            mime_type = IMAGE_MIME_TYPES.get(ext, "image/png")
            data = base64.b64encode(image_path.read_bytes()).decode("utf-8")
            return f"data:{mime_type};base64,{data}"
        except Exception as e:
            print(f"[ImageHandler] Error converting to base64: {e}", file=sys.stderr)
            return None

    def _save_base64_image(self, base64_data: str, format_hint: str) -> Optional[str]:
        """Save base64 image data to a file."""
        try:
            ext = f".{format_hint.lower()}"
            if ext not in IMAGE_EXTENSIONS:
                ext = ".png"

            content_hash = hashlib.md5(base64_data.encode()).hexdigest()[:12]
            new_name = f"base64_{content_hash}{ext}"
            dest_path = self.images_dir / new_name

            if not dest_path.exists():
                image_data = base64.b64decode(base64_data)
                dest_path.write_bytes(image_data)
                print(
                    f"[ImageHandler] Saved base64 image -> images/{new_name}",
                    file=sys.stderr,
                )

            return f"images/{new_name}"
        except Exception as e:
            print(f"[ImageHandler] Error saving base64 image: {e}", file=sys.stderr)
            return None

    def _fetch_image_base64(self, url: str) -> Optional[str]:
        """Fetch external image and convert to base64."""
        try:
            import requests
            from gangdan.core.config import get_proxies

            response = requests.get(url, timeout=10, proxies=get_proxies())
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "")
            if not content_type.startswith("image/"):
                return None

            data = base64.b64encode(response.content).decode("utf-8")
            return f"data:{content_type};base64,{data}"
        except Exception as e:
            print(f"[ImageHandler] Error fetching image: {e}", file=sys.stderr)
            return None

    def get_image_path(self, image_name: str) -> Optional[Path]:
        """Get the full path to an image in the images directory."""
        image_path = self.images_dir / image_name
        if image_path.exists() and image_path.is_file():
            if image_path.suffix.lower() in IMAGE_EXTENSIONS:
                return image_path
        return None

    def get_image_data(self, image_name: str) -> Optional[Tuple[bytes, str]]:
        """Get image data and MIME type.

        Returns
        -------
        tuple (bytes, str) or None
            Image bytes and MIME type, or None if not found.
        """
        image_path = self.get_image_path(image_name)
        if image_path:
            mime_type = IMAGE_MIME_TYPES.get(
                image_path.suffix.lower(), "application/octet-stream"
            )
            return image_path.read_bytes(), mime_type
        return None

    def list_images(self, source_file: str | None = None) -> List[Dict]:
        """List all images in the images directory.

        Parameters
        ----------
        source_file : str, optional
            Filter by source file name.
        """
        images = []
        if self.images_dir.exists():
            # Load image manifest if available
            manifest_path = self.kb_dir / ".image_manifest.json"
            manifests = {}
            if manifest_path.exists():
                import json

                manifests = json.loads(manifest_path.read_text())

            for f in self.images_dir.iterdir():
                if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS:
                    stat = f.stat()
                    image_info = {
                        "name": f.name,
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                        "path": f"images/{f.name}",
                        "mime_type": IMAGE_MIME_TYPES.get(
                            f.suffix.lower(), "application/octet-stream"
                        ),
                    }

                    # Find source file from manifests
                    if manifests:
                        for src_file, manifest in manifests.items():
                            for img in manifest.get("images", []):
                                if img.get("new_path") == f"images/{f.name}":
                                    image_info["source_file"] = src_file
                                    image_info["alt_text"] = img.get("alt_text", "")
                                    image_info["original_path"] = img.get(
                                        "original_path", ""
                                    )
                                    break
                            if "source_file" in image_info:
                                break

                    # Filter by source file if specified
                    if source_file:
                        if image_info.get("source_file") == source_file:
                            images.append(image_info)
                    else:
                        images.append(image_info)

        return images

    def save_image_manifest(self, source_file: str, images: List[ImageRef]):
        """Save image manifest for a source file.

        Parameters
        ----------
        source_file : str
            Source markdown file name.
        images : List[ImageRef]
            List of processed image references.
        """
        import json

        manifest_path = self.kb_dir / ".image_manifest.json"
        manifests = {}
        if manifest_path.exists():
            manifests = json.loads(manifest_path.read_text())

        # Only save images that were successfully processed
        processed_images = [img for img in images if img.new_path and not img.error]
        if processed_images:
            manifests[source_file] = {
                "source_file": source_file,
                "images": [
                    {
                        "original_path": img.original_path,
                        "new_path": img.new_path,
                        "alt_text": img.alt_text,
                        "is_external": img.is_external,
                        "is_base64": img.is_base64,
                    }
                    for img in processed_images
                ],
                "image_count": len(processed_images),
            }
        elif source_file in manifests:
            # Remove entry if no images
            del manifests[source_file]

        if manifests:
            manifest_path.write_text(json.dumps(manifests, indent=2))
        elif manifest_path.exists():
            manifest_path.unlink()

    def cleanup_unused_images(self, used_images: set) -> int:
        """Remove images not in the used_images set.

        Returns the count of removed images.
        """
        removed = 0
        if self.images_dir.exists():
            for f in self.images_dir.iterdir():
                if f.is_file() and f.name not in used_images:
                    try:
                        f.unlink()
                        removed += 1
                        print(
                            f"[ImageHandler] Removed unused: {f.name}", file=sys.stderr
                        )
                    except Exception as e:
                        print(
                            f"[ImageHandler] Error removing {f.name}: {e}",
                            file=sys.stderr,
                        )
        return removed


def process_kb_images(
    kb_dir: Path,
    source_path: Path,
    content: str,
    embed_mode: str = "copy",
) -> ImageProcessResult:
    """Convenience function to process images for a KB document.

    Parameters
    ----------
    kb_dir : Path
        Knowledge base directory (will contain images/ subdirectory).
    source_path : Path
        Source document path for resolving relative paths.
    content : str
        Markdown content to process.
    embed_mode : str
        "copy", "base64", or "reference".

    Returns
    -------
    ImageProcessResult
        Processed result with updated content.
    """
    handler = ImageHandler(kb_dir)
    return handler.process_document(content, source_path, embed_mode)
