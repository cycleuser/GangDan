"""Knowledge base versioning and document management.

Reference: DeepTutor's KB versioning design.

Features:
- Versioned index storage with flat `version-N` directories
- Embedding signature computation for model identification
- Hash-based document deduplication
- Progress tracking with atomic writes
- Embedding mismatch detection
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

_MAX_KB_NAME_LENGTH = 120
_FORBIDDEN_CHARS = set('<>:"/\\|?*#%')
_CONTROL_CHAR_RE = __import__('re').compile(r'[\x00-\x1f\x7f]')


# =============================================================================
# KB Name Validation
# =============================================================================

def validate_kb_name(name: str) -> str:
    """Validate and sanitize a knowledge base name.

    Parameters
    ----------
    name : str
        Raw KB name.

    Returns
    -------
    str
        Validated and sanitized name.

    Raises
    ------
    ValueError
        If name is invalid.
    """
    normalized = unicodedata.normalize("NFC", str(name or "")).strip()

    if not normalized:
        raise ValueError("KB name cannot be empty")

    if len(normalized) > _MAX_KB_NAME_LENGTH:
        raise ValueError(f"KB name too long (max {_MAX_KB_NAME_LENGTH} chars)")

    if normalized in (".", ".."):
        raise ValueError("KB name cannot be '.' or '..'")

    if _FORBIDDEN_CHARS & set(normalized):
        raise ValueError(f"KB name contains forbidden characters: {_FORBIDDEN_CHARS & set(normalized)}")

    if _CONTROL_CHAR_RE.search(normalized):
        raise ValueError("KB name contains control characters")

    return normalized


# =============================================================================
# Embedding Signature
# =============================================================================

@dataclass
class EmbeddingSignature:
    """Stable identity for an embedding configuration.

    Creates a 16-char SHA256 hex hash from embedding parameters.
    """

    model: str
    dimension: int
    base_url: str = ""
    provider: str = ""

    def compute_hash(self) -> str:
        """Compute a stable 16-char hash for this signature."""
        content = f"{self.provider}:{self.model}:{self.dimension}:{self.base_url}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "model": self.model,
            "dimension": self.dimension,
            "base_url": self.base_url,
            "provider": self.provider,
            "hash": self.compute_hash(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EmbeddingSignature":
        """Create from dictionary."""
        return cls(
            model=data.get("model", ""),
            dimension=data.get("dimension", 0),
            base_url=data.get("base_url", ""),
            provider=data.get("provider", ""),
        )


# =============================================================================
# Version Management
# =============================================================================

@dataclass
class VersionMeta:
    """Metadata for a KB index version."""

    version: str
    signature: str
    model: str
    dimension: int
    created_at: str
    layout: str = "flat"
    doc_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "version": self.version,
            "signature": self.signature,
            "model": self.model,
            "dimension": self.dimension,
            "created_at": self.created_at,
            "layout": self.layout,
            "doc_count": self.doc_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VersionMeta":
        """Create from dictionary."""
        return cls(
            version=data.get("version", ""),
            signature=data.get("signature", ""),
            model=data.get("model", ""),
            dimension=data.get("dimension", 0),
            created_at=data.get("created_at", ""),
            layout=data.get("layout", "flat"),
            doc_count=data.get("doc_count", 0),
        )


def list_kb_versions(kb_dir: Path) -> List[VersionMeta]:
    """List all index versions for a KB.

    Discovers flat `version-N` directories and legacy nested layouts.

    Parameters
    ----------
    kb_dir : Path
        KB root directory.

    Returns
    -------
    List[VersionMeta]
        List of version metadata, sorted newest-first.
    """
    versions = []

    if not kb_dir.exists():
        return versions

    # Discover flat version-N directories
    for entry in sorted(kb_dir.iterdir()):
        if entry.is_dir() and entry.name.startswith("version-"):
            meta_path = entry / "meta.json"
            if meta_path.exists():
                try:
                    data = json.loads(meta_path.read_text(encoding="utf-8"))
                    versions.append(VersionMeta.from_dict(data))
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning("[KBVersioning] Failed to read %s: %s", meta_path, e)

    # Discover legacy nested versions
    legacy_dir = kb_dir / "index_versions"
    if legacy_dir.exists():
        for entry in legacy_dir.iterdir():
            if entry.is_dir():
                meta_path = entry / "meta.json"
                if meta_path.exists():
                    try:
                        data = json.loads(meta_path.read_text(encoding="utf-8"))
                        versions.append(VersionMeta.from_dict(data))
                    except (json.JSONDecodeError, OSError):
                        pass

    # Sort by version number (newest first)
    versions.sort(key=lambda v: v.version, reverse=True)
    return versions


def find_matching_version(kb_dir: Path, signature: str) -> Optional[VersionMeta]:
    """Find a version matching the given embedding signature.

    Parameters
    ----------
    kb_dir : Path
        KB root directory.
    signature : str
        Embedding signature hash.

    Returns
    -------
    VersionMeta or None
        Matching version, or None.
    """
    versions = list_kb_versions(kb_dir)
    for v in versions:
        if v.signature == signature:
            return v
    return None


def create_new_version(kb_dir: Path, signature: EmbeddingSignature) -> Path:
    """Create a new version directory.

    Parameters
    ----------
    kb_dir : Path
        KB root directory.
    signature : EmbeddingSignature
        Embedding configuration.

    Returns
    -------
    Path
        New version directory path.
    """
    versions = list_kb_versions(kb_dir)
    next_num = len(versions) + 1
    version_name = f"version-{next_num}"
    version_dir = kb_dir / version_name
    version_dir.mkdir(parents=True, exist_ok=True)

    meta = VersionMeta(
        version=version_name,
        signature=signature.compute_hash(),
        model=signature.model,
        dimension=signature.dimension,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        layout="flat",
    )

    meta_path = version_dir / "meta.json"
    atomic_write_json(meta_path, meta.to_dict())

    logger.info("[KBVersioning] Created %s with signature %s", version_name, meta.signature)
    return version_dir


def write_version_meta(version_dir: Path, meta: VersionMeta) -> None:
    """Write version metadata to meta.json.

    Parameters
    ----------
    version_dir : Path
        Version directory.
    meta : VersionMeta
        Version metadata.
    """
    meta_path = version_dir / "meta.json"
    atomic_write_json(meta_path, meta.to_dict())


def resolve_storage_dir(kb_dir: Path, signature: str) -> Optional[Path]:
    """Resolve the correct version directory for reading.

    Parameters
    ----------
    kb_dir : Path
        KB root directory.
    signature : str
        Embedding signature hash.

    Returns
    -------
    Path or None
        Version directory, or None if no match.
    """
    version = find_matching_version(kb_dir, signature)
    if version:
        return kb_dir / version.version

    # Fall back to latest version
    versions = list_kb_versions(kb_dir)
    if versions:
        return kb_dir / versions[0].version

    return None


# =============================================================================
# File Hash Deduplication
# =============================================================================

def compute_file_hash(filepath: Path, block_size: int = 65536) -> str:
    """Compute SHA256 hash of a file.

    Parameters
    ----------
    filepath : Path
        File path.
    block_size : int
        Read block size.

    Returns
    -------
    str
        Hex digest.
    """
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            block = f.read(block_size)
            if not block:
                break
            sha256.update(block)
    return sha256.hexdigest()


def load_file_hashes(metadata_path: Path) -> Dict[str, str]:
    """Load file hashes from metadata.json.

    Parameters
    ----------
    metadata_path : Path
        Path to metadata.json.

    Returns
    -------
    Dict[str, str]
        Filename -> SHA256 hash mapping.
    """
    if not metadata_path.exists():
        return {}

    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        return data.get("file_hashes", {})
    except (json.JSONDecodeError, OSError):
        return {}


def save_file_hash(metadata_path: Path, filename: str, file_hash: str) -> None:
    """Save a file hash to metadata.json.

    Parameters
    ----------
    metadata_path : Path
        Path to metadata.json.
    filename : str
        Filename.
    file_hash : str
        SHA256 hash.
    """
    hashes = load_file_hashes(metadata_path)
    hashes[filename] = file_hash

    data = {"file_hashes": hashes}
    atomic_write_json(metadata_path, data)


def is_duplicate(metadata_path: Path, filepath: Path) -> bool:
    """Check if a file is a duplicate based on content hash.

    Parameters
    ----------
    metadata_path : Path
        Path to metadata.json.
    filepath : Path
        File to check.

    Returns
    -------
    bool
        True if duplicate.
    """
    file_hash = compute_file_hash(filepath)
    hashes = load_file_hashes(metadata_path)
    return file_hash in hashes.values()


# =============================================================================
# Atomic File Operations
# =============================================================================

def atomic_write_json(filepath: Path, data: Any) -> None:
    """Write JSON atomically using temp file + rename.

    Parameters
    ----------
    filepath : Path
        Target file path.
    data : Any
        Data to serialize.
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=filepath.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, 'w', encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, str(filepath))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def atomic_write_text(filepath: Path, text: str) -> None:
    """Write text atomically using temp file + rename.

    Parameters
    ----------
    filepath : Path
        Target file path.
    text : str
        Text to write.
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=filepath.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, 'w', encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp_path, str(filepath))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# =============================================================================
# Progress Tracking
# =============================================================================

@dataclass
class ProgressState:
    """Progress tracking state."""

    kb_name: str = ""
    task_id: str = ""
    stage: str = "initializing"
    message: str = ""
    current: int = 0
    total: int = 0
    file_name: str = ""
    timestamp: str = ""
    error: Optional[str] = None

    @property
    def progress_percent(self) -> int:
        """Compute progress percentage."""
        if self.total == 0:
            return 0
        return int(self.current / self.total * 100)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "kb_name": self.kb_name,
            "task_id": self.task_id,
            "stage": self.stage,
            "message": self.message,
            "current": self.current,
            "total": self.total,
            "file_name": self.file_name,
            "progress_percent": self.progress_percent,
            "timestamp": self.timestamp or time.strftime("%Y-%m-%dT%H:%M:%S"),
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProgressState":
        """Create from dictionary."""
        return cls(
            kb_name=data.get("kb_name", ""),
            task_id=data.get("task_id", ""),
            stage=data.get("stage", "initializing"),
            message=data.get("message", ""),
            current=data.get("current", 0),
            total=data.get("total", 0),
            file_name=data.get("file_name", ""),
            timestamp=data.get("timestamp", ""),
            error=data.get("error"),
        )


class ProgressTracker:
    """Track progress for long-running KB operations.

    Uses atomic writes for crash-safe persistence.
    """

    def __init__(self, kb_name: str, progress_path: Optional[Path] = None) -> None:
        self.kb_name = kb_name
        self.progress_path = progress_path or Path(f".{kb_name}.progress.json")
        self._callbacks: List = []
        self._state = ProgressState(kb_name=kb_name)

    def set_callback(self, callback) -> None:
        """Add a progress callback."""
        self._callbacks.append(callback)

    def remove_callback(self, callback) -> None:
        """Remove a progress callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def update(
        self,
        stage: str = "",
        message: str = "",
        current: int = -1,
        total: int = -1,
        file_name: str = "",
        error: Optional[str] = None,
    ) -> None:
        """Update progress state.

        Parameters
        ----------
        stage : str
            Current stage name.
        message : str
            Status message.
        current : int
            Current progress count (-1 to keep existing).
        total : int
            Total count (-1 to keep existing).
        file_name : str
            Current file being processed.
        error : str or None
            Error message if any.
        """
        if stage:
            self._state.stage = stage
        if message:
            self._state.message = message
        if current >= 0:
            self._state.current = current
        if total >= 0:
            self._state.total = total
        if file_name:
            self._state.file_name = file_name
        if error is not None:
            self._state.error = error

        self._state.timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._save()
        self._notify()

    def _save(self) -> None:
        """Save progress to file atomically."""
        try:
            atomic_write_json(self.progress_path, self._state.to_dict())
        except OSError as e:
            logger.warning("[ProgressTracker] Failed to save progress: %s", e)

    def _notify(self) -> None:
        """Notify all callbacks."""
        for callback in self._callbacks:
            try:
                callback(self._state.to_dict())
            except Exception as e:
                logger.warning("[ProgressTracker] Callback error: %s", e)

    def get_state(self) -> ProgressState:
        """Get current progress state."""
        return self._state

    def load(self) -> Optional[ProgressState]:
        """Load progress from file."""
        if not self.progress_path.exists():
            return None

        try:
            data = json.loads(self.progress_path.read_text(encoding="utf-8"))
            self._state = ProgressState.from_dict(data)
            return self._state
        except (json.JSONDecodeError, OSError):
            return None

    def clear(self) -> None:
        """Clear progress state."""
        if self.progress_path.exists():
            try:
                self.progress_path.unlink()
            except OSError:
                pass
        self._state = ProgressState(kb_name=self.kb_name)


# =============================================================================
# Embedding Mismatch Detection
# =============================================================================

def check_embedding_mismatch(
    kb_dir: Path,
    current_signature: EmbeddingSignature,
    stored_model: str = "",
    stored_dim: int = 0,
) -> Dict[str, Any]:
    """Check if embedding configuration has changed.

    Parameters
    ----------
    kb_dir : Path
        KB root directory.
    current_signature : EmbeddingSignature
        Current embedding configuration.
    stored_model : str
        Previously stored model name.
    stored_dim : int
        Previously stored dimension.

    Returns
    -------
    Dict[str, Any]
        Mismatch detection result with:
        - needs_reindex: bool
        - embedding_mismatch: bool
        - matching_version: Optional[VersionMeta]
    """
    current_hash = current_signature.compute_hash()
    matching_version = find_matching_version(kb_dir, current_hash)

    if matching_version:
        return {
            "needs_reindex": False,
            "embedding_mismatch": False,
            "matching_version": matching_version,
        }

    mismatch = (
        (stored_model and stored_model != current_signature.model) or
        (stored_dim and stored_dim != current_signature.dimension)
    )

    return {
        "needs_reindex": mismatch,
        "embedding_mismatch": mismatch,
        "matching_version": None,
    }
