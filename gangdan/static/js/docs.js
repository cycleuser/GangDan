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
    
    // Also refresh KB selector in chat panel
    if (typeof loadKbList === 'function') loadKbList();
}

// Upload documents to custom knowledge base
async function uploadDocs() {
    const kbName = document.getElementById('uploadKbName').value.trim();
    const filesInput = document.getElementById('uploadFiles');
    
    if (!kbName) {
        showToast(getT('kb_name_label') + '!', 'error');
        return;
    }
    if (!filesInput.files.length) {
        showToast(getT('select_files') + '!', 'error');
        return;
    }
    
    const formData = new FormData();
    formData.append('kb_name', kbName);
    for (const f of filesInput.files) {
        formData.append('files', f);
    }
    
    const statusDiv = document.getElementById('uploadStatus');
    statusDiv.innerHTML = '<span class="loading"></span> Checking...';
    
    try {
        // First check for duplicates
        const checkResp = await fetch('/api/docs/check-duplicates', { method: 'POST', body: formData });
        const checkData = await checkResp.json();
        
        if (checkData.has_duplicates) {
            // Show duplicate dialog
            const action = await showDuplicateDialog(checkData.duplicates);
            if (action === 'cancel') {
                statusDiv.textContent = getT('cancel');
                return;
            }
            
            // Recreate formData with duplicate_action
            const uploadFormData = new FormData();
            uploadFormData.append('kb_name', kbName);
            uploadFormData.append('duplicate_action', action);
            for (const f of filesInput.files) {
                uploadFormData.append('files', f);
            }
            
            statusDiv.innerHTML = '<span class="loading"></span> Uploading...';
            await doUpload(uploadFormData, statusDiv, filesInput);
        } else {
            // No duplicates, proceed directly
            statusDiv.innerHTML = '<span class="loading"></span> Uploading...';
            await doUpload(formData, statusDiv, filesInput);
        }
    } catch (e) {
        statusDiv.textContent = 'Error: ' + e.message;
        showToast(e.message, 'error');
    }
}

async function doUpload(formData, statusDiv, filesInput) {
    const resp = await fetch('/api/docs/upload', { method: 'POST', body: formData });
    const data = await resp.json();
    
    if (data.success) {
        statusDiv.innerHTML = '<span class="loading"></span> Indexing...';
        
        // Auto-index after upload
        const idxResp = await fetch('/api/docs/index', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source: data.name })
        });
        const idxData = await idxResp.json();
        
        let statusMsg = `Uploaded ${data.saved_count} files, indexed ${idxData.chunks} chunks`;
        if (data.skipped_count > 0) {
            statusMsg += ` (${data.skipped_count} skipped)`;
        }
        if (data.overwritten_count > 0) {
            statusMsg += ` (${data.overwritten_count} overwritten)`;
        }
        
        statusDiv.textContent = statusMsg;
        showToast(getT('upload_and_index') + ' ✓', 'success');
        filesInput.value = '';
        refreshDocs();
    } else {
        statusDiv.textContent = 'Error: ' + data.error;
        showToast(data.error, 'error');
    }
}

function showDuplicateDialog(duplicates) {
    return new Promise((resolve) => {
        // Create modal backdrop
        const backdrop = document.createElement('div');
        backdrop.className = 'modal-backdrop';
        backdrop.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:9999;display:flex;align-items:center;justify-content:center;';
        
        // Create modal content
        const modal = document.createElement('div');
        modal.className = 'modal-content';
        modal.style.cssText = 'background:var(--bg-secondary);border-radius:12px;padding:20px;max-width:500px;max-height:80vh;overflow-y:auto;';
        
        const title = getT('duplicate_files_found') || 'Duplicate Files Found';
        const msg = getT('duplicate_files_msg') || 'The following files already exist:';
        const skipBtn = getT('skip_duplicates') || 'Skip Duplicates';
        const overwriteBtn = getT('overwrite_duplicates') || 'Overwrite Duplicates';
        const cancelBtn = getT('cancel') || 'Cancel';
        
        modal.innerHTML = `
            <h3 style="margin-top:0;color:var(--warning);">⚠️ ${title}</h3>
            <p>${msg}</p>
            <ul style="max-height:200px;overflow-y:auto;background:rgba(0,0,0,0.2);padding:10px 10px 10px 30px;border-radius:6px;margin:10px 0;">
                ${duplicates.map(f => `<li style="margin:5px 0;">${escapeHtml(f)}</li>`).join('')}
            </ul>
            <div style="display:flex;gap:10px;margin-top:20px;flex-wrap:wrap;">
                <button class="btn btn-secondary" id="dupSkipBtn">${skipBtn}</button>
                <button class="btn btn-warning" id="dupOverwriteBtn">${overwriteBtn}</button>
                <button class="btn btn-danger" id="dupCancelBtn">${cancelBtn}</button>
            </div>
        `;
        
        backdrop.appendChild(modal);
        document.body.appendChild(backdrop);
        
        // Handle button clicks
        document.getElementById('dupSkipBtn').onclick = () => {
            document.body.removeChild(backdrop);
            resolve('skip');
        };
        document.getElementById('dupOverwriteBtn').onclick = () => {
            document.body.removeChild(backdrop);
            resolve('overwrite');
        };
        document.getElementById('dupCancelBtn').onclick = () => {
            document.body.removeChild(backdrop);
            resolve('cancel');
        };
        
        // Close on backdrop click
        backdrop.onclick = (e) => {
            if (e.target === backdrop) {
                document.body.removeChild(backdrop);
                resolve('cancel');
            }
        };
    });
}
