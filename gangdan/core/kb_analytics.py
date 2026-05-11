"""Knowledge base analytics module.

Provides analytical capabilities for knowledge bases:
- Topic clustering: group documents by semantic similarity
- Point cloud data: 2D/3D projections for visualization
- Opinion clusters: group documents by viewpoint using LLM
- Strict citation: force specific article references in responses
- Review writing: generate literature review from selected documents

All methods accept an optional doc_ids parameter to scope analysis
to a user-selected subset of documents.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ClusterInfo:
    """Information about a document cluster.

    Attributes
    ----------
    cluster_id : int
        Cluster identifier.
    name : str
        Auto-generated or user-assigned cluster name.
    doc_ids : List[str]
        Document IDs in this cluster.
    centroid : Optional[List[float]]
        Cluster centroid embedding vector.
    representative_doc : str
        Doc ID closest to centroid.
    size : int
        Number of documents in cluster.
    keywords : List[str]
        Extracted keywords describing the cluster.
    """

    cluster_id: int = 0
    name: str = ""
    doc_ids: List[str] = field(default_factory=list)
    centroid: Optional[List[float]] = None
    representative_doc: str = ""
    size: int = 0
    keywords: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "name": self.name,
            "doc_ids": self.doc_ids,
            "representative_doc": self.representative_doc,
            "size": self.size,
            "keywords": self.keywords,
        }


@dataclass
class PointCloudData:
    """2D/3D projection of document embeddings for visualization.

    Attributes
    ----------
    points : List[Dict]
        Each point: {"doc_id": str, "x": float, "y": float, "z": float, "label": str, "cluster": int}.
    dimensions : int
        Projection dimensions (2 or 3).
    method : str
        Projection method: "pca", "tsne", or "umap".
    """

    points: List[Dict[str, Any]] = field(default_factory=list)
    dimensions: int = 2
    method: str = "pca"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "points": self.points,
            "dimensions": self.dimensions,
            "method": self.method,
        }


@dataclass
class OpinionCluster:
    """A cluster of documents sharing a similar viewpoint or stance.

    Attributes
    ----------
    opinion_id : int
        Cluster identifier.
    stance : str
        Summary of the viewpoint (e.g., "supports X", "opposes Y").
    doc_ids : List[str]
        Document IDs expressing this viewpoint.
    confidence : float
        How cohesive the cluster is (0-1).
    summary : str
        LLM-generated summary of this opinion cluster.
    """

    opinion_id: int = 0
    stance: str = ""
    doc_ids: List[str] = field(default_factory=list)
    confidence: float = 0.0
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "opinion_id": self.opinion_id,
            "stance": self.stance,
            "doc_ids": self.doc_ids,
            "confidence": self.confidence,
            "summary": self.summary,
        }


class KBAnalytics:
    """Analytics engine for knowledge bases.

    Provides topic clustering, point cloud generation, opinion clustering,
    strict citation support, and literature review writing.

    All analysis methods accept an optional doc_ids parameter to restrict
    the analysis to a user-selected subset of documents.

    Parameters
    ----------
    kb_manager : CustomKBManager
        Knowledge base manager for accessing documents and embeddings.
    ollama_client : OllamaClient
        Client for embedding generation and LLM analysis.
    """

    def __init__(self, kb_manager, ollama_client) -> None:
        self.kb_manager = kb_manager
        self.ollama = ollama_client
        self._embedding_model = None

    def _get_embedding_model(self) -> str:
        """Get the current embedding model from config."""
        if self._embedding_model is None:
            from gangdan.core.config import CONFIG
            self._embedding_model = CONFIG.embedding_model
        return self._embedding_model or ""

    def _get_embeddings_for_kb(
        self,
        internal_name: str,
        doc_ids_filter: Optional[List[str]] = None,
    ) -> Tuple[List[str], List[str], List[List[float]]]:
        """Retrieve document IDs, titles, and embeddings from a KB.

        Parameters
        ----------
        internal_name : str
            KB internal name.
        doc_ids_filter : List[str] or None
            If provided, only return embeddings for these doc IDs.

        Returns
        -------
        Tuple of (doc_ids, titles, embeddings).
        """
        from gangdan.core.chroma_manager import ChromaManager
        from gangdan.core.config import CHROMA_DIR

        doc_ids = []
        titles = []
        embeddings = []

        try:
            manager = ChromaManager(persist_dir=str(CHROMA_DIR))
            if manager.client is not None:
                collection = manager.client.get_collection(name=internal_name)
                if collection is not None:
                    result = collection.get(include=["embeddings", "metadatas", "documents"])
                    if result and result.get("ids"):
                        for i, cid in enumerate(result["ids"]):
                            meta = result["metadatas"][i] if result.get("metadatas") else {}
                            emb = result["embeddings"][i] if result.get("embeddings") else None
                            if emb is None:
                                continue
                            doc_id = meta.get("doc_id", cid)
                            title = meta.get("title", "")
                            if not title:
                                docs = result.get("documents", [])
                                if docs and i < len(docs):
                                    title = docs[i][:200]
                            if doc_ids_filter and doc_id not in filter_set:
                                continue
                            doc_ids.append(doc_id)
                            titles.append(title)
                            embeddings.append(emb)
        except Exception as e:
            logger.error("[KBAnalytics] Failed to get embeddings from ChromaDB: %s", e)

        return doc_ids, titles, embeddings

    def _get_doc_contents(
        self,
        internal_name: str,
        doc_ids_filter: Optional[List[str]] = None,
        max_content_length: int = 2000,
    ) -> List[Dict[str, Any]]:
        """Get document contents from KB, optionally filtered by doc_ids.

        Parameters
        ----------
        internal_name : str
            KB internal name.
        doc_ids_filter : List[str] or None
            If provided, only return these docs.
        max_content_length : int
            Max content length per document.

        Returns
        -------
        List[Dict]
            List of dicts with doc_id, title, content.
        """
        docs = self.kb_manager.get_documents(internal_name)
        if not docs:
            return []

        filter_set = set(doc_ids_filter) if doc_ids_filter else None
        result = []

        for doc in docs:
            if filter_set and doc.doc_id not in filter_set:
                continue

            content = ""
            if doc.markdown_path:
                from pathlib import Path
                md_path = Path(doc.markdown_path)
                if md_path.exists():
                    content = md_path.read_text(encoding="utf-8")[:max_content_length]
            if not content:
                content = doc.content_preview

            result.append({
                "doc_id": doc.doc_id,
                "title": doc.title,
                "content": content,
                "authors": doc.authors or [],
                "published_date": doc.published_date or "",
                "markdown_path": doc.markdown_path or "",
            })

        return result

    # =========================================================================
    # Topic Clustering
    # =========================================================================

    def get_topic_clusters(
        self,
        internal_name: str,
        n_clusters: Optional[int] = None,
        method: str = "kmeans",
        doc_ids: Optional[List[str]] = None,
    ) -> List[ClusterInfo]:
        """Cluster documents in a KB by semantic topic.

        Parameters
        ----------
        internal_name : str
            KB internal name.
        n_clusters : int or None
            Number of clusters. Auto-determined if None.
        method : str
            Clustering method: "kmeans" (default).
        doc_ids : List[str] or None
            If provided, only cluster these documents.

        Returns
        -------
        List[ClusterInfo]
            List of discovered topic clusters.
        """
        d_ids, d_titles, d_embeddings = self._get_embeddings_for_kb(internal_name, doc_ids_filter=doc_ids)

        # Fallback to keyword-based clustering if no embeddings available
        if len(d_embeddings) == 0:
            return self._keyword_clustering(internal_name, n_clusters, doc_ids)

        if len(d_embeddings) < 2:
            return [
                ClusterInfo(
                    cluster_id=0,
                    name=d_titles[0][:40] if d_titles else "single_doc",
                    doc_ids=d_ids,
                    size=len(d_ids),
                    keywords=[],
                )
            ]

        n = len(d_embeddings)
        if n_clusters is None:
            n_clusters = max(2, min(int(n ** 0.5), 20))
        n_clusters = min(n_clusters, n)

        try:
            import numpy as np
        except ImportError:
            logger.warning("[KBAnalytics] numpy not available")
            return self._keyword_clustering(internal_name, n_clusters, doc_ids)

        X = np.array(d_embeddings)

        try:
            from sklearn.cluster import KMeans

            kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            labels = kmeans.fit_predict(X)
            centroids = kmeans.cluster_centers_
        except ImportError:
            logger.warning("[KBAnalytics] sklearn not available, using simple clustering")
            labels, centroids = self._simple_clustering(X, n_clusters)

        clusters = []
        for cid in range(n_clusters):
            mask = labels == cid
            cluster_doc_ids = [d_ids[i] for i in range(n) if mask[i]]
            cluster_titles = [d_titles[i] for i in range(n) if mask[i]]

            if not cluster_doc_ids:
                continue

            centroid = centroids[cid].tolist()
            dists = np.linalg.norm(X[mask] - centroid, axis=1)
            rep_idx = int(np.argmin(dists))
            rep_doc = cluster_doc_ids[rep_idx]

            keywords = self._extract_keywords_from_titles(cluster_titles)

            clusters.append(
                ClusterInfo(
                    cluster_id=int(cid),
                    name=f"topic_{cid}",
                    doc_ids=cluster_doc_ids,
                    centroid=centroid,
                    representative_doc=rep_doc,
                    size=len(cluster_doc_ids),
                    keywords=keywords,
                )
            )

        return clusters

    def _keyword_clustering(
        self,
        internal_name: str,
        n_clusters: Optional[int] = None,
        doc_ids: Optional[List[str]] = None,
    ) -> List[ClusterInfo]:
        """Keyword-based clustering fallback when embeddings are not available."""
        doc_contents = self._get_doc_contents(internal_name, doc_ids_filter=doc_ids, max_content_length=500)
        if not doc_contents:
            return []

        import re
        from collections import Counter

        stop_words = self._extract_keywords_from_titles([])  # reuse stop words isn't right, use inline
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
            "this", "that", "it", "its", "based", "using", "can", "may",
        }

        # Extract key terms from each doc
        doc_terms = []
        for doc in doc_contents:
            text = (doc["title"] + " " + doc["content"][:300]).lower()
            words = [w for w in re.findall(r"\b[a-z]{4,}\b", text) if w not in stop_words]
            doc_terms.append((doc["doc_id"], doc["title"], Counter(words)))

        n = len(doc_terms)
        if n == 0:
            return []

        if n_clusters is None:
            n_clusters = max(2, min(int(n ** 0.5), 10))
        n_clusters = min(n_clusters, n)

        # Greedy clustering by term overlap
        remaining = list(range(n))
        clusters = []
        cluster_id = 0

        while remaining and cluster_id < n_clusters:
            seed = remaining.pop(0)
            cluster_items = [seed]
            _, _, seed_counter = doc_terms[seed]
            seed_terms = set(seed_counter.keys())

            to_remove = []
            for idx in remaining:
                _, _, c = doc_terms[idx]
                overlap = len(set(c.keys()) & seed_terms)
                if overlap >= 1:
                    cluster_items.append(idx)
                    seed_terms |= set(c.keys())
                    to_remove.append(idx)
            for idx in to_remove:
                remaining.remove(idx)

            doc_ids_in = [doc_terms[i][0] for i in cluster_items]
            titles_in = [doc_terms[i][1] for i in cluster_items]
            keywords = self._extract_keywords_from_titles(titles_in)
            clusters.append(ClusterInfo(
                cluster_id=cluster_id,
                name=keywords[0] if keywords else f"topic_{cluster_id}",
                doc_ids=doc_ids_in,
                size=len(doc_ids_in),
                keywords=keywords,
            ))
            cluster_id += 1

        # Assign any remaining docs to nearest cluster
        if remaining:
            if clusters:
                for idx in remaining:
                    clusters[0].doc_ids.append(doc_terms[idx][0])
                    clusters[0].size += 1
            else:
                clusters.append(ClusterInfo(
                    cluster_id=0,
                    name="all_docs",
                    doc_ids=[t[0] for t in doc_terms],
                    size=n,
                    keywords=[],
                ))

        return clusters

    def _simple_clustering(self, X, n_clusters):
        """Simple distance-based clustering without sklearn.

        Uses a greedy approach: pick n_clusters seeds, assign each point to nearest seed.
        """
        import numpy as np

        n = X.shape[0]
        indices = list(range(n))

        seeds = [0]
        for _ in range(1, n_clusters):
            max_dist = -1
            best_idx = 0
            for i in indices:
                if i in seeds:
                    continue
                min_d = min(np.linalg.norm(X[i] - X[s]) for s in seeds)
                if min_d > max_dist:
                    max_dist = min_d
                    best_idx = i
            seeds.append(best_idx)

        labels = np.zeros(n, dtype=int)
        for i in range(n):
            dists = [np.linalg.norm(X[i] - X[s]) for s in seeds]
            labels[i] = int(np.argmin(dists))

        centroids = np.array([X[seeds[c]] for c in range(n_clusters)])
        return labels, centroids

    def _extract_keywords_from_titles(self, titles: List[str], top_k: int = 5) -> List[str]:
        """Extract common keywords from a list of titles.

        Parameters
        ----------
        titles : List[str]
            Document titles.
        top_k : int
            Number of top keywords to return.

        Returns
        -------
        List[str]
            Top keywords.
        """
        import re
        from collections import Counter

        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "must", "shall", "can", "need",
            "dare", "ought", "used", "it", "its", "this", "that", "these", "those",
            "i", "you", "he", "she", "we", "they", "what", "which", "who", "whom",
            "whose", "where", "when", "why", "how", "all", "each", "every", "both",
            "few", "many", "much", "some", "any", "no", "not", "only", "own",
            "same", "so", "than", "too", "very", "just", "also", "now", "here",
            "there", "then", "once", "if", "because", "as", "until", "while",
            "about", "against", "between", "into", "through", "during", "before",
            "after", "above", "below", "up", "down", "out", "off", "over", "under",
            "again", "further", "more", "most", "other", "such", "new", "using",
            "based", "approach", "method", "study", "analysis", "review",
            "learning", "deep", "neural", "network", "model", "system",
        }

        words = []
        for title in titles:
            tokens = re.findall(r"[a-zA-Z]{3,}", title.lower())
            words.extend(t for t in tokens if t not in stop_words)

        counter = Counter(words)
        return [w for w, _ in counter.most_common(top_k)]

    # =========================================================================
    # Point Cloud Generation
    # =========================================================================

    def get_point_cloud(
        self,
        internal_name: str,
        dimensions: int = 2,
        method: str = "pca",
        cluster_labels: Optional[List[int]] = None,
        doc_ids: Optional[List[str]] = None,
    ) -> PointCloudData:
        """Generate 2D/3D point cloud from document embeddings.

        Falls back to keyword-based positioning when embeddings unavailable.

        Parameters
        ----------
        internal_name : str
            KB internal name.
        dimensions : int
            Output dimensions (2 or 3).
        method : str
            Projection method: "pca", "tsne", or "umap".
        cluster_labels : List[int] or None
            Optional cluster labels for coloring points.
        doc_ids : List[str] or None
            If provided, only project these documents.

        Returns
        -------
        PointCloudData
            Projected points with metadata.
        """
        import math, random, re
        from collections import Counter

        d_ids, d_titles, d_embeddings = self._get_embeddings_for_kb(internal_name, doc_ids_filter=doc_ids)

        if len(d_embeddings) < 2:
            # Fallback: keyword similarity-based positioning
            doc_contents = self._get_doc_contents(internal_name, doc_ids_filter=doc_ids, max_content_length=2000)
            if doc_contents:
                # Simple MDS via keyword overlap similarity + force layout
                n = len(doc_contents)
                if n == 0:
                    return PointCloudData(dimensions=dimensions, method=method)

                # Stop words
                sw = {"the","a","an","and","or","but","in","on","at","to","for",
                       "of","with","by","from","is","are","was","were","be","been",
                       "this","that","it","its","based","using","can","may","has","have",
                       "which","also","such","not","more","some","all","new","one","two"}

                # Extract keyword sets per doc
                doc_kw = []
                for dc in doc_contents:
                    text = (dc["title"] + " " + dc["content"][:800]).lower()
                    words = set(re.findall(r"\b[a-z]{4,}\b", text)) - sw
                    doc_kw.append(words)

                # Jaccard similarity matrix
                sim = [[0.0]*n for _ in range(n)]
                for i in range(n):
                    for j in range(i+1, n):
                        u = len(doc_kw[i] | doc_kw[j])
                        if u > 0:
                            s = len(doc_kw[i] & doc_kw[j]) / u
                            sim[i][j] = sim[j][i] = s

                # Simple force-directed layout
                positions = [[random.uniform(-3, 3), random.uniform(-3, 3)] for _ in range(n)]
                random.seed(42)
                for _ in range(200):
                    forces = [[0.0, 0.0] for _ in range(n)]
                    for i in range(n):
                        for j in range(n):
                            if i == j:
                                continue
                            dx = positions[i][0] - positions[j][0]
                            dy = positions[i][1] - positions[j][1]
                            dist = math.sqrt(dx*dx + dy*dy) + 0.01
                            # Attraction if similar, repulsion if dissimilar
                            force = (1.0 - sim[i][j]) * 3.0 - sim[i][j] * 2.0
                            if dist < 0.5:
                                force = 2.0  # Strong repulsion for overlapping
                            fx = (dx / dist) * force * 0.01
                            fy = (dy / dist) * force * 0.01
                            forces[i][0] += fx
                            forces[i][1] += fy
                    for i in range(n):
                        positions[i][0] += forces[i][0]
                        positions[i][1] += forces[i][1]

                # Get clusters for coloring
                clusters = self._keyword_clustering(internal_name, n_clusters=min(6, max(2, n//2)), doc_ids=doc_ids)
                doc_to_cluster = {}
                for ci, cl in enumerate(clusters):
                    for did in cl.doc_ids:
                        doc_to_cluster[did] = ci

                points = []
                for i, dc in enumerate(doc_contents):
                    did = dc["doc_id"]
                    # Generate brief summary: first sentence or first 200 chars
                    content = dc.get("content", "")
                    summary = content[:300].replace("\n", " ").strip()
                    if len(summary) > 250:
                        # Try to cut at sentence boundary
                        cut = max(summary.rfind(". ", 0, 250), summary.rfind("? ", 0, 250), summary.rfind("! ", 0, 250))
                        summary = summary[:cut+1] if cut > 50 else summary[:250] + "..."

                    # Label from filename
                    label = dc["title"]
                    if dc.get("markdown_path"):
                        label = dc["markdown_path"].replace("\\", "/").split("/")[-1].replace(".md", "").replace(".txt", "")[:60]

                    points.append({
                        "doc_id": did,
                        "x": round(positions[i][0], 4),
                        "y": round(positions[i][1], 4),
                        "z": 0,
                        "label": label,
                        "cluster": doc_to_cluster.get(did, 0),
                        "summary": summary,
                    })
                return PointCloudData(points=points, dimensions=dimensions, method="keyword-similarity")
            return PointCloudData(dimensions=dimensions, method=method)

        try:
            import numpy as np
        except ImportError:
            logger.warning("[KBAnalytics] numpy not available")
            return PointCloudData(dimensions=dimensions, method=method)

        X = np.array(d_embeddings)

        if method == "pca":
            projected = self._pca_project(X, dimensions)
        elif method == "tsne":
            projected = self._tsne_project(X, dimensions)
        elif method == "umap":
            projected = self._umap_project(X, dimensions)
        else:
            projected = self._pca_project(X, dimensions)

        points = []
        for i in range(len(d_ids)):
            point = {
                "doc_id": d_ids[i],
                "x": float(projected[i][0]),
                "y": float(projected[i][1]) if projected.shape[1] > 1 else 0,
                "z": float(projected[i][2]) if projected.shape[1] > 2 else 0,
                "label": d_titles[i][:100] if i < len(d_titles) else "",
                "cluster": int(cluster_labels[i]) if cluster_labels and i < len(cluster_labels) else 0,
            }
            points.append(point)

        return PointCloudData(points=points, dimensions=dimensions, method=method)

    def _pca_project(self, X, dimensions):
        """Principal Component Analysis projection.

        Parameters
        ----------
        X : ndarray
            Input embedding matrix.
        dimensions : int
            Target dimensions.

        Returns
        -------
        ndarray
            Projected coordinates.
        """
        import numpy as np

        X_centered = X - X.mean(axis=0)
        cov = np.cov(X_centered, rowvar=False)

        if cov.ndim == 0:
            cov = np.array([[cov]])

        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        idx = np.argsort(eigenvalues)[::-1]
        eigenvectors = eigenvectors[:, idx]

        components = eigenvectors[:, :dimensions]
        return X_centered @ components

    def _tsne_project(self, X, dimensions):
        """t-SNE projection (requires sklearn).

        Falls back to PCA if sklearn is not available.
        """
        try:
            from sklearn.manifold import TSNE

            perplexity = min(30, max(5, len(X) - 1))
            tsne = TSNE(n_components=dimensions, perplexity=perplexity, random_state=42)
            return tsne.fit_transform(X)
        except ImportError:
            logger.warning("[KBAnalytics] sklearn not available for t-SNE, using PCA")
            return self._pca_project(X, dimensions)

    def _umap_project(self, X, dimensions):
        """UMAP projection (requires umap-learn).

        Falls back to PCA if umap-learn is not available.
        """
        try:
            import umap

            n_neighbors = min(15, len(X) - 1)
            reducer = umap.UMAP(n_components=dimensions, n_neighbors=n_neighbors, random_state=42)
            return reducer.fit_transform(X)
        except ImportError:
            logger.warning("[KBAnalytics] umap-learn not available, using PCA")
            return self._pca_project(X, dimensions)

    # =========================================================================
    # Opinion Clustering
    # =========================================================================

    def get_opinion_clusters(
        self,
        internal_name: str,
        topic: str = "",
        max_clusters: int = 5,
        use_llm: bool = True,
        doc_ids: Optional[List[str]] = None,
    ) -> List[OpinionCluster]:
        """Cluster documents by viewpoint/opinion on a given topic.

        Uses LLM to analyze document content and group by stance.

        Parameters
        ----------
        internal_name : str
            KB internal name.
        topic : str
            Topic to analyze opinions on. If empty, uses general themes.
        max_clusters : int
            Maximum number of opinion clusters.
        use_llm : bool
            Whether to use LLM for stance analysis.
        doc_ids : List[str] or None
            If provided, only analyze these documents.

        Returns
        -------
        List[OpinionCluster]
            Discovered opinion clusters.
        """
        doc_contents = self._get_doc_contents(internal_name, doc_ids_filter=doc_ids)

        if not doc_contents:
            return []

        if use_llm and self.ollama.is_available():
            return self._llm_opinion_clustering(doc_contents, topic, max_clusters)
        else:
            return self._heuristic_opinion_clustering(doc_contents, topic, max_clusters)

    def _llm_opinion_clustering(
        self,
        doc_contents: List[Dict],
        topic: str,
        max_clusters: int,
    ) -> List[OpinionCluster]:
        """Use LLM to analyze and cluster documents by opinion.

        Parameters
        ----------
        doc_contents : List[Dict]
            Document contents with doc_id, title, content.
        topic : str
            Topic for opinion analysis.
        max_clusters : int
            Maximum clusters.

        Returns
        -------
        List[OpinionCluster]
            Opinion clusters identified by LLM.
        """
        from gangdan.core.config import CONFIG

        topic_prompt = f" on the topic of '{topic}'" if topic else ""

        doc_summaries = []
        for i, doc in enumerate(doc_contents[:20]):
            preview = doc["content"][:500].replace("\n", " ")
            doc_summaries.append(
                f"[{i+1}] {doc['title']} (ID: {doc['doc_id']}): {preview}"
            )

        prompt = (
            f"Analyze the following documents{topic_prompt} and identify distinct viewpoints/opinions expressed.\n"
            f"Group documents that share similar stances.\n\n"
            f"Documents:\n" + "\n\n".join(doc_summaries) + "\n\n"
            f"Respond with a JSON array of opinion clusters. Each cluster should have:\n"
            f'- "stance": a short description of the viewpoint (e.g., "supports X", "opposes Y")\n'
            f'- "doc_indices": list of document numbers (1-based) that express this view\n'
            f'- "summary": a brief summary of this opinion cluster\n'
            f'- "confidence": a number 0-1 indicating how cohesive this cluster is\n\n'
            f"Return ONLY the JSON array, no other text. Maximum {max_clusters} clusters."
        )

        try:
            response = self.ollama.chat_complete(
                messages=[{"role": "user", "content": prompt}],
                model=CONFIG.chat_model,
                temperature=0.3,
            )

            clusters_data = self._parse_json_from_response(response)
            if not isinstance(clusters_data, list):
                return self._heuristic_opinion_clustering(doc_contents, topic, max_clusters)

            opinion_clusters = []
            all_assigned = set()

            for i, cluster_data in enumerate(clusters_data[:max_clusters]):
                stance = cluster_data.get("stance", "")
                doc_indices = cluster_data.get("doc_indices", [])
                summary = cluster_data.get("summary", "")
                confidence = cluster_data.get("confidence", 0.5)

                c_doc_ids = []
                for idx in doc_indices:
                    if 1 <= idx <= len(doc_contents):
                        did = doc_contents[idx - 1]["doc_id"]
                        if did not in all_assigned:
                            c_doc_ids.append(did)
                            all_assigned.add(did)

                if c_doc_ids:
                    opinion_clusters.append(
                        OpinionCluster(
                            opinion_id=i + 1,
                            stance=stance,
                            doc_ids=c_doc_ids,
                            confidence=float(confidence),
                            summary=summary,
                        )
                    )

            for doc in doc_contents:
                if doc["doc_id"] not in all_assigned:
                    if opinion_clusters:
                        opinion_clusters[0].doc_ids.append(doc["doc_id"])
                    else:
                        opinion_clusters.append(
                            OpinionCluster(
                                opinion_id=1,
                                stance="uncategorized",
                                doc_ids=[doc["doc_id"]],
                                confidence=0.0,
                                summary="Could not determine stance",
                            )
                        )

            return opinion_clusters

        except Exception as e:
            logger.error("[KBAnalytics] LLM opinion clustering failed: %s", e)
            return self._heuristic_opinion_clustering(doc_contents, topic, max_clusters)

    def _heuristic_opinion_clustering(
        self,
        doc_contents: List[Dict],
        topic: str,
        max_clusters: int,
    ) -> List[OpinionCluster]:
        """Heuristic opinion clustering based on keyword overlap.

        Groups documents by shared keywords in their titles/content.
        Much more useful than sentiment-based grouping for academic papers.

        Parameters
        ----------
        doc_contents : List[Dict]
            Document contents.
        topic : str
            Topic for analysis.
        max_clusters : int
            Maximum clusters.

        Returns
        -------
        List[OpinionCluster]
            Heuristic opinion clusters.
        """
        import re
        from collections import Counter

        # Extract significant words from each document
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
            "this", "that", "it", "its", "we", "they", "he", "she", "as", "if",
            "not", "no", "can", "may", "will", "would", "could", "should",
            "has", "have", "had", "do", "does", "did", "been", "being",
            "more", "most", "some", "any", "all", "each", "both", "such",
            "than", "then", "also", "just", "now", "only", "very", "so",
            "into", "over", "under", "about", "above", "after", "before",
            "between", "through", "during", "while", "since", "until",
            "using", "based", "based", "approach", "method", "study",
            "model", "system", "network", "learning", "deep", "paper",
        }

        doc_words = []
        for doc in doc_contents:
            text = (doc["title"] + " " + doc["content"][:500]).lower()
            words = set(re.findall(r"\b[a-z]{3,}\b", text)) - stop_words
            doc_words.append(words)

        n = len(doc_contents)
        if n == 0:
            return []

        # Greedy clustering by word overlap
        doc_indices = list(range(n))
        clusters = []

        for _ in range(min(max_clusters, n)):
            if not doc_indices:
                break
            # Pick the first unassigned doc as seed
            seed = doc_indices.pop(0)
            cluster = [seed]
            seed_words = doc_words[seed]

            # Find docs that share at least 1 significant word with seed
            remaining = []
            for idx in doc_indices:
                overlap = len(doc_words[idx] & seed_words)
                if overlap >= 1:
                    cluster.append(idx)
                    # Merge words into seed for transitive grouping
                    seed_words |= doc_words[idx]
                else:
                    remaining.append(idx)
            doc_indices = remaining

            if cluster:
                # Find top keywords for this cluster
                all_ws = []
                for idx in cluster:
                    title_words = re.findall(r"\b[a-z]{3,}\b", doc_contents[idx]["title"].lower())
                    all_ws.extend(w for w in title_words if w not in stop_words)
                top_kw = [w for w, _ in Counter(all_ws).most_common(5)]

                cluster_doc_ids = [doc_contents[idx]["doc_id"] for idx in cluster]
                clusters.append(
                    OpinionCluster(
                        opinion_id=len(clusters) + 1,
                        stance="Topic: " + ", ".join(top_kw[:3]) if top_kw else "Topic Group " + str(len(clusters) + 1),
                        doc_ids=cluster_doc_ids,
                        confidence=0.6 if len(cluster) > 1 else 0.3,
                        summary=f"Documents sharing keywords: {', '.join(top_kw[:5])}" if top_kw else "Documents with related themes",
                    )
                )

        return clusters[:max_clusters]

    def _parse_json_from_response(self, response: str) -> Any:
        """Extract JSON from LLM response.

        Parameters
        ----------
        response : str
            LLM response text.

        Returns
        -------
        Any
            Parsed JSON object, or empty list on failure.
        """
        response = response.strip()

        if response.startswith("```"):
            lines = response.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            response = "\n".join(lines)

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            start = response.find("[")
            end = response.rfind("]")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(response[start:end + 1])
                except json.JSONDecodeError:
                    pass
        return []

    # =========================================================================
    # Strict Citation
    # =========================================================================

    def generate_cited_response(
        self,
        query: str,
        required_doc_ids: List[str],
        kb_name: str,
        additional_context: str = "",
    ) -> Dict[str, Any]:
        """Generate a response that strictly cites specified articles.

        The LLM is instructed to base its answer ONLY on the provided documents
        and to cite each required article.

        Parameters
        ----------
        query : str
            User's question.
        required_doc_ids : List[str]
            Document IDs that MUST be cited in the response.
        kb_name : str
            KB internal name.
        additional_context : str
            Extra context to include.

        Returns
        -------
        Dict[str, Any]
            {"response": str, "citations": [...], "missing_citations": [...]}
        """
        from gangdan.core.config import CONFIG

        docs = self.kb_manager.get_documents(kb_name)
        doc_map = {d.doc_id: d for d in docs}

        context_parts = []
        citation_map = {}
        missing = []
        idx = 1

        for doc_id in required_doc_ids:
            doc = doc_map.get(doc_id)
            if doc is None:
                missing.append(doc_id)
                continue

            content = ""
            if doc.markdown_path:
                from pathlib import Path
                md_path = Path(doc.markdown_path)
                if md_path.exists():
                    content = md_path.read_text(encoding="utf-8")[:3000]
            if not content:
                content = doc.content_preview

            citation_map[idx] = {
                "doc_id": doc_id,
                "title": doc.title,
                "url": doc.url,
                "authors": doc.authors,
                "published_date": doc.published_date,
                "filename": Path(doc.markdown_path).name.replace(".md", "").replace(".txt", "") if doc.markdown_path else doc.title,
            }
            # Use filename (with author/year) for display
            doc_label = Path(doc.markdown_path).name if doc.markdown_path else doc.title
            context_parts.append(
                f"[{idx}] {doc_label}\n"
                f" Content: {content}\n"
            )
            idx += 1

        if not context_parts:
            return {
                "response": "No specified documents found in the knowledge base.",
                "citations": [],
                "missing_citations": required_doc_ids,
            }

        context = "\n".join(context_parts)
        if additional_context:
            context += f"\nAdditional context:\n{additional_context}\n"

        citation_list = ", ".join(
            f"[{i}] {c['title']}" for i, c in citation_map.items()
        )

        prompt = (
            f"You are answering the following question based STRICTLY on the provided documents.\n\n"
            f"Question: {query}\n\n"
            f"Reference documents:\n{context}\n"
            f"You MUST cite the following documents in your response: {citation_list}\n\n"
            f"Rules:\n"
            f"1. Base your answer ONLY on the provided documents.\n"
            f"2. Cite each required document using [N] format where N is the document number.\n"
            f"3. If a document does not contain relevant information for a part of the answer, say so.\n"
            f"4. Do NOT make up information not present in the documents.\n"
            f"5. If the documents cannot answer the question, state that clearly.\n\n"
            f"Answer:"
        )

        try:
            response = self.ollama.chat_complete(
                messages=[{"role": "user", "content": prompt}],
                model=CONFIG.chat_model,
                temperature=0.3,
            )

            return {
                "response": response,
                "citations": list(citation_map.values()),
                "missing_citations": missing,
            }
        except Exception as e:
            logger.error("[KBAnalytics] Cited response generation failed: %s", e)
            return {
                "response": f"Error generating response: {e}",
                "citations": list(citation_map.values()),
                "missing_citations": missing,
            }

    # =========================================================================
    # Literature Review / Writing
    # =========================================================================

    def generate_review(
        self,
        kb_name: str,
        doc_ids: List[str],
        topic: str = "",
        style: str = "academic",
        language: str = "",
        mode: str = "review",
    ) -> Dict[str, Any]:
        """Generate a literature review or academic paper from selected documents.

        Parameters
        ----------
        kb_name : str
            KB internal name.
        doc_ids : List[str]
            Document IDs to include.
        topic : str
            Topic or title.
        style : str
            Writing style.
        language : str
            Output language.
        mode : str
            "review" or "paper".

        Returns
        -------
        Dict[str, Any]
            {"review": str, "citations": [...], "missing_citations": [...], "doc_count": int}
        """
        from gangdan.core.config import CONFIG

        doc_contents = self._get_doc_contents(kb_name, doc_ids_filter=doc_ids, max_content_length=3000)

        if not doc_contents:
            return {
                "review": "",
                "citations": [],
                "missing_citations": doc_ids,
                "doc_count": 0,
            }

        found_ids = {d["doc_id"] for d in doc_contents}
        missing = [did for did in doc_ids if did not in found_ids]

        # Extract year from filename or published_date, sort by year
        import re
        def extract_year(doc):
            # Try published_date first
            date = doc.get("published_date", "")
            year_match = re.search(r"(\d{4})", str(date))
            if year_match:
                return int(year_match.group(1))
            # Try filename
            path = doc.get("markdown_path", "")
            fname = path.replace("\\", "/").split("/")[-1]
            year_match = re.search(r"\((\d{4})\)", fname)
            if year_match:
                return int(year_match.group(1))
            year_match = re.search(r"(\d{4})", fname)
            if year_match:
                return int(year_match.group(1))
            return 0

        # Sort documents by year for chronological presentation
        doc_contents.sort(key=extract_year)

        doc_sections = []
        citation_map = {}
        for i, doc in enumerate(doc_contents):
            idx = i + 1
            citation_map[idx] = {
                "doc_id": doc["doc_id"],
                "title": doc["title"],
                "filename": header,  # Full filename with author/year
            }
            preview = doc["content"][:2000].replace("\n", " ")
            # Use filename (contains author/year) for display
            path = doc.get("markdown_path", "")
            fname = path.replace("\\", "/").split("/")[-1] if path else doc["title"]
            date = doc.get("published_date", "")
            year = extract_year(doc)
            year_str = f" ({year})" if year else ""
            author_str = ", ".join(doc.get("authors", [])[:3]) if doc.get("authors") else ""
            header = fname
            if not author_str and not year_str:
                header = doc["title"]
            doc_sections.append(
                f"[{idx}] {header}\n{preview}"
            )

        all_docs_text = "\n\n".join(doc_sections)

        lang_instruction = ""
        if language:
            lang_instruction = f"\nWrite in {language}."

        style_instructions = {
            "academic": "Use formal academic language and structure.",
            "technical": "Use precise technical terminology.",
            "general": "Use clear, accessible language.",
        }
        style_instruction = style_instructions.get(style, style_instructions["academic"])

        topic_line = f" on: {topic}" if topic else ""

        if mode == "paper":
            structure_instruction = (
                f"Structure the paper as follows:\n"
                f"1. Abstract: Brief summary of the paper.\n"
                f"2. Introduction: Background and motivation.\n"
                f"3. Main Body: Detailed analysis organized by themes.\n"
                f"4. Conclusion: Summary and future work.\n"
            )
            task_name = "academic paper"
        else:
            structure_instruction = (
                f"Structure the review as follows:\n"
                f"1. Introduction: Overview of the topic.\n"
                f"2. Thematic Analysis: Group findings by themes.\n"
                f"3. Conclusion: Summary of insights.\n"
            )
            task_name = "literature review"

        prompt = (
            f"You are writing a {task_name}{topic_line} based STRICTLY on the following documents.\n\n"
            f"The documents are sorted by publication year. Use this chronological order to show how ideas evolved over time.\n\n"
            f"{style_instruction}\n"
            f"{structure_instruction}\n"
            f"{lang_instruction}\n\n"
            f"CRITICAL REQUIREMENTS:\n"
            f"1. You MUST use EVERY single document provided. Do not skip any.\n"
            f"2. Cite each document using [N] format where N is the document number.\n"
            f"3. Ensure every document [1] to [{len(doc_contents)}] is cited at least once.\n"
            f"4. When discussing themes, organize by chronological order - show how earlier work influenced later work.\n"
            f"5. The document filenames contain author and year information - use these in your citations.\n"
            f"6. Do NOT use outside information or make up facts.\n"
            f"7. Synthesize information across documents.\n\n"
            f"Documents:\n{all_docs_text}\n\n"
            f"{task_name.capitalize()}:"
        )

        try:
            response = self.ollama.chat_complete(
                messages=[{"role": "user", "content": prompt}],
                model=CONFIG.chat_model,
                temperature=0.4,
            )

            return {
                "review": response,
                "citations": list(citation_map.values()),
                "missing_citations": missing,
                "doc_count": len(doc_contents),
            }
        except Exception as e:
            logger.error("[KBAnalytics] Review generation failed: %s", e)
            return {
                "review": f"Error generating review: {e}",
                "citations": list(citation_map.values()),
                "missing_citations": missing,
                "doc_count": len(doc_contents),
            }

    # =========================================================================
    # Document Content
    # =========================================================================

    def get_document_content(
        self,
        internal_name: str,
        doc_id: str,
        max_length: int = 5000,
    ) -> Optional[Dict[str, Any]]:
        """Get full content of a specific document in the KB.

        Parameters
        ----------
        internal_name : str
            KB internal name.
        doc_id : str
            Document ID.
        max_length : int
            Maximum content length to return.

        Returns
        -------
        Dict or None
            Document metadata and content, or None if not found.
        """
        docs = self.kb_manager.get_documents(internal_name)

        for doc in docs:
            if doc.doc_id == doc_id:
                content = ""
                if doc.markdown_path:
                    from pathlib import Path
                    md_path = Path(doc.markdown_path)
                    if md_path.exists():
                        content = md_path.read_text(encoding="utf-8")[:max_length]
                if not content:
                    content = doc.content_preview

                return {
                    "doc_id": doc.doc_id,
                    "title": doc.title,
                    "content": content,
                    "source_type": doc.source_type,
                    "source_id": doc.source_id,
                    "authors": doc.authors,
                    "published_date": doc.published_date,
                    "url": doc.url,
                    "tags": doc.tags,
                }

        return None
