// ============================================
// Documentation Panel Functions
// ============================================

// Global state
var _uploadXhr = null;

// Toggle between files and folder upload mode
function toggleUploadMode() {
    var mode = document.getElementById('uploadMode').value;
    var filesGroup = document.getElementById('filesUploadGroup');
    var folderGroup = document.getElementById('folderUploadGroup');
    
    if (mode === 'files') {
        filesGroup.style.display = 'block';
        folderGroup.style.display = 'none';
    } else {
        filesGroup.style.display = 'none';
        folderGroup.style.display = 'block';
    }
}

// Update upload progress
function updateUploadProgress(percent, text) {
    var progressDiv = document.getElementById('uploadProgress');
    var progressBar = document.getElementById('uploadProgressBar');
    var progressText = document.getElementById('uploadProgressText');
    var progressPercent = document.getElementById('uploadProgressPercent');
    
    if (progressDiv) {
        progressDiv.style.display = 'block';
        if (progressBar) progressBar.style.width = percent + '%';
        if (progressText) progressText.textContent = text || 'Uploading...';
        if (progressPercent) progressPercent.textContent = percent + '%';
    }
}

function hideUploadProgress() {
    var progressDiv = document.getElementById('uploadProgress');
    if (progressDiv) progressDiv.style.display = 'none';
}

// System stats refresh
async function refreshSystemStats() {
    try {
        var response = await fetch('/api/system/stats');
        var data = await response.json();
        
        if (data.success) {
            var contextEl = document.getElementById('currentContextLength');
            var memoryEl = document.getElementById('memoryUsage');
            var docCountEl = document.getElementById('kbDocCount');
            
            if (contextEl) contextEl.textContent = data.context_tokens || 0;
            if (memoryEl) memoryEl.textContent = data.memory_mb || '--';
            if (docCountEl) docCountEl.textContent = data.total_docs || 0;
        }
    } catch (e) {
        console.error('Failed to refresh system stats:', e);
    }
}

// Refresh stats periodically
setInterval(refreshSystemStats, 30000);

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
    var kbName = document.getElementById('uploadKbName').value.trim();
    var uploadMode = document.getElementById('uploadMode').value;
    var filesInput = uploadMode === 'folder' 
        ? document.getElementById('uploadFolder')
        : document.getElementById('uploadFiles');
    var imageMode = document.getElementById('uploadImageMode').value;
    var wordLimit = document.getElementById('outputWordLimit').value || 1000;
    
    if (!kbName) {
        showToast(getT('kb_name_label') + '!', 'error');
        return;
    }
    if (!filesInput.files.length) {
        showToast(getT('select_files') + '!', 'error');
        return;
    }
    
    var formData = new FormData();
    formData.append('kb_name', kbName);
    formData.append('image_mode', imageMode);
    formData.append('output_word_limit', wordLimit);
    formData.append('upload_mode', uploadMode);
    
    var totalFiles = filesInput.files.length;
    var processedFiles = 0;
    
    for (var i = 0; i < filesInput.files.length; i++) {
        var f = filesInput.files[i];
        formData.append('files', f);
    }
    
    var statusDiv = document.getElementById('uploadStatus');
    updateUploadProgress(0, getT('uploading') || 'Uploading...');
    
    try {
        // First check for duplicates
        var checkResp = await fetch('/api/docs/check-duplicates', { method: 'POST', body: formData });
        var checkData = await checkResp.json();
        
        updateUploadProgress(10, 'Checking duplicates...');
        
        if (checkData.has_duplicates) {
            var action = await showDuplicateDialog(checkData.duplicates);
            if (action === 'cancel') {
                statusDiv.textContent = getT('cancel');
                hideUploadProgress();
                return;
            }
            
            var uploadFormData = new FormData();
            uploadFormData.append('kb_name', kbName);
            uploadFormData.append('duplicate_action', action);
            uploadFormData.append('image_mode', imageMode);
            uploadFormData.append('output_word_limit', wordLimit);
            uploadFormData.append('upload_mode', uploadMode);
            for (var j = 0; j < filesInput.files.length; j++) {
                uploadFormData.append('files', filesInput.files[j]);
            }
            
            updateUploadProgress(20, getT('uploading') || 'Uploading...');
            await doUpload(uploadFormData, statusDiv, filesInput, totalFiles);
        } else {
            updateUploadProgress(20, getT('uploading') || 'Uploading...');
            await doUpload(formData, statusDiv, filesInput, totalFiles);
        }
    } catch (e) {
        statusDiv.textContent = 'Error: ' + e.message;
        showToast(e.message, 'error');
        hideUploadProgress();
    }
}

