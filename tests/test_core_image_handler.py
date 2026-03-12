"""Tests for image_handler module."""

import base64
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from gangdan.core.image_handler import (
    ImageHandler,
    ImageRef,
    ImageProcessResult,
    IMAGE_EXTENSIONS,
    IMAGE_MIME_TYPES,
    process_kb_images,
)


class TestImageRef:
    """Test ImageRef dataclass."""

    def test_image_ref_defaults(self):
        """Test ImageRef default values."""
        ref = ImageRef(
            original_text="![alt](path.png)",
            alt_text="alt",
            original_path="path.png",
        )
        assert ref.new_path is None
        assert ref.is_external is False
        assert ref.is_base64 is False
        assert ref.base64_data is None
        assert ref.error is None

    def test_image_ref_external(self):
        """Test ImageRef for external URLs."""
        ref = ImageRef(
            original_text="![alt](https://example.com/img.png)",
            alt_text="alt",
            original_path="https://example.com/img.png",
            is_external=True,
        )
        assert ref.is_external is True


class TestImageProcessResult:
    """Test ImageProcessResult dataclass."""

    def test_empty_result(self):
        """Test empty ImageProcessResult."""
        result = ImageProcessResult()
        assert result.images == []
        assert result.updated_content == ""
        assert result.image_count == 0
        assert result.copied_count == 0
        assert result.error_count == 0

    def test_get_image_metadata(self):
        """Test get_image_metadata method."""
        result = ImageProcessResult(
            images=[
                ImageRef(
                    original_text="![a](a.png)",
                    alt_text="a",
                    original_path="a.png",
                    new_path="images/a_abc123.png",
                ),
                ImageRef(
                    original_text="![b](b.png)",
                    alt_text="b",
                    original_path="b.png",
                    error="Not found",
                ),
            ]
        )
        metadata = result.get_image_metadata()
        assert len(metadata) == 1
        assert metadata[0]["original_path"] == "a.png"
        assert metadata[0]["new_path"] == "images/a_abc123.png"


class TestImageHandler:
    """Test ImageHandler class."""

    def test_init(self, tmp_path: Path):
        """Test ImageHandler initialization."""
        handler = ImageHandler(tmp_path)
        assert handler.kb_dir == tmp_path
        assert handler.images_dir == tmp_path / "images"
        assert handler.images_dir.exists()

    def test_is_external_url(self, tmp_path: Path):
        """Test _is_external_url method."""
        handler = ImageHandler(tmp_path)
        assert handler._is_external_url("https://example.com/img.png") is True
        assert handler._is_external_url("http://example.com/img.png") is True
        assert handler._is_external_url("ftp://example.com/img.png") is True
        assert handler._is_external_url("/local/path/img.png") is False
        assert handler._is_external_url("./relative/img.png") is False
        assert handler._is_external_url("images/img.png") is False

    def test_process_document_no_images(self, tmp_path: Path):
        """Test process_document with no images."""
        handler = ImageHandler(tmp_path)
        content = "# Test Document\n\nNo images here."
        result = handler.process_document(content)
        assert result.image_count == 0
        assert result.copied_count == 0
        assert result.updated_content == content

    def test_process_document_with_base64_image(self, tmp_path: Path):
        """Test process_document with base64 embedded image."""
        handler = ImageHandler(tmp_path)
        png_data = base64.b64encode(
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        ).decode()
        content = f"![test](data:image/png;base64,{png_data})"
        
        result = handler.process_document(content, embed_mode="copy")
        assert result.image_count == 1
        assert result.copied_count == 1
        assert "images/base64_" in result.updated_content

    def test_process_document_with_missing_image(self, tmp_path: Path):
        """Test process_document with missing image file."""
        handler = ImageHandler(tmp_path)
        content = "![missing](./nonexistent.png)"
        
        result = handler.process_document(content, embed_mode="copy")
        assert result.image_count == 1
        assert result.copied_count == 0
        assert result.error_count == 1

    def test_process_document_with_existing_image(
        self, tmp_path: Path, sample_image: Path
    ):
        """Test process_document with existing local image."""
        handler = ImageHandler(tmp_path)
        content = f"![sample]({sample_image.name})"
        
        result = handler.process_document(
            content, 
            source_path=sample_image,
            embed_mode="copy"
        )
        assert result.image_count == 1
        assert result.copied_count == 1
        assert "images/" in result.updated_content

    def test_list_images_empty(self, tmp_path: Path):
        """Test list_images with no images."""
        handler = ImageHandler(tmp_path)
        images = handler.list_images()
        assert images == []

    def test_list_images_with_images(self, tmp_path: Path, sample_image: Path):
        """Test list_images with copied images."""
        handler = ImageHandler(tmp_path)
        content = f"![sample]({sample_image.name})"
        handler.process_document(content, source_path=sample_image, embed_mode="copy")
        
        images = handler.list_images()
        assert len(images) == 1
        assert images[0]["name"].endswith(".png")

    def test_get_image_path(self, tmp_path: Path, sample_image: Path):
        """Test get_image_path method."""
        handler = ImageHandler(tmp_path)
        content = f"![sample]({sample_image.name})"
        result = handler.process_document(
            content, source_path=sample_image, embed_mode="copy"
        )
        
        image_name = result.images[0].new_path.replace("images/", "")
        path = handler.get_image_path(image_name)
        assert path is not None
        assert path.exists()

    def test_get_image_data(self, tmp_path: Path, sample_image: Path):
        """Test get_image_data method."""
        handler = ImageHandler(tmp_path)
        content = f"![sample]({sample_image.name})"
        result = handler.process_document(
            content, source_path=sample_image, embed_mode="copy"
        )
        
        image_name = result.images[0].new_path.replace("images/", "")
        data = handler.get_image_data(image_name)
        assert data is not None
        image_bytes, mime_type = data
        assert len(image_bytes) > 0
        assert mime_type == "image/png"

    def test_embed_mode_reference(self, tmp_path: Path, sample_image: Path):
        """Test embed_mode='reference' keeps original paths."""
        handler = ImageHandler(tmp_path)
        content = f"![sample]({sample_image.name})"
        
        result = handler.process_document(
            content, 
            source_path=sample_image, 
            embed_mode="reference"
        )
        assert result.image_count == 1
        assert result.copied_count == 0
        assert result.updated_content == content


