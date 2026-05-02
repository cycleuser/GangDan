"""Batch preprint processing pipeline.

Handles batch conversion of multiple preprints to Markdown,
export as zip archive, and custom knowledge base creation.

Features:
- Batch multi-select conversion with progress tracking
- Export as downloadable zip (Markdown + metadata JSON)
- Custom knowledge base creation with user-defined name, description, tags
- Reusable KB templates
"""

from __future__ import annotations

import json
import logging
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from gangdan.core.config import DATA_DIR

logger = logging.getLogger(__name__)

PREPRINT_BATCH_STATE_FILE = DATA_DIR / "preprint_batch_state.json"
PREPRINT_KB_MANIFEST_FILE = DATA_DIR / "preprint_kb_manifest.json"


@dataclass
class BatchJob:
    """A batch conversion job.

    Attributes
    ----------
    job_id : str
        Unique job identifier.
    preprint_ids : List[str]
        List of preprint IDs to process.
    status : str
        Job status: 'pending', 'running', 'completed', 'failed'.
    total : int
        Total number of preprints.
    completed : int
        Number completed so far.
    failed_count : int
        Number of failures.
    results : List[Dict]
        Per-preprint results.
    created_at : str
        ISO timestamp.
    finished_at : str
        ISO timestamp when done.
    error : str
        Error message if failed.
    """

    job_id: str = ""
    preprint_ids: List[str] = field(default_factory=list)
    status: str = "pending"
    total: int = 0
    completed: int = 0
    failed_count: int = 0
    results: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    finished_at: str = ""
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "job_id": self.job_id,
            "preprint_ids": self.preprint_ids,
            "status": self.status,
            "total": self.total,
            "completed": self.completed,
            "failed_count": self.failed_count,
            "results": self.results,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "error": self.error,
        }


@dataclass
class CustomKB:
    """A custom knowledge base created from preprints.

    Attributes
    ----------
    kb_id : str
        Unique KB identifier.
    name : str
        Display name.
    description : str
        KB description.
    tags : List[str]
        User-assigned tags.
    preprint_ids : List[str]
        Preprints included.
    markdown_dir : str
        Directory containing Markdown files.
    created_at : str
        ISO timestamp.
    entry_count : int
        Number of entries indexed.
    """

    kb_id: str = ""
    name: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    preprint_ids: List[str] = field(default_factory=list)
    markdown_dir: str = ""
    created_at: str = ""
    entry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "kb_id": self.kb_id,
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
            "preprint_ids": self.preprint_ids,
            "markdown_dir": self.markdown_dir,
            "created_at": self.created_at,
            "entry_count": self.entry_count,
        }


