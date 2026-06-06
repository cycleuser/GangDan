"""Lightweight knowledge graph engine with JSON persistence.

Builds entity-relationship graphs from document chunks extracted by LLM.
Supports node/edge CRUD, entity search, neighbor expansion, subgraph export,
and community detection via label propagation.

No external dependencies beyond Python stdlib.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class KnowledgeGraph:
    """In-memory knowledge graph with JSON file persistence.

    Nodes represent entities (person, organization, concept, technology,
    event, location). Edges represent directed relationships between entities.

    Attributes
    ----------
    graph_path : Path
        Path to the JSON persistence file.
    nodes : Dict[str, Dict[str, Any]]
        Node storage keyed by node ID.
    edges : List[Dict[str, Any]]
        List of edge dicts (source, target, relation, weight).
    _adj_out : Dict[str, List[Tuple[str, str, float]]]
        Adjacency list: source -> [(target, relation, weight), ...]
    _adj_in : Dict[str, List[Tuple[str, str, float]]]
        Reverse adjacency: target -> [(source, relation, weight), ...]
    """

    # Entity types recognized by the graph
    ENTITY_TYPES = ["person", "organization", "concept", "technology", "event", "location", "method", "dataset"]

    # Default colors for visualization
    TYPE_COLORS = {
        "person": "#f97316",
        "organization": "#3b82f6",
        "location": "#22c55e",
        "technology": "#a855f7",
        "concept": "#eab308",
        "event": "#ef4444",
        "method": "#06b6d4",
        "dataset": "#ec4899",
    }

    def __init__(self, graph_path: str | Path) -> None:
        """Initialize knowledge graph.

        Parameters
        ----------
        graph_path : str or Path
            Path to the JSON persistence file.
        """
        self.graph_path = Path(graph_path)
        self.graph_path.parent.mkdir(parents=True, exist_ok=True)
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Dict[str, Any]] = []
        self._adj_out: Dict[str, List[Tuple[str, str, float]]] = defaultdict(list)
        self._adj_in: Dict[str, List[Tuple[str, str, float]]] = defaultdict(list)
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load graph from JSON file."""
        if self.graph_path.exists():
            try:
                data = json.loads(self.graph_path.read_text(encoding="utf-8"))
                self.nodes = data.get("nodes", {})
                self.edges = data.get("edges", [])
                self._rebuild_adjacency()
                logger.info("KG: loaded %d nodes, %d edges", len(self.nodes), len(self.edges))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("KG: failed to load graph: %s", e)

    def save(self) -> None:
        """Persist graph to JSON file."""
        data = {"nodes": self.nodes, "edges": self.edges}
        self.graph_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _rebuild_adjacency(self) -> None:
        """Rebuild adjacency lists from edges."""
        self._adj_out.clear()
        self._adj_in.clear()
        for edge in self.edges:
            src = edge["source"]
            tgt = edge["target"]
            rel = edge.get("relation", "related_to")
            w = edge.get("weight", 1.0)
            self._adj_out[src].append((tgt, rel, w))
            self._adj_in[tgt].append((src, rel, w))

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    def add_node(
        self,
        node_id: str,
        name: str,
        entity_type: str = "concept",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Add or update a node.

        Parameters
        ----------
        node_id : str
            Unique node identifier (will be normalized).
        name : str
            Display name for the entity.
        entity_type : str
            Entity type (one of ENTITY_TYPES).
        metadata : dict, optional
            Additional metadata (e.g. source document, chunk_id).

        Returns
        -------
        str
            The normalized node ID.
        """
        node_id = self._normalize_id(node_id)
        meta = metadata or {}

        if node_id in self.nodes:
            # Merge metadata
            existing = self.nodes[node_id]
            existing["name"] = name
            existing["type"] = entity_type
            existing.setdefault("metadata", {}).update(meta)
            existing["metadata"]["doc_count"] = existing["metadata"].get("doc_count", 0) + 1
        else:
            self.nodes[node_id] = {
                "id": node_id,
                "name": name,
                "type": entity_type,
                "metadata": meta,
            }

        self.save()
        return node_id

    def remove_node(self, node_id: str) -> bool:
        """Remove a node and all its incident edges.

        Parameters
        ----------
        node_id : str
            Node ID to remove.

        Returns
        -------
        bool
            True if node existed and was removed.
        """
        node_id = self._normalize_id(node_id)
        if node_id not in self.nodes:
            return False

        del self.nodes[node_id]
        self.edges = [
            e for e in self.edges
            if e["source"] != node_id and e["target"] != node_id
        ]
        self._rebuild_adjacency()
        self.save()
        return True

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get a node by ID.

        Parameters
        ----------
        node_id : str
            Node identifier.

        Returns
        -------
        dict or None
            Node data, or None if not found.
        """
        return self.nodes.get(self._normalize_id(node_id))

    # ------------------------------------------------------------------
    # Edge operations
    # ------------------------------------------------------------------

    def add_edge(
        self,
        source: str,
        target: str,
        relation: str = "related_to",
        weight: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add a directed edge between two nodes.

        Automatically creates nodes if they don't exist.

        Parameters
        ----------
        source : str
            Source entity name/ID.
        target : str
            Target entity name/ID.
        relation : str
            Relationship type (e.g. "uses", "part_of", "cited_by").
        weight : float
            Edge weight (default 1.0, higher = stronger).
        metadata : dict, optional
            Additional edge metadata.
        """
        src_id = self._normalize_id(source)
        tgt_id = self._normalize_id(target)

        # Ensure nodes exist
        if src_id not in self.nodes:
            self.nodes[src_id] = {
                "id": src_id, "name": source, "type": "concept", "metadata": {}
            }
        if tgt_id not in self.nodes:
            self.nodes[tgt_id] = {
                "id": tgt_id, "name": target, "type": "concept", "metadata": {}
            }

        # Check for duplicate
        for e in self.edges:
            if e["source"] == src_id and e["target"] == tgt_id and e.get("relation") == relation:
                e["weight"] = e.get("weight", 1.0) + weight
                self._rebuild_adjacency()
                self.save()
                return

        edge = {
            "source": src_id,
            "target": tgt_id,
            "relation": relation,
            "weight": weight,
        }
        if metadata:
            edge["metadata"] = metadata

        self.edges.append(edge)
        self._adj_out[src_id].append((tgt_id, relation, weight))
        self._adj_in[tgt_id].append((src_id, relation, weight))
        self.save()

    def remove_edge(self, source: str, target: str, relation: Optional[str] = None) -> int:
        """Remove edges matching source, target, and optional relation.

        Parameters
        ----------
        source : str
            Source entity ID.
        target : str
            Target entity ID.
        relation : str, optional
            Specific relation to remove. If None, removes all relations.

        Returns
        -------
        int
            Number of edges removed.
        """
        src_id = self._normalize_id(source)
        tgt_id = self._normalize_id(target)
        count = 0
        new_edges = []
        for e in self.edges:
            if e["source"] == src_id and e["target"] == tgt_id:
                if relation is None or e.get("relation") == relation:
                    count += 1
                    continue
            new_edges.append(e)
        if count > 0:
            self.edges = new_edges
            self._rebuild_adjacency()
            self.save()
        return count

    # ------------------------------------------------------------------
    # Query / retrieval
    # ------------------------------------------------------------------

    def search_nodes(
        self,
        query: str,
        entity_type: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search nodes by name or type.

        Parameters
        ----------
        query : str
            Substring to match against node names.
        entity_type : str, optional
            Filter by entity type.
        limit : int
            Maximum results.

        Returns
        -------
        List[Dict[str, Any]]
            Matching nodes with their degree (connection count).
        """
        q = query.lower()
        results = []
        for node_id, node in self.nodes.items():
            if entity_type and node.get("type") != entity_type:
                continue
            if q in node["name"].lower() or q in node_id.lower():
                node_copy = dict(node)
                node_copy["degree"] = len(self._adj_out.get(node_id, [])) + len(self._adj_in.get(node_id, []))
                results.append(node_copy)
            if len(results) >= limit:
                break
        return results

    def get_neighbors(
        self,
        node_id: str,
        max_depth: int = 1,
        direction: str = "both",
    ) -> Dict[str, Any]:
        """Get the neighborhood around a node.

        Parameters
        ----------
        node_id : str
            Center node ID.
        max_depth : int
            How many hops to expand (default 1).
        direction : str
            "out", "in", or "both" (default).

        Returns
        -------
        dict
            With keys: center (node dict), nodes (list), edges (list).
        """
        node_id = self._normalize_id(node_id)
        center = self.nodes.get(node_id)
        if not center:
            return {"center": None, "nodes": [], "edges": []}

        visited: Set[str] = {node_id}
        nodes_found: Dict[str, Dict[str, Any]] = {node_id: dict(center)}
        edges_found: List[Dict[str, Any]] = []

        frontier = {node_id}
        for _ in range(max_depth):
            next_frontier: Set[str] = set()
            for nid in frontier:
                neighbors: List[Tuple[str, str, float]] = []
                if direction in ("out", "both"):
                    neighbors.extend(self._adj_out.get(nid, []))
                if direction in ("in", "both"):
                    neighbors.extend(self._adj_in.get(nid, []))

                for neighbor_id, rel, w in neighbors:
                    edge = {"source": nid, "target": neighbor_id, "relation": rel, "weight": w}
                    edges_found.append(edge)
                    if neighbor_id not in visited:
                        visited.add(neighbor_id)
                        next_frontier.add(neighbor_id)
                        if neighbor_id in self.nodes:
                            nodes_found[neighbor_id] = dict(self.nodes[neighbor_id])

            frontier = next_frontier

        return {
            "center": dict(center),
            "nodes": list(nodes_found.values()),
            "edges": edges_found,
        }

    def export_subgraph(self, node_ids: List[str]) -> Dict[str, Any]:
        """Export a subgraph containing only the specified nodes and edges between them.

        Parameters
        ----------
        node_ids : List[str]
            Node IDs to include.

        Returns
        -------
        dict
            With keys: nodes (list), edges (list).
        """
        id_set = {self._normalize_id(n) for n in node_ids}
        sub_nodes = [dict(self.nodes[nid]) for nid in id_set if nid in self.nodes]
        sub_edges = [
            dict(e) for e in self.edges
            if e["source"] in id_set and e["target"] in id_set
        ]
        return {"nodes": sub_nodes, "edges": sub_edges}

    def get_graph_data(self) -> Dict[str, Any]:
        """Export full graph data for visualization.

        Returns
        -------
        dict
            With keys: nodes (list), edges (list).
        """
        nodes_out = []
        for nid, node in self.nodes.items():
            n = dict(node)
            n["linkCount"] = len(self._adj_out.get(nid, [])) + len(self._adj_in.get(nid, []))
            nodes_out.append(n)

        edges_out = [dict(e) for e in self.edges]
        return {"nodes": nodes_out, "edges": edges_out}

    # ------------------------------------------------------------------
    # Community detection (label propagation)
    # ------------------------------------------------------------------

    def detect_communities(self, max_iterations: int = 50) -> Dict[str, Any]:
        """Detect communities using label propagation.

        Each node starts with its own community. In each iteration,
        a node adopts the most common community among its neighbors.

        Parameters
        ----------
        max_iterations : int
            Maximum iterations (default 50, usually converges in < 10).

        Returns
        -------
        dict
            With keys:
            - assignments (dict): node_id -> community_id
            - communities (list): [{id, node_count, cohesion, top_nodes}]
        """
        node_ids = list(self.nodes.keys())
        if not node_ids:
            return {"assignments": {}, "communities": []}

        # Initialize: each node gets its own community
        labels: Dict[str, int] = {nid: i for i, nid in enumerate(node_ids)}

        for iteration in range(max_iterations):
            changed = 0
            # Process in random-ish order (by sorted keys for determinism)
            for nid in sorted(node_ids):
                neighbor_labels: Dict[int, int] = defaultdict(int)
                neighbors = (
                    [t for t, _, _ in self._adj_out.get(nid, [])]
                    + [s for s, _, _ in self._adj_in.get(nid, [])]
                )
                for neighbor_id in neighbors:
                    if neighbor_id in labels:
                        neighbor_labels[labels[neighbor_id]] += 1

                if not neighbor_labels:
                    continue

                # Most frequent neighbor label
                best_label = max(neighbor_labels, key=lambda k: neighbor_labels[k])
                if labels[nid] != best_label:
                    labels[nid] = best_label
                    changed += 1

            if changed == 0:
                logger.info("KG: community detection converged after %d iterations", iteration + 1)
                break

        # Group nodes by community
        communities_map: Dict[int, List[str]] = defaultdict(list)
        for nid, comm_id in labels.items():
            communities_map[comm_id].append(nid)

        # Compute community stats
        communities = []
        for comm_id, members in communities_map.items():
            # Cohesion: ratio of internal edges to possible edges
            internal_edges = 0
            member_set = set(members)
            for e in self.edges:
                if e["source"] in member_set and e["target"] in member_set:
                    internal_edges += 1

            n = len(members)
            max_possible = n * (n - 1) if n > 1 else 1
            cohesion = internal_edges / max_possible if max_possible > 0 else 0.0

            # Top nodes by degree
            top = sorted(
                members,
                key=lambda nid: len(self._adj_out.get(nid, [])) + len(self._adj_in.get(nid, [])),
                reverse=True,
            )[:5]

            communities.append({
                "id": comm_id,
                "nodeCount": n,
                "cohesion": round(cohesion, 4),
                "topNodes": [self.nodes[nid]["name"] for nid in top if nid in self.nodes],
            })

        communities.sort(key=lambda c: c["nodeCount"], reverse=True)

        return {
            "assignments": {nid: int(labels[nid]) for nid in labels},
            "communities": communities,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_id(name: str) -> str:
        """Normalize an entity name into a graph node ID."""
        return name.strip().lower().replace(" ", "_").replace("-", "_")

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    def clear(self) -> None:
        """Clear all nodes and edges."""
        self.nodes.clear()
        self.edges.clear()
        self._adj_out.clear()
        self._adj_in.clear()
        self.save()
