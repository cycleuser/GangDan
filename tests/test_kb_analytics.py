"""Tests for KB analytics module and API routes."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def analytics_env(temp_data_dir):
    """Set up environment for analytics tests."""
    from gangdan.core.config import CONFIG
    CONFIG.embedding_model = "nomic-embed-text"
    CONFIG.chat_model = "llama3.2"
    yield temp_data_dir


@pytest.fixture
def mock_kb_manager(analytics_env):
    """Create a KB manager with test data."""
    from gangdan.core.kb_manager import CustomKBManager, KBDocEntry

    manager = CustomKBManager()
    kb = manager.create_kb("Test Analytics KB", "KB for analytics testing")

    docs_dir = analytics_env / "test_docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    test_docs = [
        {
            "doc_id": "doc_transformer_1",
            "title": "Attention Is All You Need",
            "content": "The Transformer is a neural network architecture based on self-attention mechanisms. It has become the dominant architecture for natural language processing tasks. The attention mechanism allows the model to weigh the importance of different parts of the input sequence.",
        },
        {
            "doc_id": "doc_transformer_2",
            "title": "BERT: Pre-training of Deep Bidirectional Transformers",
            "content": "BERT introduces a new language representation model using bidirectional Transformer pre-training. Unlike previous approaches, BERT is designed to pre-train deep bidirectional representations. The model achieves state-of-art results on many NLP tasks.",
        },
        {
            "doc_id": "doc_rlhf_1",
            "title": "Training Language Models with Human Feedback",
            "content": "We present a method for training language models using human feedback. Reinforcement Learning from Human Feedback (RLHF) has become a key technique for aligning language models with human preferences. This approach improves the helpfulness and safety of AI assistants.",
        },
        {
            "doc_id": "doc_rlhf_2",
            "title": "Constitutional AI: Harmlessness from AI Feedback",
            "content": "Constitutional AI is a method for training harmless AI systems without human feedback labels. The approach uses a set of principles (a constitution) to guide the model's behavior. This scales better than RLHF and produces models that are more aligned with human values.",
        },
        {
            "doc_id": "doc_vision_1",
            "title": "Vision Transformers for Image Recognition",
            "content": "We apply pure Transformer architectures to image recognition tasks. Vision Transformers (ViT) split images into patches and process them as sequences. This approach achieves excellent results on image classification benchmarks.",
        },
    ]

    for doc_data in test_docs:
        md_path = docs_dir / f"{doc_data['doc_id']}.md"
        md_path.write_text(f"# {doc_data['title']}\n\n{doc_data['content']}", encoding="utf-8")

        doc = KBDocEntry(
            doc_id=doc_data["doc_id"],
            title=doc_data["title"],
            source_type="paper",
            source_id="",
            source_platform="arxiv",
            markdown_path=str(md_path),
            content_preview=doc_data["content"][:500],
            authors=["Test Author"],
            published_date="2024-01-01",
            url="",
            tags=[],
            added_at="2024-01-01T00:00:00",
        )
        manager.add_document(kb.internal_name, doc, index_to_chroma=False)

    return manager


@pytest.fixture
def mock_ollama_client():
    """Create a mock Ollama client."""
    client = MagicMock()
    client.is_available.return_value = True
    client.chat_complete.return_value = json.dumps([
        {
            "stance": "Supports Transformer architecture",
            "doc_indices": [1, 2, 5],
            "summary": "Documents supporting the use of Transformer architecture",
            "confidence": 0.85,
        },
        {
            "stance": "Focuses on alignment methods",
            "doc_indices": [3, 4],
            "summary": "Documents discussing AI alignment techniques",
            "confidence": 0.75,
        },
    ])
    return client


# =============================================================================
# KBAnalytics Core Tests
# =============================================================================

class TestKBAnalyticsInit:
    """Test KBAnalytics initialization."""

    def test_init(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )
        assert analytics.kb_manager is mock_kb_manager
        assert analytics.ollama is mock_ollama_client

    def test_get_embedding_model(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )
        model = analytics._get_embedding_model()
        assert model == "nomic-embed-text"


class TestTopicClustering:
    """Test topic clustering functionality."""

    def test_topic_clusters_with_numpy(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )

        with patch.object(analytics, '_get_embeddings_for_kb') as mock_emb:
            mock_emb.return_value = (
                ["doc1", "doc2", "doc3", "doc4", "doc5"],
                ["Title A", "Title B", "Title C", "Title D", "Title E"],
                [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3], [0.9, 0.8, 0.7], [0.9, 0.8, 0.7], [0.5, 0.5, 0.5]],
            )

            clusters = analytics.get_topic_clusters("user_test_analytics_kb", n_clusters=2)

            assert len(clusters) == 2
            total_docs = sum(c.size for c in clusters)
            assert total_docs == 5

    def test_topic_clusters_auto_n(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )

        with patch.object(analytics, '_get_embeddings_for_kb') as mock_emb:
            mock_emb.return_value = (
                ["doc1", "doc2", "doc3"],
                ["Title A", "Title B", "Title C"],
                [[0.1, 0.2], [0.5, 0.5], [0.9, 0.8]],
            )

            clusters = analytics.get_topic_clusters("user_test_analytics_kb")

            assert len(clusters) >= 1
            assert all(c.size > 0 for c in clusters)

    def test_topic_clusters_single_doc(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )

        with patch.object(analytics, '_get_embeddings_for_kb') as mock_emb:
            mock_emb.return_value = (
                ["doc1"],
                ["Single Doc"],
                [[0.1, 0.2, 0.3]],
            )

            clusters = analytics.get_topic_clusters("user_test_analytics_kb")

            assert len(clusters) == 1
            assert clusters[0].size == 1

    def test_topic_clusters_no_numpy(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )

        with patch.object(analytics, '_get_embeddings_for_kb') as mock_emb:
            mock_emb.return_value = (
                ["doc1", "doc2", "doc3"],
                ["Title A", "Title B", "Title C"],
                [[0.1, 0.2], [0.5, 0.5], [0.9, 0.8]],
            )

            with patch.dict(sys.modules, {"numpy": None}):
                clusters = analytics.get_topic_clusters("user_test_analytics_kb", n_clusters=2)

                assert len(clusters) == 1

    def test_keyword_extraction(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )

        titles = [
            "Deep Python Programming for Natural Language Tasks",
            "JavaScript Approaches to Text Classification",
            "Rust Models for Machine Translation Systems",
        ]
        keywords = analytics._extract_keywords_from_titles(titles, top_k=5)

        assert len(keywords) > 0

    def test_simple_clustering(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics
        import numpy as np

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )

        X = np.array([
            [0.0, 0.0],
            [0.1, 0.1],
            [0.9, 0.9],
            [1.0, 1.0],
        ])

        labels, centroids = analytics._simple_clustering(X, 2)

        assert len(labels) == 4
        assert len(centroids) == 2
        assert set(labels) == {0, 1}


class TestPointCloud:
    """Test point cloud generation."""

    def test_pca_projection(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics
        import numpy as np

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )

        X = np.random.randn(10, 768)
        projected = analytics._pca_project(X, 2)

        assert projected.shape == (10, 2)

    def test_pca_3d(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics
        import numpy as np

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )

        X = np.random.randn(10, 768)
        projected = analytics._pca_project(X, 3)

        assert projected.shape == (10, 3)

    def test_point_cloud_2d(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )

        with patch.object(analytics, '_get_embeddings_for_kb') as mock_emb:
            mock_emb.return_value = (
                ["doc1", "doc2", "doc3"],
                ["Doc A", "Doc B", "Doc C"],
                [[0.1, 0.2, 0.3], [0.5, 0.5, 0.5], [0.9, 0.8, 0.7]],
            )

            cloud = analytics.get_point_cloud("user_test_analytics_kb", dimensions=2, method="pca")

            assert cloud.dimensions == 2
            assert cloud.method == "pca"
            assert len(cloud.points) == 3
            assert all("x" in p and "y" in p for p in cloud.points)

    def test_point_cloud_empty(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )

        with patch.object(analytics, '_get_embeddings_for_kb') as mock_emb, \
             patch.object(analytics, '_get_doc_contents') as mock_docs:
            mock_emb.return_value = ([], [], [])
            mock_docs.return_value = []  # No docs available for fallback

            cloud = analytics.get_point_cloud("user_test_analytics_kb")
            assert len(cloud.points) == 0  # No embbedings and no docs = empty

    def test_point_cloud_keyword_fallback(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )

        with patch.object(analytics, '_get_embeddings_for_kb') as mock_emb, \
             patch.object(analytics, '_get_doc_contents') as mock_docs:
            mock_emb.return_value = ([], [], [])
            mock_docs.return_value = [
                {"doc_id": "d1", "title": "Doc One", "content": "test content", "markdown_path": "Test (2024) - Doc One.md"},
                {"doc_id": "d2", "title": "Doc Two", "content": "other content", "markdown_path": "Smith (2025) - Doc Two.md"},
            ]

            cloud = analytics.get_point_cloud("user_test_analytics_kb")
            assert len(cloud.points) == 2  # Keyword fallback generates points
            assert cloud.method == "keyword"
            assert cloud.points[0]["label"] == "Test (2024) - Doc One"

    def test_tsne_fallback(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics
        import numpy as np

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )

        X = np.random.randn(10, 64)

        with patch.dict(sys.modules, {"sklearn.manifold": None}):
            projected = analytics._tsne_project(X, 2)
            assert projected.shape == (10, 2)

    def test_umap_fallback(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics
        import numpy as np

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )

        X = np.random.randn(10, 64)

        with patch.dict(sys.modules, {"umap": None}):
            projected = analytics._umap_project(X, 2)
            assert projected.shape == (10, 2)


class TestOpinionClustering:
    """Test opinion clustering."""

    def test_heuristic_opinion_clustering(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )

        doc_contents = [
            {"doc_id": "d1", "title": "Positive Review", "content": "This is a great approach with many benefits and advantages. It is effective and useful."},
            {"doc_id": "d2", "title": "Negative Review", "content": "This has many problems and issues. The drawbacks are significant and it fails to deliver."},
            {"doc_id": "d3", "title": "Neutral Review", "content": "This paper describes and analyzes the approach. We examine the method and present results."},
        ]

        clusters = analytics._heuristic_opinion_clustering(doc_contents, "test topic", max_clusters=3)

        assert len(clusters) >= 1
        assert all(len(c.doc_ids) > 0 for c in clusters)

    def test_llm_opinion_clustering(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )

        doc_contents = [
            {"doc_id": "d1", "title": "Paper A", "content": "Supports the new approach with strong evidence."},
            {"doc_id": "d2", "title": "Paper B", "content": "Also supports the approach with additional benefits."},
            {"doc_id": "d3", "title": "Paper C", "content": "Criticizes the approach and points out limitations."},
        ]

        clusters = analytics._llm_opinion_clustering(doc_contents, "test topic", max_clusters=2)

        assert len(clusters) >= 1

    def test_llm_opinion_clustering_parse_json(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )

        response = json.dumps([
            {"stance": "Pro", "doc_indices": [1, 2], "summary": "Supports", "confidence": 0.9},
            {"stance": "Con", "doc_indices": [3], "summary": "Opposes", "confidence": 0.8},
        ])

        result = analytics._parse_json_from_response(response)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_llm_opinion_clustering_parse_json_code_block(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )

        response = '```json\n[{"stance": "Pro", "doc_indices": [1], "summary": "Supports", "confidence": 0.9}]\n```'

        result = analytics._parse_json_from_response(response)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_opinion_clusters_empty(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )

        with patch.object(mock_kb_manager, 'get_documents', return_value=[]):
            clusters = analytics.get_opinion_clusters("user_test_analytics_kb")
            assert clusters == []


class TestStrictCitation:
    """Test strict citation functionality."""

    def test_generate_cited_response(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )

        mock_ollama_client.chat_complete.return_value = (
            "The Transformer architecture [1] uses self-attention mechanisms. "
            "BERT [2] extends this with bidirectional pre-training."
        )

        result = analytics.generate_cited_response(
            query="What is the Transformer?",
            required_doc_ids=["doc_transformer_1", "doc_transformer_2"],
            kb_name="user_test_analytics_kb",
        )

        assert "response" in result
        assert "citations" in result
        assert "missing_citations" in result
        assert len(result["citations"]) == 2
        assert len(result["missing_citations"]) == 0

    def test_generate_cited_response_missing_docs(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )

        result = analytics.generate_cited_response(
            query="Test question",
            required_doc_ids=["nonexistent_doc"],
            kb_name="user_test_analytics_kb",
        )

        assert "missing_citations" in result
        assert "nonexistent_doc" in result["missing_citations"]

    def test_generate_cited_response_all_missing(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )

        result = analytics.generate_cited_response(
            query="Test",
            required_doc_ids=["doc_a", "doc_b", "doc_c"],
            kb_name="user_test_analytics_kb",
        )

        assert "No specified documents found" in result["response"]

    def test_get_document_content(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )

        content = analytics.get_document_content(
            "user_test_analytics_kb",
            "doc_transformer_1",
            max_length=1000,
        )

        assert content is not None
        assert content["doc_id"] == "doc_transformer_1"
        assert "Attention" in content["title"]

    def test_get_document_content_not_found(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )

        content = analytics.get_document_content(
            "user_test_analytics_kb",
            "nonexistent_doc",
        )

        assert content is None


class TestEmbeddingRetrieval:
    """Test embedding retrieval from ChromaDB."""

    def test_get_embeddings_for_kb_no_chroma(self, mock_kb_manager, mock_ollama_client):
        from gangdan.core.kb_analytics import KBAnalytics

        analytics = KBAnalytics(
            kb_manager=mock_kb_manager,
            ollama_client=mock_ollama_client,
        )

        doc_ids, titles, embeddings = analytics._get_embeddings_for_kb("nonexistent_kb")

        assert doc_ids == []
        assert titles == []
        assert embeddings == []


# =============================================================================
# Data Class Tests
# =============================================================================

class TestDataClasses:
    """Test analytics data classes."""

    def test_cluster_info_to_dict(self):
        from gangdan.core.kb_analytics import ClusterInfo

        cluster = ClusterInfo(
            cluster_id=1,
            name="test_cluster",
            doc_ids=["doc1", "doc2"],
            centroid=[0.1, 0.2, 0.3],
            representative_doc="doc1",
            size=2,
            keywords=["test", "cluster"],
        )

        d = cluster.to_dict()
        assert d["cluster_id"] == 1
        assert d["name"] == "test_cluster"
        assert d["doc_ids"] == ["doc1", "doc2"]
        assert d["size"] == 2
        assert d["keywords"] == ["test", "cluster"]

    def test_point_cloud_to_dict(self):
        from gangdan.core.kb_analytics import PointCloudData

        cloud = PointCloudData(
            points=[
                {"doc_id": "doc1", "x": 0.1, "y": 0.2, "z": 0, "label": "Doc 1", "cluster": 0},
            ],
            dimensions=2,
            method="pca",
        )

        d = cloud.to_dict()
        assert d["dimensions"] == 2
        assert d["method"] == "pca"
        assert len(d["points"]) == 1

    def test_opinion_cluster_to_dict(self):
        from gangdan.core.kb_analytics import OpinionCluster

        cluster = OpinionCluster(
            opinion_id=1,
            stance="Supports X",
            doc_ids=["doc1", "doc2"],
            confidence=0.85,
            summary="Documents that support X",
        )

        d = cluster.to_dict()
        assert d["opinion_id"] == 1
        assert d["stance"] == "Supports X"
        assert d["confidence"] == 0.85
