"""Lightweight cron scheduler for GangDan Refined.

Supports interval-based ('every'), fixed-time ('at'), and cron-expression
schedule types. Runs in a background daemon thread. Jobs are persisted
to JSON so they survive restarts.

Inspired by nanobot's cron service module.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CronJob:
    """A scheduled job definition.

    Attributes
    ----------
    job_id : str
        Unique identifier (auto-generated).
    name : str
        Human-readable name.
    kind : str
        "every", "at", or "cron".
    schedule_value : str
        For "every": seconds ("3600"), for "at": "HH:MM", for "cron": "0 */6 * * *".
    action : str
        Description of what to execute (e.g., "fetch_arxiv", "reindex_kb").
    enabled : bool
        Whether this job is currently active.
    last_run : str or None
        ISO timestamp of last execution.
    last_result : str or None
        "ok", "error", or None.
    created_at : str
        ISO timestamp of creation.
    """

    job_id: str = ""
    name: str = ""
    kind: str = "every"   # "every" | "at" | "cron"
    schedule_value: str = "3600"  # seconds for "every", "HH:MM" for "at", cron expr
    action: str = ""
    enabled: bool = True
    last_run: Optional[str] = None
    last_result: Optional[str] = None
    created_at: str = ""

    def __post_init__(self):
        if not self.job_id:
            import uuid
            self.job_id = uuid.uuid4().hex[:12]
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


class CronService:
    """Background scheduler that runs registered jobs on their cadence.

    Uses a single daemon thread that wakes every 30 seconds to check
    which jobs are due. Jobs are persisted to a JSON file.

    Attributes
    ----------
    jobs_path : Path
        Path to the JSON persistence file.
    jobs : Dict[str, CronJob]
        Registered jobs keyed by job_id.
    _actions : Dict[str, Callable]
        Mapping of action names to callables.
    _running : bool
        Whether the scheduler loop is active.
    _lock : threading.Lock
        Mutex for thread-safe job mutation.
    """

    def __init__(self, jobs_dir: str | Path) -> None:
        """Initialize cron service.

        Parameters
        ----------
        jobs_dir : str or Path
            Directory for job persistence.
        """
        self.jobs_path = Path(jobs_dir) / "cron_jobs.json"
        self.jobs_path.parent.mkdir(parents=True, exist_ok=True)
        self.jobs: Dict[str, CronJob] = {}
        self._actions: Dict[str, Callable] = {}
        self._running = False
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._load()

    # ------------------------------------------------------------------
    # Job management
    # ------------------------------------------------------------------

    def add_job(
        self,
        name: str,
        kind: str,
        schedule_value: str,
        action: str = "",
        enabled: bool = True,
    ) -> CronJob:
        """Register a new job.

        Parameters
        ----------
        name : str
            Human-readable name.
        kind : str
            "every", "at", or "cron".
        schedule_value : str
            Schedule specification.
        action : str
            Action name (must match a registered action callback).
        enabled : bool
            Start enabled.

        Returns
        -------
        CronJob
            The created job.
        """
        job = CronJob(
            name=name,
            kind=kind,
            schedule_value=schedule_value,
            action=action,
            enabled=enabled,
        )
        with self._lock:
            self.jobs[job.job_id] = job
            self._save()
        logger.info("Cron: added job '%s' [%s %s]", name, kind, schedule_value)
        return job

    def remove_job(self, job_id: str) -> bool:
        """Remove a job by ID."""
        with self._lock:
            if job_id in self.jobs:
                del self.jobs[job_id]
                self._save()
                logger.info("Cron: removed job %s", job_id)
                return True
        return False

    def toggle_job(self, job_id: str, enabled: bool) -> bool:
        """Enable or disable a job."""
        with self._lock:
            if job_id in self.jobs:
                self.jobs[job_id].enabled = enabled
                self._save()
                return True
        return False

    def list_jobs(self) -> List[dict]:
        """List all jobs as dicts."""
        with self._lock:
            return [asdict(j) for j in self.jobs.values()]

    def register_action(self, name: str, callback: Callable) -> None:
        """Register a named action callback.

        Parameters
        ----------
        name : str
            Action name referenced in job.action.
        callback : Callable
            Function to call when job triggers. Receives the CronJob instance.
        """
        self._actions[name] = callback

    # ------------------------------------------------------------------
    # Scheduler loop
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background scheduler thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="cron-scheduler")
        self._thread.start()
        logger.info("Cron: scheduler started")

    def stop(self) -> None:
        """Stop the scheduler thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("Cron: scheduler stopped")

    def _loop(self) -> None:
        """Main scheduler loop — checks every 30s."""
        while self._running:
            now = time.time()
            with self._lock:
                jobs_snapshot = list(self.jobs.values())
            for job in jobs_snapshot:
                if not job.enabled:
                    continue
                if self._is_due(job, now):
                    self._fire(job)
            time.sleep(30)

    def _is_due(self, job: CronJob, now_ts: float) -> bool:
        """Check if a job is due to run."""
        last = job.last_run
        if last:
            try:
                last_ts = datetime.fromisoformat(last).timestamp()
            except ValueError:
                last_ts = 0
        else:
            last_ts = 0

        if job.kind == "every":
            try:
                interval = int(job.schedule_value)
            except ValueError:
                interval = 3600
            return (now_ts - last_ts) >= interval

        if job.kind == "at":
            # Parse HH:MM
            m = re.match(r"(\d{1,2}):(\d{2})", job.schedule_value)
            if not m:
                return False
            h, mm = int(m.group(1)), int(m.group(2))
            now_dt = datetime.fromtimestamp(now_ts)
            target = now_dt.replace(hour=h, minute=mm, second=0, microsecond=0)
            if target <= now_dt:
                target = target.replace(day=target.day + 1)
            if last_ts < target.timestamp():
                return now_ts >= target.timestamp()

        if job.kind == "cron":
            return self._cron_matches(job.schedule_value, now_ts, last_ts)

        return False

    def _cron_matches(self, expr: str, now_ts: float, last_ts: float) -> bool:
        """Simple cron matching (minute, hour, dom, month, dow only)."""
        parts = expr.strip().split()
        if len(parts) != 5:
            return False
        now = datetime.fromtimestamp(now_ts)
        last = datetime.fromtimestamp(last_ts) if last_ts else datetime(2000, 1, 1)
        fields = {
            "minute": (now.minute, parts[0]),
            "hour": (now.hour, parts[1]),
            "dom": (now.day, parts[2]),
            "month": (now.month, parts[3]),
            "dow": (now.weekday(), parts[4]),
        }
        for _, (value, spec) in fields.items():
            if not self._match_cron_field(value, spec):
                return False
        return True

    @staticmethod
    def _match_cron_field(value: int, spec: str) -> bool:
        """Check if a single value matches a cron field spec."""
        if spec == "*":
            return True
        for part in spec.split(","):
            part = part.strip()
            if "-" in part:
                lo, hi = part.split("-", 1)
                if int(lo) <= value <= int(hi):
                    return True
            elif "/" in part:
                base, step = part.split("/", 1)
                base_val = int(base) if base != "*" else 0
                if base == "*" and value % int(step) == 0:
                    return True
                if (value - base_val) % int(step) == 0 and value >= base_val:
                    return True
            else:
                if int(part) == value:
                    return True
        return False

    def _fire(self, job: CronJob) -> None:
        """Execute a job's action."""
        logger.info("Cron: firing job '%s' [%s]", job.name, job.action)
        try:
            callback = self._actions.get(job.action)
            if callback:
                result = callback(job)
                job.last_result = "ok" if result else "error"
            else:
                job.last_result = "error"
                logger.warning("Cron: no action registered for '%s'", job.action)
        except Exception as e:
            job.last_result = "error"
            logger.error("Cron: job '%s' failed: %s", job.name, e)
        job.last_run = datetime.now().isoformat()
        self._save()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load jobs from JSON."""
        if self.jobs_path.exists():
            try:
                data = json.loads(self.jobs_path.read_text(encoding="utf-8"))
                self.jobs = {
                    j["job_id"]: CronJob(**j)
                    for j in data.get("jobs", [])
                }
                logger.info("Cron: loaded %d jobs", len(self.jobs))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Cron: failed to load jobs: %s", e)

    def _save(self) -> None:
        """Save jobs to JSON."""
        try:
            data = {"jobs": [asdict(j) for j in self.jobs.values()]}
            self.jobs_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as e:
            logger.error("Cron: failed to save jobs: %s", e)


# Module-level singleton
_cron_service: Optional[CronService] = None


def get_cron_service() -> CronService:
    """Get or create the shared cron service instance."""
    global _cron_service
    if _cron_service is None:
        from gangdan_refined.core.config import DATA_DIR
        _cron_service = CronService(DATA_DIR / "cron")
        _cron_service.start()
    return _cron_service
