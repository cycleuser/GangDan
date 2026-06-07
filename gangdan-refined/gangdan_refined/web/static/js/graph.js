/* Knowledge Graph visualization using vis-network (CDN loaded on demand). */
var GraphModule = (function() {
  'use strict';
  var network = null, data = { nodes: [], edges: [] }, communities = null;
  var COLORS = { person:'#f97316', organization:'#3b82f6', location:'#22c55e', technology:'#a855f7', concept:'#eab308', event:'#ef4444', method:'#06b6d4', dataset:'#ec4899' };

  function status(msg) {
    var el = document.getElementById('graphStatus');
    if (el) el.textContent = msg;
  }

  function _loadVis(cb) {
    if (typeof vis !== 'undefined') { cb(); return; }
    status('Loading graph engine...');
    var s = document.createElement('script');
    s.src = 'https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js';
    s.onload = function() { cb(); };
    s.onerror = function() {
      status('Graph engine failed to load. Check internet connection.');
      document.getElementById('graph-canvas').innerHTML = '<div class="empty"><div class="icon">🕸️</div><h3>Graph Unavailable</h3><p>vis-network CDN failed to load. Check your internet connection.</p></div>';
    };
    document.head.appendChild(s);
  }

  function loadGraph() {
    _loadVis(function() {
      fetch('/api/graph/data').then(function(r){ return r.json(); }).then(function(d){
        data = d;
        render();
        status(data.nodes.length + ' nodes, ' + data.edges.length + ' edges');
      }).catch(function(e){ status('Error: '+e.message); });
    });
  }

  function render() {
    var container = document.getElementById('graph-canvas');
    if (!container || typeof vis === 'undefined') return;
    container.innerHTML = '';

    if (!data.nodes.length) {
      container.innerHTML = '<div class="empty"><div class="icon">🕸️</div><h3>Empty Graph</h3><p>Click "Extract" to build entities from your knowledge base, or add nodes manually.</p></div>';
      return;
    }

    var nodes = new vis.DataSet();
    var edges = new vis.DataSet();
    data.nodes.forEach(function(n){
      var color = COLORS[n.type] || '#64748b';
      if (communities && communities[n.id] !== undefined) {
        var pal = ['#FF6B6B','#4ECDC4','#45B7D1','#96CEB4','#FFEAA7','#DDA0DD'];
        color = pal[communities[n.id] % pal.length];
      }
      var size = Math.max(12, Math.min(40, (n.linkCount||1)*3+10));
      nodes.add({ id:n.id, label:n.name, color:{background:color,border:'#333'}, font:{size:size>20?13:10}, size:size, title:n.type+': '+n.name });
    });
    data.edges.forEach(function(e){
      edges.add({ from:e.source, to:e.target, label:e.relation||'', width:Math.max(1,e.weight||1), arrows:'to' });
    });

    network = new vis.Network(container, {nodes:nodes,edges:edges}, {
      physics:{solver:'forceAtlas2Based',forceAtlas2Based:{gravitationalConstant:-40,centralGravity:0.01}},
      interaction:{hover:true,tooltipDelay:200},
      edges:{smooth:{type:'continuous'}}
    });
    network.on('click', function(p){
      if (p.nodes.length > 0) {
        fetch('/api/graph/neighbors/'+encodeURIComponent(p.nodes[0])+'?depth=1')
          .then(function(r){ return r.json(); })
          .then(function(d){
            if (d.center) status('\uD83D\uDCCD '+d.center.name+' ('+d.center.type+') — '+d.nodes.length+' neighbors');
          });
      }
    });
  }

  function search() {
    var q = document.getElementById('graphSearch').value.trim();
    var type = document.getElementById('graphType').value;
    if (!q) { loadGraph(); return; }
    var url = '/api/graph/search?q='+encodeURIComponent(q)+'&limit=30';
    if (type) url += '&type='+encodeURIComponent(type);
    fetch(url).then(function(r){ return r.json(); }).then(function(ids){
      if (!ids.length) { status('No results for "'+q+'"'); return; }
      var nodeIds = ids.map(function(n){ return n.id; });
      fetch('/api/graph/subgraph', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({node_ids:nodeIds})})
        .then(function(r){ return r.json(); }).then(function(sg){ data = sg; render(); status('Search: '+sg.nodes.length+' nodes'); });
    });
  }

  function applyFilter() { search(); }

  function detectCommunities() {
    fetch('/api/graph/communities').then(function(r){ return r.json(); }).then(function(d){
      communities = d.assignments || {};
      render();
      var info = document.getElementById('graph-communities');
      var lines = ['<strong>Communities:</strong>'];
      (d.communities||[]).slice(0,5).forEach(function(c){
        lines.push(' C'+c.id+': '+c.nodeCount+' nodes, cohesion='+c.cohesion.toFixed(2)+' ['+(c.topNodes||[]).slice(0,3).join(', ')+']');
      });
      if (info) info.innerHTML = lines.join('<br>');
      status('Detected '+(d.communities||[]).length+' communities');
    });
  }

  function extractFromKb() {
    status('Extracting entities...');
    fetch('/api/kb/list').then(function(r){ return r.json(); }).then(function(d){
      var kbs = d.kbs || d || [];
      var names = kbs.map(function(k){ return k.display_name || k.internal_name || k.name; }).slice(0,5);
      if (!names.length) { status('No KBs found'); return; }
      // Quick approach: search across all KBs
      return fetch('/api/graph/extract', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({chunks:names.map(function(n){ return 'Topic: '+n; }), kb_id:names.join(',')})
      });
    }).then(function(r){ return r.json(); }).then(function(d){
      if (d.entities_added !== undefined) status('Added '+d.entities_added+' entities, '+d.relationships_added+' relations');
      loadGraph();
    }).catch(function(e){ status('Extraction error: '+e.message); loadGraph(); });
  }

  function clearGraph() {
    if (!confirm('Clear the entire knowledge graph?')) return;
    fetch('/api/graph/clear',{method:'POST'}).then(function(){
      data = {nodes:[],edges:[]}; communities = null;
      render(); status('Graph cleared');
    });
  }

  document.addEventListener('DOMContentLoaded', function(){ setTimeout(loadGraph, 600); });

  return { loadGraph:loadGraph, search:search, applyFilter:applyFilter, detectCommunities:detectCommunities, extractFromKb:extractFromKb, clearGraph:clearGraph };
})();
