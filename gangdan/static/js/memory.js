/**
 * Memory management module.
 *
 * Provides remember, forget, search, and list operations on the persistent
 * memory store (MEMORY.md + history.jsonl).
 */
var MemoryModule = (function() {
    'use strict';

    function remember() {
        var content = document.getElementById('memContentInput').value.trim();
        var type = document.getElementById('memTypeSelect').value;
        if (!content) { showToast('Please enter content to remember', 'warning'); return; }

        fetch('/api/memory', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: content, memory_type: type, importance: 0.8 }),
        })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.success) {
                    document.getElementById('memContentInput').value = '';
                    showToast('Memory saved (' + type + ')', 'success');
                    listAll();
                } else {
                    showToast('Error: ' + (data.error || 'unknown'), 'error');
                }
            })
            .catch(function(e) { showToast('Error: ' + e.message, 'error'); });
    }

    function search() {
        var q = document.getElementById('memSearchInput').value.trim();
        if (!q) { listAll(); return; }

        fetch('/api/memory/search?q=' + encodeURIComponent(q) + '&limit=20')
            .then(function(r) { return r.json(); })
            .then(function(data) { _renderResults(data.results || data); });
    }

    function listAll() {
        fetch('/api/memory/list?limit=50')
            .then(function(r) { return r.json(); })
            .then(function(data) { _renderResults(data.results || data); });
    }

    function forget(entryId, contentPreview) {
        if (!confirm('Forget: "' + contentPreview.substring(0, 80) + '..." ?')) return;
        fetch('/api/memory/forget', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ memory_id: entryId }),
        })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.success) { showToast('Forgotten', 'success'); listAll(); }
                else { showToast('Error: ' + (data.error || 'unknown'), 'error'); }
            });
    }

    function _renderResults(results) {
        var el = document.getElementById('memResults');
        if (!el) return;

        if (!results || results.length === 0) {
            el.innerHTML = '<div class="empty-state" style="padding:20px;">No memories found</div>';
            return;
        }

        var html = '';
        results.forEach(function(m) {
            var typeBadge = '<span style="background:var(--accent);color:#fff;padding:1px 6px;border-radius:4px;font-size:0.75em;">' + escapeHtml(m.type || 'fact') + '</span>';
            var impStars = '★'.repeat(Math.round((m.importance || 0.5) * 5));
            var content = escapeHtml(m.content || '').substring(0, 300);
            html += '<div style="border:1px solid var(--border);border-radius:8px;padding:10px 14px;margin-bottom:8px;display:flex;justify-content:space-between;align-items:flex-start;">' +
                '<div style="flex:1;">' +
                '<div style="margin-bottom:4px;">' + typeBadge + ' <span style="color:#f59e0b;font-size:0.8em;">' + impStars + '</span> <span style="font-size:0.75em;color:var(--text-muted);">' + (m.created_at || '').substring(0,10) + '</span></div>' +
                '<div style="white-space:pre-wrap;font-size:0.9em;">' + content + '</div>' +
                '</div>' +
                '<button class="btn btn-sm" style="color:#ef4444;border:none;background:none;cursor:pointer;font-size:1.1em;" title="Forget" onclick="MemoryModule.forget(\'' + (m.id || '') + '\',\'' + (m.content || '').replace(/'/g, "\\'").substring(0, 80) + '\')">✕</button>' +
                '</div>';
        });
        el.innerHTML = html;
    }

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Load on panel switch
    return {
        remember: remember,
        search: search,
        listAll: listAll,
        forget: forget,
    };
})();
