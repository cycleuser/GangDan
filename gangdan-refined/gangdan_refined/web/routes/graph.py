"""Knowledge graph API routes for GangDan Refined."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from flask import Blueprint, jsonify, request

from ...core.config import DATA_DIR
from ...storage.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)

graph_bp = Blueprint("graph_store", __name__, url_prefix="/api/graph")

_kg = None

def get_kg():
    global _kg
    if _kg is None:
        _kg = KnowledgeGraph(DATA_DIR / "knowledge_graph" / "graph.json")
    return _kg


ENTITY_EXTRACTION_PROMPT = """Extract entities and their relationships from the following text.
Identify entities of these types: person, organization, concept, technology, event, location, method, dataset.
For each entity, provide name and type. For each relationship, provide source, target, relation.
Return JSON: {"entities": [{"name": "...", "type": "..."}], "relationships": [{"source": "...", "target": "...", "relation": "..."}]}
Text: {text}
Return ONLY the JSON object."""


@graph_bp.route("/data")
def api_graph_data():
    return jsonify(get_kg().get_graph_data())

@graph_bp.route("/search")
def api_graph_search():
    q = request.args.get("q", "")
    etype = request.args.get("type") or None
    limit = min(int(request.args.get("limit", 20)), 100)
    if not q: return jsonify([])
    return jsonify(get_kg().search_nodes(q, entity_type=etype, limit=limit))

@graph_bp.route("/neighbors/<node_id>")
def api_graph_neighbors(node_id):
    depth = min(int(request.args.get("depth", 1)), 3)
    direction = request.args.get("direction", "both")
    r = get_kg().get_neighbors(node_id, max_depth=depth, direction=direction)
    if not r.get("center"): return jsonify({"error": "Not found"}), 404
    return jsonify(r)

@graph_bp.route("/subgraph", methods=["POST"])
def api_graph_subgraph():
    data = request.get_json(silent=True) or {}
    return jsonify(get_kg().export_subgraph(data.get("node_ids", [])))

@graph_bp.route("/communities")
def api_graph_communities():
    return jsonify(get_kg().detect_communities())

@graph_bp.route("/stats")
def api_graph_stats():
    kg = get_kg()
    tc = {}
    for n in kg.nodes.values():
        t = n.get("type", "unknown")
        tc[t] = tc.get(t, 0) + 1
    return jsonify({"total_nodes": kg.node_count, "total_edges": kg.edge_count, "entity_types": tc})

@graph_bp.route("/extract", methods=["POST"])
def api_graph_extract():
    data = request.get_json(silent=True) or {}
    chunks = data.get("chunks", [])
    if not chunks: return jsonify({"error": "No chunks"}), 400

    from ...llm.ollama import OllamaClient
    from ...core.config import CONFIG

    kg = get_kg()
    ollama = OllamaClient(CONFIG.llm.ollama_url)
    total_e = total_r = 0

    for chunk in chunks[:20]:
        if len(chunk.strip()) < 50: continue
        try:
            msgs = [{"role": "user", "content": ENTITY_EXTRACTION_PROMPT.format(text=chunk[:3000])}]
            resp = ollama.chat_complete(msgs, CONFIG.llm.chat_model, temperature=0.1)
            result = _parse_json(resp)
            if not result: continue
            for ent in result.get("entities", []):
                name = ent.get("name", "").strip()
                etype = ent.get("type", "concept")
                if name:
                    kg.add_node(name, name, etype)
                    total_e += 1
            for rel in result.get("relationships", []):
                s, t = rel.get("source", "").strip(), rel.get("target", "").strip()
                if s and t:
                    kg.add_edge(s, t, rel.get("relation", "related_to"))
                    total_r += 1
        except Exception as e:
            logger.warning("KG extract error: %s", e)
    return jsonify({"entities_added": total_e, "relationships_added": total_r, "total_nodes": kg.node_count, "total_edges": kg.edge_count})

@graph_bp.route("/clear", methods=["POST"])
def api_graph_clear():
    get_kg().clear()
    return jsonify({"status": "cleared"})

def _parse_json(text):
    if not text: return None
    try: return json.loads(text)
    except: pass
    m = re.search(r'\{[\s\S]*"entities"[\s\S]*"relationships"[\s\S]*\}', text)
    if m:
        try: return json.loads(m.group())
        except: pass
    return None