async function doUpload(formData, statusDiv, filesInput, totalFiles) {
    var imageMode = formData.get('image_mode') || 'copy';
    var wordLimit = formData.get('output_word_limit') || 1000;
    
    updateUploadProgress(30, 'Uploading files...');
    
    var xhr = new XMLHttpRequest();
    _uploadXhr = xhr;
    
    xhr.upload.onprogress = function(e) {
        if (e.lengthComputable) {
            var percent = Math.round((e.loaded / e.total) * 50) + 30;
            updateUploadProgress(percent, 'Uploading files...');
        }
    };
    
    var uploadComplete = new Promise(function(resolve, reject) {
        xhr.onload = function() {
            if (xhr.status === 200) {
                resolve(JSON.parse(xhr.responseText));
            } else {
                reject(new Error('Upload failed: ' + xhr.statusText));
            }
        };
        xhr.onerror = function() {
            reject(new Error('Network error'));
        };
    });
    
    xhr.open('POST', '/api/docs/upload');
    xhr.send(formData);
    
    try {
        var data = await uploadComplete;
    } catch (e) {
        hideUploadProgress();
        statusDiv.textContent = 'Error: ' + e.message;
        showToast(e.message, 'error');
        return;
    } finally {
        _uploadXhr = null;
    }
    
    if (data.success) {
        updateUploadProgress(60, 'Indexing documents...');
        statusDiv.innerHTML = '<span class="loading"></span> Indexing...';
        
        var idxResp = await fetch('/api/docs/index', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ 
                source: data.name,
                image_mode: imageMode,
                output_word_limit: parseInt(wordLimit)
            })
        });
        var idxData = await idxResp.json();
        
        updateUploadProgress(100, 'Complete!');
        
        var statusMsg = 'Uploaded ' + data.saved_count + ' files, indexed ' + idxData.chunks + ' chunks';
        if (idxData.images_processed > 0) {
            statusMsg += ', ' + idxData.images_processed + ' images';
        }
        if (data.skipped_count > 0) {
            statusMsg += ' (' + data.skipped_count + ' skipped)';
        }
        if (data.overwritten_count > 0) {
            statusMsg += ' (' + data.overwritten_count + ' overwritten)';
        }
        
        statusDiv.textContent = statusMsg;
        showToast(getT('upload_and_index') + ' ✓', 'success');
        filesInput.value = '';
        
        setTimeout(function() {
            hideUploadProgress();
        }, 2000);
        
        refreshDocs();
        refreshSystemStats();
    } else {
        hideUploadProgress();
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

// ============================================
// Import / Export Functions
// ============================================

async function exportRawFiles() {
    const statusDiv = document.getElementById('rawFilesStatus');
    statusDiv.innerHTML = '<span class="loading"></span> ' + (getT('exporting') || 'Exporting...');

    try {
        const response = await fetch('/api/export-raw-files');
        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.error || `HTTP ${response.status}`);
        }

        const blob = await response.blob();
        const disposition = response.headers.get('Content-Disposition') || '';
        const match = disposition.match(/filename="?([^"]+)"?/);
        const filename = match ? match[1] : 'gangdan_raw_files.zip';

        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        statusDiv.textContent = getT('export_success') || 'Export successful';
        showToast(getT('export_success') || 'Export successful', 'success');
    } catch (e) {
        statusDiv.textContent = 'Error: ' + e.message;
        showToast(e.message, 'error');
    }
}

async function importRawFiles(input) {
    if (!input.files.length) return;

    const statusDiv = document.getElementById('rawFilesStatus');
    statusDiv.innerHTML = '<span class="loading"></span> ' + (getT('importing') || 'Importing...');

    const formData = new FormData();
    formData.append('file', input.files[0]);

    try {
        const response = await fetch('/api/import-raw-files', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();

        if (data.success) {
            statusDiv.textContent = (getT('import_success') || 'Import successful') + ' - ' + data.message;
            showToast(getT('import_success') || 'Import successful', 'success');
            refreshDocs();
        } else {
            statusDiv.textContent = 'Error: ' + data.error;
            showToast(data.error, 'error');
        }
    } catch (e) {
        statusDiv.textContent = 'Error: ' + e.message;
        showToast(e.message, 'error');
    }

    input.value = '';
}

async function exportKb() {
    const statusDiv = document.getElementById('kbStatus');
    statusDiv.innerHTML = '<span class="loading"></span> ' + (getT('exporting') || 'Exporting...');

    try {
        const response = await fetch('/api/export-kb');
        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.error || `HTTP ${response.status}`);
        }

        const blob = await response.blob();
        const disposition = response.headers.get('Content-Disposition') || '';
        const match = disposition.match(/filename="?([^"]+)"?/);
        const filename = match ? match[1] : 'gangdan_kb.zip';

        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        statusDiv.textContent = getT('export_success') || 'Export successful';
        showToast(getT('export_success') || 'Export successful', 'success');
    } catch (e) {
        statusDiv.textContent = 'Error: ' + e.message;
        showToast(e.message, 'error');
    }
}

async function importKb(input) {
    if (!input.files.length) return;

    const statusDiv = document.getElementById('kbStatus');
    statusDiv.innerHTML = '<span class="loading"></span> ' + (getT('importing') || 'Importing...');

    const formData = new FormData();
    formData.append('file', input.files[0]);

    try {
        const response = await fetch('/api/import-kb', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();

        if (data.success) {
            statusDiv.textContent = (getT('import_success') || 'Import successful') + ' - ' + data.message;
            showToast(getT('import_success') || 'Import successful', 'success');
            refreshDocs();
        } else {
            statusDiv.textContent = 'Error: ' + data.error;
            showToast(data.error, 'error');
        }
    } catch (e) {
        statusDiv.textContent = 'Error: ' + e.message;
        showToast(e.message, 'error');
    }

    input.value = '';
}
