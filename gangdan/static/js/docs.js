// ============================================
// Documentation Panel Functions
// ============================================

// GitHub Search
async function searchGitHub() {
    const query = document.getElementById('githubSearchQuery').value.trim();
    const lang = document.getElementById('githubSearchLang').value;
    
    if (!query) {
        showToast('Please enter a search query', 'error');
        return;
    }
    
    const resultsDiv = document.getElementById('githubResults');
    resultsDiv.innerHTML = '<span class="loading"></span> Searching GitHub...';
    
    try {
        const response = await fetch('/api/github-search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, language: lang })
        });
        const data = await response.json();
        
        if (data.results && data.results.length > 0) {
            resultsDiv.innerHTML = data.results.map(r => `
                <div style="padding:8px; margin:5px 0; background:rgba(0,0,0,0.2); border-radius:6px;">
                    <div style="font-weight:500; color:#4fc3f7;">${escapeHtml(r.name)}</div>
                    <div style="font-size:0.85em; color:#90a4ae;">${escapeHtml(r.description || 'No description')}</div>
                    <div style="margin-top:5px;">
                        <button onclick="downloadGitHubRepo('${r.full_name}', '${r.name}')" 
                            class="btn btn-primary" style="padding:4px 10px; font-size:0.8em;">
                            ⬇️ Download
                        </button>
                        <span style="font-size:0.8em; color:#90a4ae; margin-left:10px;">⭐ ${r.stars}</span>
                    </div>
                </div>
            `).join('');
        } else {
            resultsDiv.innerHTML = '<span style="color:#90a4ae;">No results found</span>';
        }
    } catch (e) {
        resultsDiv.innerHTML = `<span style="color:#ef5350;">Error: ${e.message}</span>`;
    }
}

async function downloadGitHubRepo(fullName, name) {
    showToast(`Downloading ${name}...`, 'success');
    
    try {
        const response = await fetch('/api/github-download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ repo: fullName, name })
        });
        const data = await response.json();
        
        if (data.success) {
            showToast(`Downloaded ${data.files} files from ${name}`, 'success');
            refreshDocs();
        } else {
            showToast(`Error: ${data.error}`, 'error');
        }
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
}

// Single doc operations
async function downloadDocs() {
    const source = document.getElementById('docSource').value;
    document.getElementById('docStatus').innerHTML = '<span class="loading"></span> Downloading...';
    
    const response = await fetch('/api/docs/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source })
    });
    const data = await response.json();
    
    document.getElementById('docStatus').textContent = 
        `Downloaded: ${data.downloaded}, Errors: ${data.errors.length}`;
    refreshDocs();
}

async function indexDocs() {
    const source = document.getElementById('docSource').value;
    document.getElementById('docStatus').innerHTML = '<span class="loading"></span> Indexing...';
    
    const response = await fetch('/api/docs/index', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source })
    });
    const data = await response.json();
    
    document.getElementById('docStatus').textContent = 
        `Files: ${data.files}, Chunks: ${data.chunks}`;
}

// Batch operations
function selectAllBatch(checked) {
    document.querySelectorAll('.batch-checkbox').forEach(cb => cb.checked = checked);
}

async function batchDownload() {
    const sources = Array.from(document.querySelectorAll('.batch-checkbox:checked')).map(cb => cb.value);
    if (sources.length === 0) {
        showToast('Please select at least one source', 'error');
        return;
    }
    
    document.getElementById('batchStatus').innerHTML = '<span class="loading"></span> Downloading ' + sources.length + ' sources...';
    
    const response = await fetch('/api/docs/batch-download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sources })
    });
    const data = await response.json();
    
    document.getElementById('batchStatus').innerHTML = data.results.map(r => 
        `${r.source}: ${r.downloaded} files, ${r.errors} errors`
    ).join('<br>');
    refreshDocs();
}

async function batchIndex() {
    const sources = Array.from(document.querySelectorAll('.batch-checkbox:checked')).map(cb => cb.value);
    if (sources.length === 0) {
        showToast('Please select at least one source', 'error');
        return;
    }
    
    document.getElementById('batchStatus').innerHTML = '<span class="loading"></span> Indexing ' + sources.length + ' sources...';
    
    const response = await fetch('/api/docs/batch-index', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sources })
    });
    const data = await response.json();
    
    document.getElementById('batchStatus').innerHTML = data.results.map(r => 
        `${r.source}: ${r.files} files, ${r.chunks} chunks`
    ).join('<br>');
}

// Web search to KB
async function webSearchToKb() {
    const query = document.getElementById('webSearchQuery').value.trim();
    const name = document.getElementById('webSearchName').value.trim() || 'web_search';
    
    if (!query) {
        showToast('Please enter a search query', 'error');
        return;
    }
    
    document.getElementById('webSearchStatus').innerHTML = '<span class="loading"></span> Searching and indexing...';
    
    const response = await fetch('/api/docs/web-search-to-kb', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, name })
    });
    const data = await response.json();
    
    document.getElementById('webSearchStatus').textContent = 
        `Found: ${data.found} results, Indexed: ${data.indexed} chunks`;
    refreshDocs();
}

async function refreshDocs() {
    const response = await fetch('/api/docs/list');
    const data = await response.json();
    
    const list = document.getElementById('docsList');
    list.innerHTML = data.map(d => `
        <div class="doc-item">
            <div>
                <div class="name">${d.name}</div>
                <div class="status">${d.files} files</div>
            </div>
        </div>
    `).join('') || '<p style="color:#90a4ae">No documents downloaded</p>';
}
