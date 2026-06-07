/* Memory management — persistent fact storage via /api/memory/* */
var MemoryModule = (function() {
  'use strict';

  function remember() {
    var content = (document.getElementById('memContent')?.value || '').trim();
    var type = document.getElementById('memType')?.value || 'fact';
    if (!content) { G.toast('Enter content to remember', 'warn'); return; }
    fetch('/api/memory/remember', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({content:content, memory_type:type, importance:0.8})
    }).then(function(r){ return r.json(); }).then(function(d){
      if (d.success) { document.getElementById('memContent').value = ''; G.toast('Remembered ('+type+')', 'ok'); listAll(); }
      else G.toast('Error: '+(d.error||'unknown'), 'err');
    }).catch(function(e){ G.toast('Error: '+e.message, 'err'); });
  }

  function search() {
    var q = (document.getElementById('memSearch')?.value || '').trim();
    if (!q) { listAll(); return; }
    fetch('/api/memory/search?q='+encodeURIComponent(q)+'&limit=20')
      .then(function(r){ return r.json(); }).then(function(d){ render(d.results||d); });
  }

  function listAll() {
    fetch('/api/memory/list?limit=50')
      .then(function(r){ return r.json(); }).then(function(d){ render(d.results||d); });
  }

  function forget(id, preview) {
    if (!confirm('Forget "'+(preview||'').substring(0,80)+'..."?')) return;
    fetch('/api/memory/forget', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({memory_id:id})})
      .then(function(r){ return r.json(); }).then(function(d){
        if (d.success) { G.toast('Forgotten', 'ok'); listAll(); }
        else G.toast('Error: '+(d.error||'unknown'), 'err');
      });
  }

  function render(items) {
    var el = document.getElementById('memResults');
    if (!el) return;
    if (!items || !items.length) {
      el.innerHTML = '<div class="empty"><div class="icon">🧠</div><h3>No memories found</h3><p>Save facts, preferences and research findings</p></div>';
      return;
    }
    el.innerHTML = items.map(function(m){
      var type = m.type || 'fact';
      var stars = '\u2605'.repeat(Math.round((m.importance||0.5)*5));
      var content = (m.content||'').substring(0,350).replace(/</g,'&lt;');
      var date = (m.created_at||'').substring(0,10);
      var id = (m.id||'').replace(/'/g,"\\'");
      return '<div style="border:1px solid var(--border);border-radius:8px;padding:10px 14px;margin-bottom:8px;display:flex;justify-content:space-between;align-items:flex-start;">'+
        '<div style="flex:1;"><div style="margin-bottom:4px;">'+
        '<span class="badge green" style="margin-right:6px;">'+type+'</span>'+
        '<span style="color:#f59e0b;font-size:0.78em;">'+stars+'</span> '+
        '<span style="font-size:0.75em;color:var(--muted);">'+date+'</span></div>'+
        '<div style="white-space:pre-wrap;font-size:0.88em;">'+content+'</div></div>'+
        '<button style="color:var(--red);border:none;background:none;cursor:pointer;font-size:1.1em;padding:4px;" title="Forget" onclick="MemoryModule.forget(\''+id+'\',\''+content.substring(0,60)+'\')">\u2715</button>'+
        '</div>';
    }).join('');
  }

  return { remember:remember, search:search, listAll:listAll, forget:forget };
})();
