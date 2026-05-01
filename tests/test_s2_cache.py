"""Tests for S2Cache (in-memory TTL cache)."""

import time

import pytest

from gangdan.core.s2_cache import S2Cache


class TestS2Cache:
    """Test S2Cache TTL cache behavior."""

    def test_put_and_get(self):
        cache = S2Cache(ttl_seconds=60)
        cache.put("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_missing_key(self):
        cache = S2Cache()
        assert cache.get("nonexistent") is None

    def test_expired_entry(self):
        cache = S2Cache(ttl_seconds=0)
        cache.put("key1", "value1")
        time.sleep(0.01)
        assert cache.get("key1") is None

    def test_clear_expired(self):
        cache = S2Cache(ttl_seconds=0)
        cache.put("key1", "value1")
        cache.put("key2", "value2")
        time.sleep(0.01)
        removed = cache.clear_expired()
        assert removed == 2
        assert cache.size() == 0

    def test_clear_all(self):
        cache = S2Cache()
        cache.put("key1", "value1")
        cache.put("key2", "value2")
        cache.clear()
        assert cache.size() == 0

    def test_size(self):
        cache = S2Cache()
        assert cache.size() == 0
        cache.put("key1", "value1")
        cache.put("key2", "value2")
        assert cache.size() == 2

    def test_overwrite_key(self):
        cache = S2Cache(ttl_seconds=60)
        cache.put("key1", "value1")
        cache.put("key1", "value2")
        assert cache.get("key1") == "value2"

    def test_ttl_keeps_valid_entries(self):
        cache = S2Cache(ttl_seconds=3600)
        cache.put("key1", "value1")
        assert cache.get("key1") == "value1"
