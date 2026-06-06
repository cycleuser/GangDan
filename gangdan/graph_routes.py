"""Knowledge graph API routes.

Provides RESTful endpoints for:
- Graph data retrieval (full graph, subgraph, neighborhood)
- Entity extraction from document chunks
- Community detection
- Graph search
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, request

from gangdan.core.config import DATA_DIR

logger = logging.getLogger(__name__)

graph_bp = Blueprint("graph", __name__, url_prefix="/api/graph")

# Singleton graph instance
_graph_instance = None


def get_graph():
    """Get or create the shared KnowledgeGraph instance."""
    global _graph_instance
    if _graph_instance is None:
        from gangdan.core.knowledge_graph import KnowledgeGraph

        graph_path = DATA_DIR / "knowledge_graph" / "graph.json"
        _graph_instance = KnowledgeGraph(graph_path)
    return _graph_instance


# ---------------------------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------------------------

ENTITY_EXTRACTION_PROMPT = """Extract entities and their relationships from the following text.

Identify entities of these types: person, organization, concept, technology, event, location, method, dataset.

For each entity, provide:
- name: the entity name
- type: one of the types above

For each relationship between two entities, provide:
- source: name of the source entity
- target: name of the target entity  
- relation: the relationship type (e.g., "uses", "based_on", "part_of", "founded_by", "cited_by", "applied_to", "introduced", "improves", "evaluates")

Return JSON:
{
  "entities": [{"name": "...", "type": "..."}, ...],
  "relationships": [{"source": "...", "target": "...", "relation": "..."}, ...]
}

Text:
{text}

Return ONLY the JSON object, no other text."""


@graph_bp.route("/extract", methods=["POST"])
def api_extract_entities():
    """Extract entities from text chunks and add to the knowledge graph.

    Request body:
        chunks: List[str] - text chunks to analyze
        kb_id: str (optional) - knowledge base identifier

    Returns:
        JSON with extracted entity and relationship counts.
    """
    data = request.get_json(silent=True) or {}
    chunks = data.get("chunks", [])
    kb_id = data.get("kb_id", "")

    if not chunks:
        return jsonify({"error": "No chunks provided"}), 400

    # Get LLM client
    from gangdan.app import get_chat_client, CONFIG
    client = get_chat_client()

    graph = get_graph()
    total_entities = 0
    total_relations = 0

    for chunk in chunks[:20]:  # Limit chunks for performance
        if len(chunk.strip()) < 50:
            continue

        try:
            prompt = ENTITY_EXTRACTION_PROMPT.format(text=chunk[:3000])
            messages = [{"role": "user", "content": prompt}]
            response = client.chat(messages, temperature=0.1, max_tokens=1024)

            # Parse JSON response
            result = _parse_entity_json(response)
            if not result:
                continue

            entities = result.get("entities", [])
            relationships = result.get("relationships", [])

            # Add entities to graph
            for ent in entities:
                name = ent.get("name", "").strip()
                etype = ent.get("type", "concept")
                if name and etype in KnowledgeGraph.ENTITY_TYPES:
                    metadata = {"source": kb_id} if kb_id else {}
                    graph.add_node(name, name, etype, metadata)
                    total_entities += 1

            # Add relationships
            for rel in relationships:
                src = rel.get("source", "").strip()
                tgt = rel.get("target", "").strip()
                relation = rel.get("relation", "related_to")
                if src and tgt:
                    metadata = {"source": kb_id} if kb_id else {}
                    graph.add_edge(src, tgt, relation, 1.0, metadata)
                    total_relations += 1

        except Exception as e:
            logger.warning("KG extract error: %s", e)
            continue

    return jsonify({
        "entities_added": total_entities,
        "relationships_added": total_relations,
        "total_nodes": graph.node_count,
        "total_edges": graph.edge_count,
    })


def _parse_entity_json(text: str) -> Optional[Dict[str, Any]]:
    """Parse LLM JSON response for entity extraction."""
    if not text:
        return None

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON block
    import re
    match = re.search(r'\{[\s\S]*"entities"[\s\S]*"relationships"[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


# ---------------------------------------------------------------------------
# Graph data endpoints
# ---------------------------------------------------------------------------

@graph_bp.route("/data", methods=["GET"])
def api_get_graph():
    """Get full graph data for visualization.

    Returns:
        JSON with nodes (list) and edges (list).
    """
    graph = get_graph()
    return jsonify(graph.get_graph_data())


@graph_bp.route("/search", methods=["GET"])
def api_search_nodes():
    """Search nodes by name.

    Query params:
        q: search query
        type: optional entity type filter
        limit: max results (default 20)

    Returns:
        JSON list of matching nodes.
    """
    query = request.args.get("q", "")
    entity_type = request.args.get("type")
    limit = min(int(request.args.get("limit", 20)), 100)

    if not query:
        return jsonify([])

    graph = get_graph()
    results = graph.search_nodes(query, entity_type=entity_type, limit=limit)
    return jsonify(results)


@graph_bp.route("/neighbors/<node_id>", methods=["GET"])
def api_get_neighbors(node_id: str):
    """Get neighborhood around a node.

    Query params:
        depth: max hops (default 1)
        direction: out, in, or both (default both)

    Returns:
        JSON with center node, neighbor nodes, and edges.
    """
    depth = min(int(request.args.get("depth", 1)), 3)
    direction = request.args.get("direction", "both")

    graph = get_graph()
    result = graph.get_neighbors(node_id, max_depth=depth, direction=direction)
    if result["center"] is None:
        return jsonify({"error": "Node not found"}), 404
    return jsonify(result)


@graph_bp.route("/subgraph", methods=["POST"])
def api_export_subgraph():
    """Export a subgraph containing only specified nodes.

    Request body:
        node_ids: List[str] - node IDs to include

    Returns:
        JSON with filtered nodes and edges.
    """
    data = request.get_json(silent=True) or {}
    node_ids = data.get("node_ids", [])

    if not node_ids:
        return jsonify({"nodes": [], "edges": []})

    graph = get_graph()
    result = graph.export_subgraph(node_ids)
    return jsonify(result)


@graph_bp.route("/communities", methods=["GET"])
def api_get_communities():
    """Detect communities using label propagation.

    Returns:
        JSON with community assignments and stats.
    """
    graph = get_graph()
    result = graph.detect_communities()
    return jsonify(result)


@graph_bp.route("/stats", methods=["GET"])
def api_get_stats():
    """Get graph statistics.

    Returns:
        JSON with node/edge counts and entity type breakdown.
    """
    graph = get_graph()

    type_counts: Dict[str, int] = {}
    for node in graph.nodes.values():
        t = node.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    return jsonify({
        "total_nodes": graph.node_count,
        "total_edges": graph.edge_count,
        "entity_types": type_counts,
    })


@graph_bp.route("/clear", methods=["POST"])
def api_clear_graph():
    """Clear the entire knowledge graph.

    Returns:
        JSON confirmation.
    """
    graph = get_graph()
    graph.clear()
    return jsonify({"status": "cleared", "nodes": 0, "edges": 0})


# Import at module level to avoid circular imports
from gangdan.core.knowledge_graph import KnowledgeGraph  # noqa: E402
