"""Tests for KB versioning module."""

import json
import pytest
from pathlib import Path

from gangdan.core.kb_versioning import (
    validate_kb_name,
    EmbeddingSignature,
    VersionMeta,
    list_kb_versions,
    find_matching_version,
    create_new_version,
    compute_file_hash,
    load_file_hashes,
    save_file_hash,
    is_duplicate,
    atomic_write_json,
    atomic_write_text,
    ProgressState,
    ProgressTracker,
    check_embedding_mismatch,
)


class TestValidateKBName:
    """Tests for KB name validation."""

    def test_valid_name(self):
        assert validate_kb_name("my-kb") == "my-kb"

    def test_unicode_name(self):
        assert validate_kb_name("知识库") == "知识库"

    def test_empty_name_raises(self):
        with pytest.raises(ValueError):
            validate_kb_name("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError):
            validate_kb_name("   ")

    def test_forbidden_chars_raises(self):
        with pytest.raises(ValueError):
            validate_kb_name("my/kb")

    def test_dot_dot_raises(self):
        with pytest.raises(ValueError):
            validate_kb_name("..")

    def test_too_long_raises(self):
        with pytest.raises(ValueError):
            validate_kb_name("a" * 121)

    def test_control_chars_raises(self):
        with pytest.raises(ValueError):
            validate_kb_name("my\x00kb")


class TestEmbeddingSignature:
    """Tests for embedding signature."""

    def test_compute_hash(self):
        sig = EmbeddingSignature(model="nomic-embed-text", dimension=768)
        h = sig.compute_hash()
        assert len(h) == 16
        assert h == EmbeddingSignature(model="nomic-embed-text", dimension=768).compute_hash()

    def test_different_models_different_hash(self):
        sig1 = EmbeddingSignature(model="model-a", dimension=768)
        sig2 = EmbeddingSignature(model="model-b", dimension=768)
        assert sig1.compute_hash() != sig2.compute_hash()

    def test_to_dict(self):
        sig = EmbeddingSignature(model="test", dimension=512, base_url="http://localhost")
        d = sig.to_dict()
        assert d["model"] == "test"
        assert d["dimension"] == 512
        assert d["base_url"] == "http://localhost"
        assert len(d["hash"]) == 16

    def test_from_dict(self):
        d = {"model": "test", "dimension": 512, "base_url": "", "provider": "ollama", "hash": "abc123"}
        sig = EmbeddingSignature.from_dict(d)
        assert sig.model == "test"
        assert sig.dimension == 512


class TestVersionMeta:
    """Tests for version metadata."""

    def test_to_dict(self):
        meta = VersionMeta(
            version="version-1",
            signature="abc123",
            model="test",
            dimension=768,
            created_at="2024-01-01",
        )
        d = meta.to_dict()
        assert d["version"] == "version-1"
        assert d["signature"] == "abc123"

    def test_from_dict(self):
        d = {"version": "version-2", "signature": "def456", "model": "test", "dimension": 512, "created_at": "2024-01-02"}
        meta = VersionMeta.from_dict(d)
        assert meta.version == "version-2"


class TestVersionManagement:
    """Tests for version management functions."""

    def test_list_versions_empty(self, tmp_path):
        versions = list_kb_versions(tmp_path)
        assert versions == []

    def test_create_and_list_version(self, tmp_path):
        sig = EmbeddingSignature(model="test", dimension=768)
        version_dir = create_new_version(tmp_path, sig)
        assert version_dir.exists()
        assert version_dir.name == "version-1"

        versions = list_kb_versions(tmp_path)
        assert len(versions) == 1
        assert versions[0].version == "version-1"

    def test_create_multiple_versions(self, tmp_path):
        sig = EmbeddingSignature(model="test", dimension=768)
        create_new_version(tmp_path, sig)
        create_new_version(tmp_path, sig)

        versions = list_kb_versions(tmp_path)
        assert len(versions) == 2
        assert versions[0].version == "version-2"
        assert versions[1].version == "version-1"

    def test_find_matching_version(self, tmp_path):
        sig = EmbeddingSignature(model="test", dimension=768)
        create_new_version(tmp_path, sig)

        matching = find_matching_version(tmp_path, sig.compute_hash())
        assert matching is not None
        assert matching.signature == sig.compute_hash()

    def test_find_non_matching_version(self, tmp_path):
        sig = EmbeddingSignature(model="test", dimension=768)
        create_new_version(tmp_path, sig)

        other_sig = EmbeddingSignature(model="other", dimension=512)
        matching = find_matching_version(tmp_path, other_sig.compute_hash())
        assert matching is None


class TestFileHashDedup:
    """Tests for file hash deduplication."""

    def test_compute_file_hash(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        h = compute_file_hash(f)
        assert len(h) == 64

    def test_same_content_same_hash(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("same content")
        f2.write_text("same content")
        assert compute_file_hash(f1) == compute_file_hash(f2)

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("content a")
        f2.write_text("content b")
        assert compute_file_hash(f1) != compute_file_hash(f2)

    def test_save_and_load_hashes(self, tmp_path):
        meta = tmp_path / "metadata.json"
        save_file_hash(meta, "test.txt", "abc123")
        hashes = load_file_hashes(meta)
        assert hashes["test.txt"] == "abc123"

    def test_is_duplicate(self, tmp_path):
        meta = tmp_path / "metadata.json"
        f = tmp_path / "test.txt"
        f.write_text("hello")

        h = compute_file_hash(f)
        save_file_hash(meta, "test.txt", h)

        assert is_duplicate(meta, f)

    def test_is_not_duplicate(self, tmp_path):
        meta = tmp_path / "metadata.json"
        f = tmp_path / "test.txt"
        f.write_text("hello")

        save_file_hash(meta, "other.txt", "different_hash")

        assert not is_duplicate(meta, f)


class TestAtomicWrites:
    """Tests for atomic file operations."""

    def test_atomic_write_json(self, tmp_path):
        f = tmp_path / "test.json"
        atomic_write_json(f, {"key": "value"})
        assert f.exists()
        data = json.loads(f.read_text())
        assert data["key"] == "value"

    def test_atomic_write_text(self, tmp_path):
        f = tmp_path / "test.txt"
        atomic_write_text(f, "hello world")
        assert f.exists()
        assert f.read_text() == "hello world"

    def test_atomic_write_creates_parent(self, tmp_path):
        f = tmp_path / "subdir" / "test.json"
        atomic_write_json(f, {"a": 1})
        assert f.exists()


class TestProgressTracker:
    """Tests for progress tracking."""

    def test_initial_state(self):
        tracker = ProgressTracker("test-kb")
        state = tracker.get_state()
        assert state.kb_name == "test-kb"
        assert state.stage == "initializing"
        assert state.progress_percent == 0

    def test_update_progress(self):
        tracker = ProgressTracker("test-kb")
        tracker.update(stage="processing", current=5, total=10)
        state = tracker.get_state()
        assert state.stage == "processing"
        assert state.current == 5
        assert state.total == 10
        assert state.progress_percent == 50

    def test_callback_notification(self):
        tracker = ProgressTracker("test-kb")
        notifications = []
        tracker.set_callback(lambda s: notifications.append(s))
        tracker.update(stage="test", current=1, total=10)
        assert len(notifications) == 1
        assert notifications[0]["stage"] == "test"

    def test_save_and_load(self, tmp_path):
        path = tmp_path / "progress.json"
        tracker = ProgressTracker("test-kb", path)
        tracker.update(stage="processing", current=3, total=10)

        tracker2 = ProgressTracker("test-kb", path)
        state = tracker2.load()
        assert state is not None
        assert state.stage == "processing"
        assert state.current == 3

    def test_clear(self, tmp_path):
        path = tmp_path / "progress.json"
        tracker = ProgressTracker("test-kb", path)
        tracker.update(stage="processing")
        assert path.exists()

        tracker.clear()
        assert not path.exists()


class TestEmbeddingMismatch:
    """Tests for embedding mismatch detection."""

    def test_no_mismatch_same_config(self, tmp_path):
        sig = EmbeddingSignature(model="test", dimension=768)
        create_new_version(tmp_path, sig)

        result = check_embedding_mismatch(tmp_path, sig)
        assert result["needs_reindex"] is False
        assert result["embedding_mismatch"] is False
        assert result["matching_version"] is not None

    def test_mismatch_different_model(self, tmp_path):
        sig1 = EmbeddingSignature(model="model-a", dimension=768)
        create_new_version(tmp_path, sig1)

        sig2 = EmbeddingSignature(model="model-b", dimension=768)
        result = check_embedding_mismatch(tmp_path, sig2, stored_model="model-a", stored_dim=768)
        assert result["needs_reindex"] is True
        assert result["embedding_mismatch"] is True

    def test_mismatch_different_dimension(self, tmp_path):
        sig1 = EmbeddingSignature(model="test", dimension=768)
        create_new_version(tmp_path, sig1)

        sig2 = EmbeddingSignature(model="test", dimension=512)
        result = check_embedding_mismatch(tmp_path, sig2, stored_model="test", stored_dim=768)
        assert result["needs_reindex"] is True
