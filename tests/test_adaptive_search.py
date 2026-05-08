"""Tests for gangdan.core.adaptive_search module."""

import pytest
from unittest.mock import MagicMock

from gangdan.core.adaptive_search import (
    AdaptiveResult,
    adaptive_embed,
    adaptive_search_collections,
    build_collection_info_cache,
    get_current_model_dimension,
)


class TestGetCurrentModelDimension:
    def test_returns_dimension_on_success(self):
        ollama = MagicMock()
        ollama.embed.return_value = [0.1] * 768
        assert get_current_model_dimension(ollama, "test-model") == 768

    def test_returns_zero_on_empty_model(self):
        ollama = MagicMock()
        assert get_current_model_dimension(ollama, "") == 0

    def test_returns_zero_on_none_ollama(self):
        assert get_current_model_dimension(None, "test-model") == 0

    def test_returns_zero_on_embed_failure(self):
        ollama = MagicMock()
        ollama.embed.side_effect = Exception("connection failed")
        assert get_current_model_dimension(ollama, "test-model") == 0

    def test_returns_zero_on_empty_embedding(self):
        ollama = MagicMock()
        ollama.embed.return_value = []
        assert get_current_model_dimension(ollama, "test-model") == 0


class TestBuildCollectionInfoCache:
    def test_returns_empty_when_no_vdb(self):
        assert build_collection_info_cache(None, ["coll1"]) == {}

    def test_returns_empty_when_no_get_collection_info(self):
        vdb = MagicMock(spec=[])
        assert build_collection_info_cache(vdb, ["coll1"]) == {}

    def test_caches_collection_info(self):
        vdb = MagicMock()
        vdb.get_collection_info.return_value = {"dimension": 768, "embedding_model": "nomic"}
        result = build_collection_info_cache(vdb, ["coll1", "coll2"])
        assert "coll1" in result
        assert "coll2" in result
        assert result["coll1"]["dimension"] == 768

    def test_skips_failed_collections(self):
        vdb = MagicMock()
        vdb.get_collection_info.side_effect = [
            {"dimension": 768},
            Exception("not found"),
        ]
        result = build_collection_info_cache(vdb, ["coll1", "coll2"])
        assert "coll1" in result
        assert "coll2" not in result


class TestAdaptiveEmbed:
    def test_dimensions_match(self):
        ollama = MagicMock()
        current_emb = [0.1] * 1024
        ar = adaptive_embed(
            query_text="test query",
            collection_name="coll1",
            current_embedding=current_emb,
            current_dim=1024,
            current_model="model-a",
            coll_info={"dimension": 1024, "embedding_model": "model-a"},
            ollama=ollama,
        )
        assert ar.embedding == current_emb
        assert not ar.adapted
        assert ar.reason == "dimensions_match"

    def test_dimension_mismatch_with_known_model(self):
        ollama = MagicMock()
        ollama.embed.return_value = [0.2] * 768
        current_emb = [0.1] * 1024
        ar = adaptive_embed(
            query_text="test query",
            collection_name="coll1",
            current_embedding=current_emb,
            current_dim=1024,
            current_model="model-a",
            coll_info={"dimension": 768, "embedding_model": "model-b"},
            ollama=ollama,
        )
        assert ar.adapted
        assert ar.embedding == [0.2] * 768
        assert "adapted" in ar.reason
        ollama.embed.assert_called_with("test query", "model-b")

    def test_dimension_mismatch_re_embed_failure_falls_back(self):
        ollama = MagicMock()
        ollama.embed.side_effect = Exception("model not found")
        current_emb = [0.1] * 1024
        ar = adaptive_embed(
            query_text="test query",
            collection_name="coll1",
            current_embedding=current_emb,
            current_dim=1024,
            current_model="model-a",
            coll_info={"dimension": 768, "embedding_model": "model-b"},
            ollama=ollama,
        )
        assert ar.adapted
        assert ar.embedding == current_emb
        assert "dimension_mismatch" in ar.reason

    def test_dimension_mismatch_no_model_info_falls_back(self):
        ollama = MagicMock()
        current_emb = [0.1] * 1024
        ar = adaptive_embed(
            query_text="test query",
            collection_name="coll1",
            current_embedding=current_emb,
            current_dim=1024,
            current_model="model-a",
            coll_info={"dimension": 768, "embedding_model": ""},
            ollama=ollama,
        )
        assert ar.adapted
        assert ar.embedding == current_emb
        assert "dimension_mismatch" in ar.reason

    def test_no_collection_dim_uses_current(self):
        ollama = MagicMock()
        current_emb = [0.1] * 1024
        ar = adaptive_embed(
            query_text="test query",
            collection_name="coll1",
            current_embedding=current_emb,
            current_dim=1024,
            current_model="model-a",
            coll_info={"dimension": 0, "embedding_model": ""},
            ollama=ollama,
        )
        assert ar.embedding == current_emb
        assert not ar.adapted
        assert "no_collection_dim_info" in ar.reason

    def test_re_embed_wrong_dim_falls_back(self):
        ollama = MagicMock()
        ollama.embed.return_value = [0.3] * 512
        current_emb = [0.1] * 1024
        ar = adaptive_embed(
            query_text="test query",
            collection_name="coll1",
            current_embedding=current_emb,
            current_dim=1024,
            current_model="model-a",
            coll_info={"dimension": 768, "embedding_model": "model-b"},
            ollama=ollama,
        )
        assert ar.adapted
        assert ar.embedding == current_emb
        assert "dimension_mismatch" in ar.reason

    def test_same_model_name_but_different_dim(self):
        ollama = MagicMock()
        current_emb = [0.1] * 1024
        ar = adaptive_embed(
            query_text="test query",
            collection_name="coll1",
            current_embedding=current_emb,
            current_dim=1024,
            current_model="model-a",
            coll_info={"dimension": 768, "embedding_model": "model-a"},
            ollama=ollama,
        )
        assert ar.adapted
        assert ar.embedding == current_emb


