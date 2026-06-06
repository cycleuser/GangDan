/**
 * Knowledge Graph visualization module.
 *
 * Renders an interactive entity-relation graph using vis-network (loaded from CDN).
 * Supports search, filtering by entity type, community detection, and entity extraction
 * from knowledge base documents.
 */
var GraphModule = (function() {
    'use strict';

    var _network = null;
    var _graphData = { nodes: [], edges: [] };
    var _communityAssignments = null;

    var TYPE_COLORS = {
        person: '#f97316', organization: '#3b82f6', location: '#22c55e',
        technology: '#a855f7', concept: '#eab308', event: '#ef4444',
        method: '#06b6d4', dataset: '#ec4899',
    };

    function loadVisLib(cb) {
        if (typeof vis !== 'undefined') { cb(); return; }
        var s = document.createElement('script');
        s.src = 'https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js';
        s.onload = cb;
        document.head.appendChild(s);
    }

    function loadGraph() {
        loadVisLib(function() { _fetchGraph(); });
    }

    function _fetchGraph() {
        setStatus('Loading graph...');
        fetch('/api/graph/data')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                _graphData = data;
                _render();
                setStatus('Graph loaded: ' + data.nodes.length + ' nodes, ' + data.edges.length + ' edges');
                var statsEl = document.getElementById('graphStats');
                if (statsEl) statsEl.textContent = data.nodes.length + ' nodes, ' + data.edges.length + ' edges';
            })
            .catch(function(e) {
                setStatus('Error loading graph: ' + e.message);
            });
    }

    function _render() {
        var nodes = new vis.DataSet();
        var edges = new vis.DataSet();
        var nodeMap = {};

        _graphData.nodes.forEach(function(n) {
            var color = TYPE_COLORS[n.type] || '#64748b';
            if (_communityAssignments && _communityAssignments[n.id] !== undefined) {
                var palette = ['#FF6B6B','#4ECDC4','#45B7D1','#96CEB4','#FFEAA7','#DDA0DD','#98D8C8','#F7DC6F'];
                color = palette[_communityAssignments[n.id] % palette.length];
            }
            var size = Math.max(12, Math.min(40, (n.linkCount || 1) * 3 + 10));
            nodes.add({
                id: n.id,
                label: n.name,
                color: { background: color, border: '#333' },
                font: { size: size > 20 ? 14 : 11 },
                size: size,
                title: n.type + ': ' + n.name + ' (' + (n.linkCount || 0) + ' links)',
            });
            nodeMap[n.id] = n;
        });

        _graphData.edges.forEach(function(e) {
            edges.add({
                from: e.source,
                to: e.target,
                label: e.relation,
                width: Math.max(1, e.weight || 1),
                arrows: 'to',
                title: (e.relation || '') + ' (weight: ' + (e.weight || 1) + ')',
            });
        });

        var container = document.getElementById('graphCanvas');
        if (!container) return;
        container.innerHTML = '';

        var options = {
            physics: { solver: 'forceAtlas2Based', forceAtlas2Based: { gravitationalConstant: -40, centralGravity: 0.01 } },
            interaction: { hover: true, tooltipDelay: 200 },
            edges: { smooth: { type: 'continuous' } },
        };

        _network = new vis.Network(container, { nodes: nodes, edges: edges }, options);

        _network.on('click', function(params) {
            if (params.nodes.length > 0) {
                _showNeighbors(params.nodes[0]);
            }
        });
    }

    function _showNeighbors(nodeId) {
        fetch('/api/graph/neighbors/' + encodeURIComponent(nodeId) + '?depth=1')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.center) {
                    var info = '📍 ' + data.center.name + ' (' + data.center.type + ') - ' + data.nodes.length + ' neighbors';
                    setStatus(info);
                }
            });
    }

    function search() {
        var q = document.getElementById('graphSearchInput').value.trim();
        var type = document.getElementById('graphTypeFilter').value;
        if (!q) { loadGraph(); return; }

        var url = '/api/graph/search?q=' + encodeURIComponent(q) + '&limit=30';
        if (type) url += '&type=' + encodeURIComponent(type);

        fetch(url)
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.length === 0) { setStatus('No nodes found'); return; }
                var ids = data.map(function(n) { return n.id; });
                fetch('/api/graph/subgraph', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ node_ids: ids }) })
                    .then(function(r) { return r.json(); })
                    .then(function(sg) {
                        _graphData = sg;
                        _render();
                        setStatus('Search: ' + sg.nodes.length + ' nodes for "' + q + '"');
                    });
            });
    }

    function applyFilter() {
        search();
    }

    function detectCommunities() {
        fetch('/api/graph/communities')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                _communityAssignments = data.assignments || {};
                _render();
                var infoEl = document.getElementById('graphCommunityInfo');
                var lines = ['<strong>Communities:</strong>'];
                (data.communities || []).slice(0, 5).forEach(function(c) {
                    lines.push('  C' + c.id + ': ' + c.nodeCount + ' nodes, cohesion=' + c.cohesion.toFixed(2) + ' [' + (c.topNodes || []).slice(0,3).join(', ') + ']');
                });
                if (infoEl) infoEl.innerHTML = lines.join('<br>');
                setStatus('Detected ' + data.communities.length + ' communities');
            });
    }

    function extractFromKb() {
        // Get selected KBs from the shared KB selection
        var kbs = [];
        try {
            if (typeof window._selectedKbs !== 'undefined' && window._selectedKbs) {
                kbs = Array.from(window._selectedKbs);
            }
        } catch(e) {}
        if (kbs.length === 0) {
            kbs = ['all'];
        }

        setStatus('Extracting entities from KB...');
        // Quick approach: use the selected KB names directly
        fetch('/api/kb/files', { method: 'GET' })
            .then(function(r) { return r.json(); })
            .then(function(files) {
                // Sample up to 10 files
                var sample = (files.files || files || []).slice(0, 10);
                var chunks = sample.map(function(f) { return (f.title || f.name || '') + ' ' + (f.snippet || '').substring(0, 500); });
                return fetch('/api/graph/extract', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ chunks: chunks, kb_id: kbs.join(',') }),
                });
            })
            .then(function(r) { return r.json(); })
            .then(function(result) {
                setStatus('Extracted: ' + (result.entities_added || 0) + ' entities, ' + (result.relationships_added || 0) + ' relations');
                loadGraph();
            })
            .catch(function(e) {
                setStatus('Extraction error: ' + e.message);
                // Fallback: just reload
                loadGraph();
            });
    }

    function clearGraph() {
        if (!confirm('Clear the entire knowledge graph?')) return;
        fetch('/api/graph/clear', { method: 'POST' })
            .then(function(r) { return r.json(); })
            .then(function() {
                _graphData = { nodes: [], edges: [] };
                _communityAssignments = null;
                _render();
                setStatus('Graph cleared');
            });
    }

    function setStatus(msg) {
        var el = document.getElementById('graphStats');
        if (el) el.textContent = msg;
    }

    // Auto-load when graph tab is shown
    document.addEventListener('DOMContentLoaded', function() {
        setTimeout(function() { loadGraph(); }, 500);
    });

    return {
        loadGraph: loadGraph,
        search: search,
        applyFilter: applyFilter,
        detectCommunities: detectCommunities,
        extractFromKb: extractFromKb,
        clearGraph: clearGraph,
    };
})();
