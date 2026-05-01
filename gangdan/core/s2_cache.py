"""In-memory TTL cache for Semantic Scholar API results.

Reference: CiteBox caching design for reducing API calls.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional


class S2Cache:
    """Simple in-memory cache for Semantic Scholar results with TTL.

    Parameters
    ----------
    ttl_seconds : int
        Time-to-live in seconds. Default is 86400 (24 hours).
    """

    def __init__(self, ttl_seconds: int = 86400) -> None:
        self._cache: Dict[str, tuple] = {}
        self._ttl = ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        """Get a cached value if it exists and is not expired.

        Parameters
        ----------
        key : str
            Cache key.

        Returns
        -------
        Any or None
            Cached value, or None if expired or not found.
        """
        if key not in self._cache:
            return None

        value, timestamp = self._cache[key]
        if time.time() - timestamp > self._ttl:
            del self._cache[key]
            return None

        return value

    def put(self, key: str, value: Any) -> None:
        """Store a value in the cache.

        Parameters
        ----------
        key : str
            Cache key.
        value : Any
            Value to cache.
        """
        self._cache[key] = (value, time.time())

    def clear_expired(self) -> int:
        """Remove all expired entries.

        Returns
        -------
        int
            Number of entries removed.
        """
        now = time.time()
        expired = [k for k, (_, ts) in self._cache.items() if now - ts > self._ttl]
        for k in expired:
            del self._cache[k]
        return len(expired)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()

    def size(self) -> int:
        """Return the number of cached entries."""
        return len(self._cache)
