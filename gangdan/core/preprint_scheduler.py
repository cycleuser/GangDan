"""Preprint scheduler for background fetch and indexing.

Manages scheduled preprint fetching from arXiv, bioRxiv, and medRxiv.
Runs as a background thread with configurable intervals.

Features:
- Scheduled fetching at configurable intervals
- Keyword-based subscriptions for targeted fetching
- Progress tracking and status reporting
- Automatic conversion and indexing pipeline
- Persistent state (saved to JSON)
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from gangdan.core.config import DATA_DIR

logger = logging.getLogger(__name__)

PREPRINT_STATE_FILE = DATA_DIR / "preprint_state.json"


@dataclass
class Subscription:
    """A keyword-based preprint subscription.

    Attributes
    ----------
    name : str
        Subscription name (e.g., 'LLM Research').
    keywords : List[str]
        Keywords to search for.
    platforms : List[str]
        Platforms to search: 'arxiv', 'biorxiv', 'medrxiv'.
    categories : List[str]
        arXiv categories to filter by.
    max_results : int
        Maximum results per keyword per platform.
    enabled : bool
        Whether this subscription is active.
    last_fetched : str
        ISO timestamp of last successful fetch.
    total_fetched : int
        Total number of preprints fetched.
    """

    name: str = ""
    keywords: List[str] = field(default_factory=list)
    platforms: List[str] = field(default_factory=lambda: ["arxiv"])
    categories: List[str] = field(default_factory=list)
    max_results: int = 10
    enabled: bool = True
    last_fetched: str = ""
    total_fetched: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "keywords": self.keywords,
            "platforms": self.platforms,
            "categories": self.categories,
            "max_results": self.max_results,
            "enabled": self.enabled,
            "last_fetched": self.last_fetched,
            "total_fetched": self.total_fetched,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Subscription":
        """Create from dictionary."""
        return cls(
            name=data.get("name", ""),
            keywords=data.get("keywords", []),
            platforms=data.get("platforms", ["arxiv"]),
            categories=data.get("categories", []),
            max_results=data.get("max_results", 10),
            enabled=data.get("enabled", True),
            last_fetched=data.get("last_fetched", ""),
            total_fetched=data.get("total_fetched", 0),
        )


@dataclass
class SchedulerStatus:
    """Current status of the preprint scheduler.

    Attributes
    ----------
    running : bool
        Whether the scheduler is currently running.
    last_run : str
        ISO timestamp of last run.
    next_run : str
        ISO timestamp of next scheduled run.
    interval_hours : int
        Hours between scheduled runs.
    total_runs : int
        Total number of runs completed.
    total_preprints : int
        Total preprints fetched across all runs.
    current_job : str
        Description of current running job (empty if idle).
    error : str
        Last error message (empty if none).
    """

    running: bool = False
    last_run: str = ""
    next_run: str = ""
    interval_hours: int = 24
    total_runs: int = 0
    total_preprints: int = 0
    current_job: str = ""
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "running": self.running,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "interval_hours": self.interval_hours,
            "total_runs": self.total_runs,
            "total_preprints": self.total_preprints,
            "current_job": self.current_job,
            "error": self.error,
        }


@dataclass
class FetchJob:
    """A single fetch job record.

    Attributes
    ----------
    job_id : str
        Unique job identifier.
    subscription_name : str
        Name of the subscription that triggered this job.
    keyword : str
            Keyword that was searched.
    platform : str
        Platform searched.
    status : str
        Job status: 'pending', 'running', 'completed', 'failed'.
    started_at : str
        ISO timestamp when job started.
    finished_at : str
        ISO timestamp when job finished.
    preprints_found : int
        Number of preprints found.
    preprints_converted : int
        Number of preprints converted to Markdown.
    error : str
        Error message if job failed.
    """

    job_id: str = ""
    subscription_name: str = ""
    keyword: str = ""
    platform: str = ""
    status: str = "pending"
    started_at: str = ""
    finished_at: str = ""
    preprints_found: int = 0
    preprints_converted: int = 0
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "job_id": self.job_id,
            "subscription_name": self.subscription_name,
            "keyword": self.keyword,
            "platform": self.platform,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "preprints_found": self.preprints_found,
            "preprints_converted": self.preprints_converted,
            "error": self.error,
        }


class PreprintScheduler:
    """Background scheduler for preprint fetching and indexing.

    Manages scheduled fetching of preprints based on keyword subscriptions.
    Runs as a background thread with configurable intervals.

    Parameters
    ----------
    state_file : Path
        Path to persist scheduler state.
    """

    def __init__(self, state_file: Optional[Path] = None) -> None:
        self.state_file = state_file or PREPRINT_STATE_FILE
        self.subscriptions: List[Subscription] = []
        self.status = SchedulerStatus()
        self.jobs: List[FetchJob] = []
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._on_progress: Optional[Callable[[str, int, int], None]] = None
        self._fetch_cache: Dict[str, Any] = {}

        self._load_state()

    def set_progress_callback(self, callback: Callable[[str, int, int], None]) -> None:
        """Set a callback for progress updates.

        Parameters
        ----------
        callback : Callable
            Function(status_message, current, total) called on progress.
        """
        self._on_progress = callback

    def add_subscription(
        self,
        name: str,
        keywords: List[str],
        platforms: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        max_results: int = 10,
    ) -> Subscription:
        """Add a new keyword subscription.

        Parameters
        ----------
        name : str
            Subscription name.
        keywords : List[str]
            Keywords to search for.
        platforms : List[str] or None
            Platforms to search. Defaults to ['arxiv'].
        categories : List[str] or None
            arXiv categories to filter by.
        max_results : int
            Maximum results per keyword.

        Returns
        -------
        Subscription
            The created subscription.
        """
        sub = Subscription(
            name=name,
            keywords=keywords,
            platforms=platforms or ["arxiv"],
            categories=categories or [],
            max_results=max_results,
        )
        self.subscriptions.append(sub)
        self._save_state()
        return sub

    def remove_subscription(self, name: str) -> bool:
        """Remove a subscription by name.

        Parameters
        ----------
        name : str
            Subscription name to remove.

        Returns
        -------
        bool
            True if removed, False if not found.
        """
        before = len(self.subscriptions)
        self.subscriptions = [s for s in self.subscriptions if s.name != name]
        removed = len(self.subscriptions) < before
        if removed:
            self._save_state()
        return removed

    def get_subscription(self, name: str) -> Optional[Subscription]:
        """Get a subscription by name.

        Parameters
        ----------
        name : str
            Subscription name.

        Returns
        -------
        Subscription or None
            The subscription, or None if not found.
        """
        for sub in self.subscriptions:
            if sub.name == name:
                return sub
        return None

    def set_interval(self, hours: int) -> None:
        """Set the fetch interval in hours.

        Parameters
        ----------
        hours : int
            Hours between scheduled runs.
        """
        self.status.interval_hours = hours
        self._save_state()

    def start(self) -> bool:
        """Start the background scheduler thread.

        Returns
        -------
        bool
            True if started, False if already running.
        """
        if self.status.running:
            return False

        self._stop_event.clear()
        self.status.running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("[PreprintScheduler] Started with %d subscriptions", len(self.subscriptions))
        return True

    def stop(self) -> bool:
        """Stop the background scheduler thread.

        Returns
        -------
        bool
            True if stopped, False if not running.
        """
        if not self.status.running:
            return False

        self._stop_event.set()
        self.status.running = False
        self.status.current_job = ""
        if self._thread is not None:
            self._thread.join(timeout=30)
        logger.info("[PreprintScheduler] Stopped")
        return True

    def run_once(self) -> Dict[str, Any]:
        """Run a single fetch cycle immediately.

        Returns
        -------
        Dict
            Summary of the fetch cycle.
        """
        return self._run_fetch_cycle()

    def get_status(self) -> Dict[str, Any]:
        """Get current scheduler status.

        Returns
        -------
        Dict
            Status dictionary.
        """
        with self._lock:
            result = self.status.to_dict()
            result["subscriptions"] = [s.to_dict() for s in self.subscriptions]
            result["recent_jobs"] = [j.to_dict() for j in self.jobs[-10:]]
            return result

    def get_jobs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent fetch jobs.

        Parameters
        ----------
        limit : int
            Maximum number of jobs to return.

        Returns
        -------
        List[Dict]
            Recent job records.
        """
        with self._lock:
            return [j.to_dict() for j in self.jobs[-limit:]]

    def _run_loop(self) -> None:
        """Main scheduler loop."""
        while not self._stop_event.is_set():
            try:
                self._run_fetch_cycle()
            except Exception as e:
                logger.error("[PreprintScheduler] Fetch cycle failed: %s", e)
                with self._lock:
                    self.status.error = str(e)

            next_run_time = time.time() + (self.status.interval_hours * 3600)
            with self._lock:
                self.status.next_run = datetime.fromtimestamp(next_run_time).isoformat()

            for _ in range(self.status.interval_hours * 3600):
                if self._stop_event.is_set():
                    break
                time.sleep(1)

    def _run_fetch_cycle(self) -> Dict[str, Any]:
        """Execute a single fetch cycle across all subscriptions.

        Returns
        -------
        Dict
            Summary of the cycle.
        """
        from gangdan.core.preprint_fetcher import PreprintFetcher

        summary = {
            "started_at": datetime.now().isoformat(),
            "subscriptions_processed": 0,
            "total_preprints": 0,
            "total_converted": 0,
            "errors": [],
        }

        with self._lock:
            self.status.last_run = summary["started_at"]
            self.status.current_job = "Fetching preprints..."
            self.status.total_runs += 1

        active_subs = [s for s in self.subscriptions if s.enabled]
        summary["subscriptions_processed"] = len(active_subs)

        for sub in active_subs:
            if self._stop_event.is_set():
                break

            for keyword in sub.keywords:
                for platform in sub.platforms:
                    job = self._create_job(sub.name, keyword, platform)
                    self._add_job(job)

                    try:
                        fetcher = PreprintFetcher(
                            platforms=[platform],
                            max_results=sub.max_results,
                        )

                        self._report_progress(f"Searching {platform} for '{keyword}'...", 0, 1)
                        papers = fetcher.search(keyword, categories=sub.categories if platform == "arxiv" else None)

                        job.preprints_found = len(papers)
                        job.status = "running"

                        converted = 0
                        for paper in papers:
                            if self._stop_event.is_set():
                                break

                            if paper.has_html or paper.has_tex:
                                try:
                                    self._convert_and_store(paper)
                                    converted += 1
                                except Exception as e:
                                    logger.warning("[PreprintScheduler] Convert failed for %s: %s", paper.preprint_id, e)

                        job.preprints_converted = converted
                        job.status = "completed"
                        job.finished_at = datetime.now().isoformat()

                        with self._lock:
                            sub.total_fetched += len(papers)
                            sub.last_fetched = job.finished_at
                            self.status.total_preprints += len(papers)

                        summary["total_preprints"] += len(papers)
                        summary["total_converted"] += converted

                        self._report_progress(
                            f"Found {len(papers)} preprints on {platform} for '{keyword}'",
                            converted,
                            len(papers),
                        )
                    except Exception as e:
                        job.status = "failed"
                        job.error = str(e)
                        job.finished_at = datetime.now().isoformat()
                        summary["errors"].append(f"{sub.name}/{keyword}/{platform}: {e}")
                        logger.error("[PreprintScheduler] Job failed: %s", e)

                    self._update_job(job)

        with self._lock:
            self.status.current_job = ""

        summary["finished_at"] = datetime.now().isoformat()
        self._save_state()
        return summary

    def _create_job(self, subscription_name: str, keyword: str, platform: str) -> FetchJob:
        """Create a new fetch job record."""
        import uuid

        return FetchJob(
            job_id=str(uuid.uuid4())[:8],
            subscription_name=subscription_name,
            keyword=keyword,
            platform=platform,
            status="pending",
            started_at=datetime.now().isoformat(),
        )

    def _add_job(self, job: FetchJob) -> None:
        """Add a job to the job list."""
        with self._lock:
            self.jobs.append(job)
            if len(self.jobs) > 100:
                self.jobs = self.jobs[-100:]

    def _update_job(self, job: FetchJob) -> None:
        """Update a job in the job list."""
        with self._lock:
            for i, j in enumerate(self.jobs):
                if j.job_id == job.job_id:
                    self.jobs[i] = job
                    break

    def _convert_and_store(self, paper) -> None:
        """Convert a preprint to Markdown and store it.

        Parameters
        ----------
        paper : PreprintMetadata
            Preprint metadata with URL info.
        """
        import tempfile

        from gangdan.core.preprint_converter import PreprintConverter

        preferred = "html" if paper.has_html else ("tex" if paper.has_tex else "pdf")

        if preferred == "html" and paper.html_url:
            converter = PreprintConverter(fallback_to_pdf=True)
            output_dir = Path(tempfile.mkdtemp(prefix=f"gangdan_{paper.preprint_id}_"))
            result = converter.convert_from_url(
                paper.html_url,
                content_type="html",
                output_dir=output_dir,
                preprint_id=paper.preprint_id,
            )
            if result.success:
                self._store_preprint(paper, result.markdown_path, "html")
        elif preferred == "tex" and paper.tex_source_url:
            converter = PreprintConverter(fallback_to_pdf=True)
            output_dir = Path(tempfile.mkdtemp(prefix=f"gangdan_{paper.preprint_id}_"))
            result = converter.convert_from_url(
                paper.tex_source_url,
                content_type="tex",
                output_dir=output_dir,
                preprint_id=paper.preprint_id,
            )
            if result.success:
                self._store_preprint(paper, result.markdown_path, "tex")

    def _store_preprint(self, paper, md_path: str, source_format: str) -> None:
        """Store a converted preprint in the cache.

        Parameters
        ----------
        paper : PreprintMetadata
            Preprint metadata.
        md_path : str
            Path to the converted Markdown file.
        source_format : str
            Source format used: 'html', 'tex', 'pdf'.
        """
        self._fetch_cache[paper.preprint_id] = {
            "metadata": paper.to_dict(),
            "markdown_path": md_path,
            "source_format": source_format,
            "stored_at": datetime.now().isoformat(),
        }

    def _report_progress(self, message: str, current: int, total: int) -> None:
        """Report progress via callback."""
        if self._on_progress:
            self._on_progress(message, current, total)
        logger.info("[PreprintScheduler] %s (%d/%d)", message, current, total)

    def _load_state(self) -> None:
        """Load scheduler state from disk."""
        if not self.state_file.exists():
            return

        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))

            subs_data = data.get("subscriptions", [])
            self.subscriptions = [Subscription.from_dict(s) for s in subs_data]

            status_data = data.get("status", {})
            self.status = SchedulerStatus(**status_data)

            jobs_data = data.get("jobs", [])
            self.jobs = [FetchJob(**j) for j in jobs_data]

            self._fetch_cache = data.get("cache", {})
        except Exception as e:
            logger.error("[PreprintScheduler] Failed to load state: %s", e)

    def _save_state(self) -> None:
        """Save scheduler state to disk."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "subscriptions": [s.to_dict() for s in self.subscriptions],
                "status": self.status.to_dict(),
                "jobs": [j.to_dict() for j in self.jobs[-50:]],
                "cache": self._fetch_cache,
            }
            self.state_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            logger.error("[PreprintScheduler] Failed to save state: %s", e)

    def get_cached_preprints(self) -> List[Dict[str, Any]]:
        """Get all cached preprints.

        Returns
        -------
        List[Dict]
            Cached preprint data.
        """
        return list(self._fetch_cache.values())

    def get_cached_preprint(self, preprint_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific cached preprint.

        Parameters
        ----------
        preprint_id : str
            Preprint identifier.

        Returns
        -------
        Dict or None
            Cached preprint data, or None if not found.
        """
        return self._fetch_cache.get(preprint_id)

    def clear_cache(self) -> None:
        """Clear the preprint cache."""
        self._fetch_cache.clear()
        self._save_state()