class PreprintBatchProcessor:
    """Process multiple preprints in batch.

    Parameters
    ----------
    state_file : Path
        Path to persist batch job state.
    """

    def __init__(self, state_file: Optional[Path] = None) -> None:
        self.state_file = state_file or PREPRINT_BATCH_STATE_FILE
        self.jobs: Dict[str, BatchJob] = {}
        self.custom_kbs: Dict[str, CustomKB] = {}
        self._on_progress: Optional[Callable[[str, int, int], None]] = None
        self._load_state()

    def set_progress_callback(self, callback: Callable[[str, int, int], None]) -> None:
        """Set progress callback."""
        self._on_progress = callback

    def create_batch_job(
        self,
        preprint_ids: List[str],
        preprint_data: Dict[str, Any],
    ) -> str:
        """Create a new batch conversion job.

        Parameters
        ----------
        preprint_ids : List[str]
            List of preprint IDs to convert.
        preprint_data : Dict[str, Any]
            Mapping of preprint_id -> {url, content_type, metadata}.

        Returns
        -------
        str
            Job ID.
        """
        import uuid

        job_id = str(uuid.uuid4())[:8]
        job = BatchJob(
            job_id=job_id,
            preprint_ids=preprint_ids,
            total=len(preprint_ids),
            created_at=datetime.now().isoformat(),
        )
        self.jobs[job_id] = job
        self._save_state()
        return job_id

    def run_batch_job(
        self,
        job_id: str,
        preprint_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a batch conversion job.

        Parameters
        ----------
        job_id : str
            Job ID to run.
        preprint_data : Dict[str, Any]
            Mapping of preprint_id -> {url, content_type, metadata}.

        Returns
        -------
        Dict[str, Any]
            Job summary with results.
        """
        job = self.jobs.get(job_id)
        if not job:
            return {"error": "Job not found"}

        job.status = "running"
        output_dir = Path(tempfile.mkdtemp(prefix="gangdan_batch_"))

        for i, pid in enumerate(job.preprint_ids):
            if pid not in preprint_data:
                job.results.append({
                    "preprint_id": pid,
                    "status": "failed",
                    "error": "No data provided",
                })
                job.failed_count += 1
                continue

            data = preprint_data[pid]
            try:
                result = self._convert_single(pid, data, output_dir)
                job.results.append(result)
                if result.get("success"):
                    job.completed += 1
                else:
                    job.failed_count += 1
            except Exception as e:
                job.results.append({
                    "preprint_id": pid,
                    "status": "failed",
                    "error": str(e),
                })
                job.failed_count += 1

            self._report_progress(f"Converting {i + 1}/{job.total}: {pid}", i + 1, job.total)

        job.status = "completed"
        job.finished_at = datetime.now().isoformat()
        self._save_state()

        return {
            "job_id": job_id,
            "total": job.total,
            "completed": job.completed,
            "failed": job.failed_count,
            "output_dir": str(output_dir),
            "results": job.results,
        }

    def _convert_single(
        self,
        preprint_id: str,
        data: Dict[str, Any],
        output_dir: Path,
    ) -> Dict[str, Any]:
        """Convert a single preprint.

        Parameters
        ----------
        preprint_id : str
            Preprint identifier.
        data : Dict[str, Any]
            {url, content_type, metadata}.
        output_dir : Path
            Output directory.

        Returns
        -------
        Dict[str, Any]
            Conversion result.
        """
        from gangdan.core.preprint_converter import PreprintConverter

        url = data.get("url", "")
        content_type = data.get("content_type", "html")

        if not url:
            return {"preprint_id": preprint_id, "success": False, "error": "No URL"}

        converter = PreprintConverter(fallback_to_pdf=True)
        result = converter.convert_from_url(
            url, content_type=content_type, output_dir=output_dir, preprint_id=preprint_id
        )

        if result.success:
            md_path = Path(result.markdown_path)
            md_content = ""
            if md_path.exists():
                md_content = md_path.read_text(encoding="utf-8")

            return {
                "preprint_id": preprint_id,
                "success": True,
                "markdown_path": result.markdown_path,
                "markdown_content": md_content,
                "engine": result.engine,
            }
        else:
            return {
                "preprint_id": preprint_id,
                "success": False,
                "error": result.error,
            }

    def export_as_zip(self, job_id: str, output_path: Optional[Path] = None) -> Optional[str]:
        """Export batch results as a zip file.

        Parameters
        ----------
        job_id : str
            Completed job ID.
        output_path : Path or None
            Output zip path. If None, creates in temp dir.

        Returns
        -------
        str or None
            Path to zip file, or None if failed.
        """
        job = self.jobs.get(job_id)
        if not job:
            return None

        if output_path is None:
            output_path = Path(tempfile.mkdtemp()) / f"preprint_batch_{job_id}.zip"

        success_results = [r for r in job.results if r.get("success")]
        if not success_results:
            return None

        try:
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                metadata = []
                for result in success_results:
                    md_path = Path(result["markdown_path"])
                    if md_path.exists():
                        zf.write(md_path, f"markdown/{md_path.name}")

                    meta = {
                        "preprint_id": result["preprint_id"],
                        "markdown_file": f"markdown/{md_path.name}",
                        "engine": result.get("engine", ""),
                        "exported_at": datetime.now().isoformat(),
                    }
                    metadata.append(meta)

                zf.writestr("metadata.json", json.dumps(metadata, indent=2, ensure_ascii=False))
                zf.writestr("README.md", self._generate_readme(job, metadata))

            return str(output_path)
        except Exception as e:
            logger.error("[PreprintBatchProcessor] Export failed: %s", e)
            return None

    def _generate_readme(self, job: BatchJob, metadata: List[Dict]) -> str:
        """Generate a README for the exported zip.

        Parameters
        ----------
        job : BatchJob
            Batch job info.
        metadata : List[Dict]
            Exported file metadata.

        Returns
        -------
        str
            README markdown content.
        """
        lines = [
            "# Preprint Batch Export",
            "",
            f"**Exported:** {job.finished_at or datetime.now().isoformat()}",
            f"**Total preprints:** {job.completed}",
            f"**Failed:** {job.failed_count}",
            "",
            "## Contents",
            "",
        ]
        for m in metadata:
            lines.append(f"- `{m['markdown_file']}` - {m['preprint_id']}")
        lines.append("")
        lines.append("Generated by GangDan Preprint Intelligence")
        return "\n".join(lines)

    def create_custom_kb(
        self,
        name: str,
        description: str,
        preprint_ids: List[str],
        markdown_data: Dict[str, str],
        tags: Optional[List[str]] = None,
    ) -> CustomKB:
        """Create a custom knowledge base from converted preprints.

        Parameters
        ----------
        name : str
            KB display name.
        description : str
            KB description.
        preprint_ids : List[str]
            Preprint IDs to include.
        markdown_data : Dict[str, str]
            Mapping of preprint_id -> markdown content.
        tags : List[str] or None
            User tags.

        Returns
        -------
        CustomKB
            The created knowledge base.
        """
        import uuid

        kb_id = str(uuid.uuid4())[:8]
        kb_dir = DATA_DIR / "preprint_kbs" / kb_id
        kb_dir.mkdir(parents=True, exist_ok=True)

        entry_count = 0
        for pid, md_content in markdown_data.items():
            if md_content:
                md_path = kb_dir / f"{pid}.md"
                md_path.write_text(md_content, encoding="utf-8")
                entry_count += 1

        kb = CustomKB(
            kb_id=kb_id,
            name=name,
            description=description,
            tags=tags or [],
            preprint_ids=preprint_ids,
            markdown_dir=str(kb_dir),
            created_at=datetime.now().isoformat(),
            entry_count=entry_count,
        )
        self.custom_kbs[kb_id] = kb
        self._save_manifest()
        return kb

    def get_custom_kbs(self) -> List[Dict[str, Any]]:
        """List all custom knowledge bases.

        Returns
        -------
        List[Dict]
            Custom KB info.
        """
        return [kb.to_dict() for kb in self.custom_kbs.values()]

    def get_custom_kb(self, kb_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific custom KB.

        Parameters
        ----------
        kb_id : str
            KB identifier.

        Returns
        -------
        Dict or None
            KB info, or None if not found.
        """
        kb = self.custom_kbs.get(kb_id)
        return kb.to_dict() if kb else None

    def delete_custom_kb(self, kb_id: str) -> bool:
        """Delete a custom knowledge base.

        Parameters
        ----------
        kb_id : str
            KB identifier.

        Returns
        -------
        bool
            True if deleted.
        """
        kb = self.custom_kbs.pop(kb_id, None)
        if kb:
            kb_dir = Path(kb.markdown_dir)
            if kb_dir.exists():
                import shutil
                shutil.rmtree(kb_dir, ignore_errors=True)
            self._save_manifest()
            return True
        return False

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job status.

        Parameters
        ----------
        job_id : str
            Job identifier.

        Returns
        -------
        Dict or None
            Job info.
        """
        job = self.jobs.get(job_id)
        return job.to_dict() if job else None

    def get_all_jobs(self) -> List[Dict[str, Any]]:
        """Get all jobs.

        Returns
        -------
        List[Dict]
            All job info.
        """
        return [j.to_dict() for j in self.jobs.values()]

    def _report_progress(self, message: str, current: int, total: int) -> None:
        """Report progress."""
        if self._on_progress:
            self._on_progress(message, current, total)
        logger.info("[PreprintBatchProcessor] %s (%d/%d)", message, current, total)

    def _load_state(self) -> None:
        """Load state from disk."""
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                jobs_data = data.get("jobs", {})
                self.jobs = {
                    jid: BatchJob(**jdata) for jid, jdata in jobs_data.items()
                }
            except Exception as e:
                logger.error("[PreprintBatchProcessor] Load state failed: %s", e)

        if PREPRINT_KB_MANIFEST_FILE.exists():
            try:
                data = json.loads(PREPRINT_KB_MANIFEST_FILE.read_text(encoding="utf-8"))
                kbs_data = data.get("kbs", {})
                self.custom_kbs = {
                    kid: CustomKB(**kdata) for kid, kdata in kbs_data.items()
                }
            except Exception as e:
                logger.error("[PreprintBatchProcessor] Load manifest failed: %s", e)

    def _save_state(self) -> None:
        """Save state to disk."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "jobs": {jid: j.to_dict() for jid, j in self.jobs.items()},
            }
            self.state_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            logger.error("[PreprintBatchProcessor] Save state failed: %s", e)

    def _save_manifest(self) -> None:
        """Save KB manifest to disk."""
        try:
            PREPRINT_KB_MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "kbs": {kid: kb.to_dict() for kid, kb in self.custom_kbs.items()},
            }
            PREPRINT_KB_MANIFEST_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            logger.error("[PreprintBatchProcessor] Save manifest failed: %s", e)