class TestProcessKBImages:
    """Test the convenience function process_kb_images."""

    def test_process_kb_images(self, tmp_path: Path, sample_image: Path):
        """Test process_kb_images convenience function."""
        content = f"![sample]({sample_image.name})"
        result = process_kb_images(
            tmp_path, sample_image, content, embed_mode="copy"
        )
        assert result.image_count == 1
        assert result.copied_count == 1


class TestImageExtensions:
    """Test supported image extensions."""

    def test_supported_extensions(self):
        """Test that common extensions are supported."""
        assert '.png' in IMAGE_EXTENSIONS
        assert '.jpg' in IMAGE_EXTENSIONS
        assert '.jpeg' in IMAGE_EXTENSIONS
        assert '.gif' in IMAGE_EXTENSIONS
        assert '.webp' in IMAGE_EXTENSIONS
        assert '.svg' in IMAGE_EXTENSIONS

    def test_mime_types(self):
        """Test MIME type mapping."""
        assert IMAGE_MIME_TYPES['.png'] == 'image/png'
        assert IMAGE_MIME_TYPES['.jpg'] == 'image/jpeg'
        assert IMAGE_MIME_TYPES['.svg'] == 'image/svg+xml'


# Fixtures

@pytest.fixture
def sample_image(tmp_path: Path) -> Path:
    """Create a sample PNG image for testing."""
    import struct
    import zlib
    
    def create_minimal_png(width=1, height=1):
        def png_chunk(chunk_type, data):
            chunk_len = struct.pack('>I', len(data))
            chunk_crc = struct.pack('>I', zlib.crc32(chunk_type + data) & 0xffffffff)
            return chunk_len + chunk_type + data + chunk_crc
        
        signature = b'\x89PNG\r\n\x1a\n'
        ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
        raw_data = b''
        for y in range(height):
            raw_data += b'\x00' + b'\xff\xff\xff' * width
        idat = zlib.compress(raw_data)
        iend = b''
        
        return (
            signature +
            png_chunk(b'IHDR', ihdr) +
            png_chunk(b'IDAT', idat) +
            png_chunk(b'IEND', iend)
        )
    
    image_path = tmp_path / "test_image.png"
    image_path.write_bytes(create_minimal_png())
    return image_path