class TestAdaptiveSearchCollections:
    def test_returns_results_from_matching_collections(self):
        vdb = MagicMock()
        vdb.get_collection_info.return_value = {"dimension": 1024, "embedding_model": "model-a"}
        vdb.search.return_value = [
            {"document": "test doc", "distance": 0.3, "metadata": {"file": "a.md"}},
        ]
        ollama = MagicMock()
        ollama.embed.return_value = [0.1] * 1024

        results, log = adaptive_search_collections(
            query_text="test",
            collection_names=["coll1"],
            vector_db=vdb,
            ollama=ollama,
            current_model="model-a",
            top_k=5,
        )
        assert len(results) == 1
        assert len(log) == 1
        assert not log[0].adapted

    def test_handles_mismatched_collections(self):
        vdb = MagicMock()
        vdb.get_collection_info.side_effect = [
            {"dimension": 768, "embedding_model": "model-b"},
            {"dimension": 1024, "embedding_model": "model-a"},
        ]
        vdb.search.return_value = [{"document": "doc", "distance": 0.2, "metadata": {}}]
        ollama = MagicMock()
        ollama.embed.side_effect = [
            [0.1] * 1024,
            [0.2] * 768,
        ]

        results, log = adaptive_search_collections(
            query_text="test",
            collection_names=["coll1", "coll2"],
            vector_db=vdb,
            ollama=ollama,
            current_model="model-a",
            top_k=5,
        )
        assert len(log) == 2
        assert log[0].adapted
        assert not log[1].adapted

    def test_no_model_returns_empty(self):
        vdb = MagicMock()
        ollama = MagicMock()
        results, log = adaptive_search_collections(
            query_text="test",
            collection_names=["coll1"],
            vector_db=vdb,
            ollama=ollama,
            current_model="",
            top_k=5,
        )
        assert results == []
        assert log == []

    def test_search_exception_logged_not_crash(self):
        vdb = MagicMock()
        vdb.get_collection_info.return_value = {"dimension": 1024, "embedding_model": "model-a"}
        vdb.search.side_effect = Exception("dimension mismatch in search")
        ollama = MagicMock()
        ollama.embed.return_value = [0.1] * 1024

        results, log = adaptive_search_collections(
            query_text="test",
            collection_names=["coll1"],
            vector_db=vdb,
            ollama=ollama,
            current_model="model-a",
            top_k=5,
        )
        assert results == []
        assert len(log) == 1