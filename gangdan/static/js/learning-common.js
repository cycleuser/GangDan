/* GangDan - Learning Module Common Utilities
 * Shared code for all learning modules.
 */

// Shared KB selection state
window._learningSelectedKbs = new Set();
var _sharedKbData = null;

// =============================================================================
// Shared KB Loading (for integrated tabs)
// =============================================================================

async function loadSharedKbList() {
    var prefixes = ['q', 'g', 'r', 'l', 'e'];
    try {
        var res = await fetch('/api/learning/kb/list');
        var data = await res.json();
        _sharedKbData = data.kbs || [];
        if (_sharedKbData.length === 0) {
            var emptyHtml = '<div class="empty-state">No knowledge bases available</div>';
            prefixes.forEach(function(p) {
                var c = document.getElementById(p + '-kbCheckList');
                if (c) c.innerHTML = emptyHtml;
            });
            return;
        }
        var html = _sharedKbData.map(function(kb) {
            return '<label class="kb-check-item">' +
                '<input type="checkbox" value="' + kb.name + '"' +
                (window._learningSelectedKbs.has(kb.name) ? ' checked' : '') +
                ' onchange="toggleSharedKb(this)">' +
                '<span>' + kb.display_name + ' <small style="color:var(--text-muted)">(' + kb.doc_count + ')</small></span>' +
                '</label>';
        }).join('');
        prefixes.forEach(function(p) {
            var c = document.getElementById(p + '-kbCheckList');
            if (c) c.innerHTML = html;
        });
    } catch (e) {
        prefixes.forEach(function(p) {
            var c = document.getElementById(p + '-kbCheckList');
            if (c) c.innerHTML = '<div class="empty-state">Failed to load KBs</div>';
        });
    }
}

function toggleSharedKb(checkbox) {
    if (checkbox.checked) window._learningSelectedKbs.add(checkbox.value);
    else window._learningSelectedKbs.delete(checkbox.value);
    // Sync all checkboxes with same value across containers
    ['q', 'g', 'r', 'l', 'e'].forEach(function(p) {
        var container = document.getElementById(p + '-kbCheckList');
        if (!container) return;
        var cb = container.querySelector('input[value="' + checkbox.value + '"]');
        if (cb && cb !== checkbox) cb.checked = checkbox.checked;
    });
}

// =============================================================================
// Translation Helper
// =============================================================================

function getTCommon(key) {
    if (window.ALL_TRANSLATIONS && window.ALL_TRANSLATIONS[key]) {
        return window.ALL_TRANSLATIONS[key][window.SERVER_CONFIG.lang] ||
               window.ALL_TRANSLATIONS[key]['en'] || key;
    }
    return key;
}

// =============================================================================
// Status Message
// =============================================================================

function setStatusCommon(msg, elementId) {
    var el = document.getElementById(elementId || 'statusMsg');
    if (el) el.textContent = msg;
}

// =============================================================================
// SSE Reader
// =============================================================================

async function createSSEReader(response, handlers, onError) {
    if (!response.ok) {
        var errMsg = 'Server error: ' + response.status;
        if (onError) onError(errMsg);
        return;
    }

    var reader = response.body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';

    try {
        while (true) {
            var result = await reader.read();
            if (result.done) break;

            buffer += decoder.decode(result.value, { stream: true });
            var lines = buffer.split('\n');
            buffer = lines.pop();

            for (var i = 0; i < lines.length; i++) {
                var line = lines[i];
                if (!line.startsWith('data: ')) continue;
                try {
                    var event = JSON.parse(line.slice(6));
                    if (event.type === 'error') {
                        if (onError) onError(event.message);
                        else if (handlers.error) handlers.error(event);
                    } else if (handlers[event.type]) {
                        handlers[event.type](event);
                    }
                } catch (e) {
                    // Skip malformed SSE lines
                }
            }
        }
    } catch (e) {
        if (onError) onError('Connection error: ' + e.message);
    }
}

// =============================================================================
// localStorage Persistence
// =============================================================================

function saveState(moduleKey, stateObject) {
    try {
        localStorage.setItem('gangdan_' + moduleKey, JSON.stringify(stateObject));
    } catch (e) {}
}

function loadState(moduleKey) {
    try {
        var raw = localStorage.getItem('gangdan_' + moduleKey);
        return raw ? JSON.parse(raw) : null;
    } catch (e) {
        return null;
    }
}

function clearState(moduleKey) {
    try {
        localStorage.removeItem('gangdan_' + moduleKey);
    } catch (e) {}
}

// =============================================================================
// Export Utilities
// =============================================================================

function exportMarkdown(content, filename) {
    if (!content) return;
    var blob = new Blob([content], { type: 'text/markdown' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = filename || 'export.md';
    a.click();
    URL.revokeObjectURL(url);
}

function copyToClipboard(content, statusCallback) {
    if (!content) return;
    navigator.clipboard.writeText(content).then(function() {
        if (statusCallback) statusCallback('Copied to clipboard');
    }).catch(function() {
        if (statusCallback) statusCallback('Copy failed');
    });
}

// =============================================================================
// Retry Button
// =============================================================================

function createRetryHtml(retryFn, message) {
    var id = 'retry_' + Date.now();
    window[id] = retryFn;
    return '<div class="error-retry-container">' +
        '<div class="error-msg">' + (message || 'An error occurred') + '</div>' +
        '<button class="btn-learning btn-learning-secondary btn-retry" onclick="' + id + '()">Retry</button>' +
    '</div>';
}
