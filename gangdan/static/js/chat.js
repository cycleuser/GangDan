// ============================================
// Chat Panel Functions
// ============================================

let isGenerating = false;
let availableKbs = [];
let selectedKbs = new Set();

function addMessage(role, content) {
    const div = document.createElement('div');
    div.className = 'message ' + role;
    div.innerHTML = renderMarkdown(content);
    document.getElementById('chatMessages').appendChild(div);
    // Render LaTeX formulas
    renderLatex(div);
    div.scrollIntoView({ behavior: 'smooth' });
    return div;
}

function copyCode(blockId) {
    const code = document.getElementById(blockId).textContent;
    navigator.clipboard.writeText(code);
    showToast('Copied to clipboard', 'success');
}

async function runCodeBlock(blockId, lang) {
    const code = document.getElementById(blockId).textContent;
    const container = document.getElementById(blockId + '-container');
    
    // Remove existing output
    const existingOutput = container.querySelector('.code-output');
    if (existingOutput) existingOutput.remove();
    
    // Show loading
    const outputDiv = document.createElement('div');
    outputDiv.className = 'code-output';
    outputDiv.textContent = 'Running...';
    container.appendChild(outputDiv);
    
    try {
        const response = await fetch('/api/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code, language: lang })
        });
        const data = await response.json();
        
        outputDiv.className = 'code-output ' + (data.error ? 'error' : 'success');
        outputDiv.textContent = data.output || data.error || 'No output';
    } catch (e) {
        outputDiv.className = 'code-output error';
        outputDiv.textContent = 'Error: ' + e.message;
    }
}

async function sendMessage() {
    const input = document.getElementById('chatInput');
    const message = input.value.trim();
    if (!message || isGenerating) return;
    
    input.value = '';
    addMessage('user', message);
    
    isGenerating = true;
    document.getElementById('sendBtn').style.display = 'none';
    document.getElementById('stopBtn').style.display = 'inline-block';
    
    const assistantDiv = addMessage('assistant', '<span class="loading"></span>');
    
    try {
        const useKb = document.getElementById('useKb').checked;
        const useWeb = document.getElementById('useWeb').checked;
        
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, use_kb: useKb, use_web: useWeb, kb_scope: useKb ? Array.from(selectedKbs) : null })
        });
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const text = decoder.decode(value);
            const lines = text.split('\n');
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.content) {
                            fullText += data.content;
                            assistantDiv.innerHTML = renderStreamingText(fullText);
                        }
                        if (data.done || data.stopped) break;
                    } catch (e) {}
                }
            }
        }
        
        // Final render with LaTeX
        assistantDiv.innerHTML = renderMarkdown(fullText);
        renderLatex(assistantDiv);
        
    } catch (e) {
        assistantDiv.innerHTML = 'Error: ' + e.message;
    }
    
isGenerating = false;
    document.getElementById('sendBtn').style.display = 'inline-block';
    document.getElementById('stopBtn').style.display = 'none';
}

// ============================================
// KB Management Functions
// ============================================

async function showKbManager() {
    const backdrop = document.createElement('div');
    backdrop.className = 'modal-backdrop';
    backdrop.id = 'kbManagerBackdrop';
    backdrop.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:9999;display:flex;align-items:center;justify-content:center;overflow-y:auto;padding:20px;';
    
    const title = getT('kb_manager') || 'Knowledge Base Manager';
    const loadingText = getT('loading') || 'Loading...';
    
    backdrop.innerHTML = `
        <div class="modal-content kb-manager-modal" style="background:var(--bg-secondary);border-radius:12px;padding:20px;max-width:800px;width:100%;max-height:90vh;overflow-y:auto;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;">
                <h3 style="margin:0;color:var(--primary);">📚 ${title}</h3>
                <button class="btn btn-sm btn-secondary" onclick="closeKbManager()">✕</button>
            </div>
            <div id="kbManagerContent" style="min-height:200px;">
                <span class="loading"></span> ${loadingText}
            </div>
        </div>
    `;
    
    document.body.appendChild(backdrop);
    backdrop.onclick = (e) => {
        if (e.target === backdrop) closeKbManager();
    };
    
    await loadKbManagerContent();
}

function closeKbManager() {
    const backdrop = document.getElementById('kbManagerBackdrop');
    if (backdrop) backdrop.remove();
}

async function loadKbManagerContent() {
    const content = document.getElementById('kbManagerContent');
    
    try {
        const response = await fetch('/api/kb/list');
        const data = await response.json();
        const kbs = data.kbs || [];
        
        if (kbs.length === 0) {
            content.innerHTML = `<p style="color:var(--text-muted);text-align:center;padding:40px;">${getT('no_kbs_found') || 'No knowledge bases found'}</p>`;
            return;
        }
        
        const typeOrder = { builtin: 0, user: 1, other: 2 };
        const sorted = [...kbs].sort((a, b) => (typeOrder[a.type] || 9) - (typeOrder[b.type] || 9));
        
        const builtinLabel = getT('builtin_kb_type') || 'Built-in';
        const userLabel = getT('user_kb_type') || 'User';
        const otherLabel = getT('other_kb_type') || 'Other';
        const deleteLabel = getT('delete') || 'Delete';
        const viewFilesLabel = getT('view_files') || 'View Files';
        const docsLabel = getT('docs_count') || 'docs';
        
        content.innerHTML = sorted.map(kb => {
            const badgeClass = kb.type === 'user' ? 'user' : (kb.type === 'builtin' ? 'builtin' : 'other');
            const badgeText = kb.type === 'user' ? userLabel : (kb.type === 'builtin' ? builtinLabel : otherLabel);
            const canDelete = kb.type === 'user' || kb.type === 'other';
            
            return `
                <div class="kb-manager-item" style="display:flex;justify-content:space-between;align-items:center;padding:12px;margin:8px 0;background:rgba(0,0,0,0.2);border-radius:8px;flex-wrap:wrap;gap:10px;">
                    <div style="flex:1;min-width:200px;">
                        <div style="font-weight:500;color:var(--text-primary);">${escapeHtml(kb.display_name)}</div>
                        <div style="font-size:0.85em;color:var(--text-muted);">
                            <span class="kb-type-badge ${badgeClass}" style="margin-right:8px;">${badgeText}</span>
                            ${kb.doc_count} ${docsLabel}
                            ${kb.languages && kb.languages.length > 0 ? `<span style="margin-left:8px;">[${kb.languages.join(', ')}]</span>` : ''}
                        </div>
                    </div>
                    <div style="display:flex;gap:8px;flex-wrap:wrap;">
                        <button class="btn btn-sm btn-secondary" onclick="showKbFiles('${kb.name}', '${escapeHtml(kb.display_name)}')">📁 ${viewFilesLabel}</button>
                        ${canDelete ? `<button class="btn btn-sm btn-danger" onclick="confirmDeleteKb('${kb.name}', '${escapeHtml(kb.display_name)}')">🗑️ ${deleteLabel}</button>` : ''}
                    </div>
                </div>
            `;
        }).join('');
    } catch (e) {
        content.innerHTML = `<p style="color:var(--error);text-align:center;padding:40px;">Error: ${e.message}</p>`;
    }
}

async function showKbFiles(kbName, displayName) {
    const content = document.getElementById('kbManagerContent');
    const backLabel = getT('back') || 'Back';
    const loadingText = getT('loading') || 'Loading...';
    
    content.innerHTML = `
        <div style="margin-bottom:15px;">
            <button class="btn btn-sm btn-secondary" onclick="loadKbManagerContent()">← ${backLabel}</button>
        </div>
        <h4 style="color:var(--primary);margin-bottom:15px;">📁 ${escapeHtml(displayName)}</h4>
        <div id="kbFilesContent"><span class="loading"></span> ${loadingText}</div>
    `;
    
    const filesContent = document.getElementById('kbFilesContent');
    
    try {
        const response = await fetch(`/api/kb/files?name=${encodeURIComponent(kbName)}`);
        const data = await response.json();
        
        if (!data.success) {
            filesContent.innerHTML = `<p style="color:var(--error);">${data.error || 'Failed to load files'}</p>`;
            return;
        }
        
        const files = data.files || [];
        if (files.length === 0) {
            filesContent.innerHTML = `<p style="color:var(--text-muted);text-align:center;padding:20px;">${getT('no_files_in_kb') || 'No files in this knowledge base'}</p>`;
            return;
        }
        
        const deleteSelectedLabel = getT('delete_selected') || 'Delete Selected';
        const deleteAllLabel = getT('delete_all_files') || 'Delete All Files';
        const fileNameLabel = getT('file_name') || 'File Name';
        const chunksLabel = getT('chunks') || 'Chunks';
        const langLabel = getT('language') || 'Language';
        
        filesContent.innerHTML = `
            <div style="margin-bottom:15px;display:flex;gap:10px;flex-wrap:wrap;">
                <button class="btn btn-sm btn-danger" onclick="deleteSelectedKbFiles('${kbName}')">🗑️ ${deleteSelectedLabel}</button>
                <button class="btn btn-sm btn-danger" onclick="deleteAllKbFiles('${kbName}', '${escapeHtml(displayName)}')">⚠️ ${deleteAllLabel}</button>
            </div>
            <div style="display:flex;justify-content:space-between;padding:8px;background:rgba(0,0,0,0.3);border-radius:4px;margin-bottom:10px;font-size:0.85em;color:var(--text-muted);">
                <label style="display:flex;align-items:center;gap:5px;cursor:pointer;">
                    <input type="checkbox" id="selectAllKbFiles" onchange="toggleAllKbFiles(this.checked)">
                    ${fileNameLabel}
                </label>
                <span>${chunksLabel}</span>
                <span>${langLabel}</span>
            </div>
            <div id="kbFilesList">
                ${files.map(f => `
                    <div class="kb-file-item" style="display:flex;justify-content:space-between;align-items:center;padding:8px;margin:4px 0;background:rgba(0,0,0,0.15);border-radius:6px;">
                        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;flex:1;min-width:0;">
                            <input type="checkbox" class="kb-file-checkbox" data-file="${escapeHtml(f.file)}">
                            <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(f.file)}">${escapeHtml(f.file)}</span>
                        </label>
                        <span style="font-size:0.85em;color:var(--text-muted);min-width:60px;text-align:center;">${f.doc_count}</span>
                        <span style="font-size:0.85em;color:var(--text-muted);min-width:80px;text-align:center;">${f.language || '-'}</span>
                    </div>
                `).join('')}
            </div>
            <div style="margin-top:15px;padding:10px;background:rgba(0,0,0,0.2);border-radius:6px;font-size:0.85em;color:var(--text-muted);">
                <strong>${getT('total') || 'Total'}:</strong> ${data.total_docs} ${getT('documents') || 'documents'} ${getT('in') || 'in'} ${files.length} ${getT('files') || 'files'}
            </div>
        `;
    } catch (e) {
        filesContent.innerHTML = `<p style="color:var(--error);">Error: ${e.message}</p>`;
    }
}

function toggleAllKbFiles(checked) {
    document.querySelectorAll('.kb-file-checkbox').forEach(cb => cb.checked = checked);
}

async function deleteSelectedKbFiles(kbName) {
    const checkboxes = document.querySelectorAll('.kb-file-checkbox:checked');
    const files = Array.from(checkboxes).map(cb => cb.dataset.file);
    
    if (files.length === 0) {
        showToast(getT('select_files_first') || 'Please select files first', 'warning');
        return;
    }
    
    const confirmMsg = (getT('confirm_delete_files') || 'Delete {0} file(s) from this knowledge base?').replace('{0}', files.length);
    if (!confirm(confirmMsg)) return;
    
    try {
        const response = await fetch('/api/kb/delete-files', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: kbName, files: files })
        });
        const data = await response.json();
        
        if (data.success) {
            showToast((getT('deleted_docs') || 'Deleted {0} documents').replace('{0}', data.deleted_count), 'success');
            showKbFiles(kbName, kbName);
            if (typeof loadKbList === 'function') loadKbList();
        } else {
            showToast(data.error || 'Failed to delete files', 'error');
        }
    } catch (e) {
        showToast('Error: ' + e.message, 'error');
    }
}

async function deleteAllKbFiles(kbName, displayName) {
    const confirmMsg = getT('confirm_delete_all_files') || 'Delete ALL files from this knowledge base? This cannot be undone.';
    if (!confirm(confirmMsg)) return;
    
    const doubleConfirmMsg = getT('confirm_delete_all_files_final') || 'Are you REALLY sure? Type the KB name to confirm:';
    const userInput = prompt(doubleConfirmMsg + '\n\n' + displayName);
    if (userInput !== displayName) {
        if (userInput !== null) showToast(getT('name_mismatch') || 'Name does not match', 'warning');
        return;
    }
    
    try {
        const filesResponse = await fetch(`/api/kb/files?name=${encodeURIComponent(kbName)}`);
        const filesData = await filesResponse.json();
        
        if (filesData.success && filesData.files.length > 0) {
            const allFiles = filesData.files.map(f => f.file);
            
            const response = await fetch('/api/kb/delete-files', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: kbName, files: allFiles })
            });
            const data = await response.json();
            
            if (data.success) {
                showToast((getT('deleted_docs') || 'Deleted {0} documents').replace('{0}', data.deleted_count), 'success');
                loadKbManagerContent();
                if (typeof loadKbList === 'function') loadKbList();
            } else {
                showToast(data.error || 'Failed to delete files', 'error');
            }
        }
    } catch (e) {
        showToast('Error: ' + e.message, 'error');
    }
}

async function confirmDeleteKb(kbName, displayName) {
    const deleteFilesMsg = getT('also_delete_source_files') || 'Also delete source files?';
    const deleteFiles = confirm(deleteFilesMsg);
    
    const confirmMsg = deleteFiles 
        ? (getT('confirm_delete_kb_with_files') || 'Delete knowledge base "{0}" and all its source files?')
        : (getT('confirm_delete_kb') || 'Delete knowledge base "{0}"?');
    
    if (!confirm(confirmMsg.replace('{0}', displayName))) return;
    
    try {
        const response = await fetch('/api/kb/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: kbName, delete_files: deleteFiles })
        });
        const data = await response.json();
        
        if (data.success) {
            showToast(getT('kb_deleted') || 'Knowledge base deleted', 'success');
            loadKbManagerContent();
            if (typeof loadKbList === 'function') loadKbList();
        } else {
            showToast(data.error || 'Failed to delete knowledge base', 'error');
        }
    } catch (e) {
        showToast('Error: ' + e.message, 'error');
    }
}

// ============================================
// Literature Review Generation
// ============================================
// Knowledge Base Scope Selector
// ============================================

async function loadKbList() {
    try {
        const response = await fetch('/api/kb/list');
        const data = await response.json();
        availableKbs = data.kbs || [];
        
        // Preserve previous selection if possible, otherwise select all
        const prevSelected = new Set(selectedKbs);
        selectedKbs.clear();
        
        for (const kb of availableKbs) {
            if (prevSelected.size === 0 || prevSelected.has(kb.name)) {
                selectedKbs.add(kb.name);
            }
        }
        
        renderKbDropdownList();
        updateKbSelectionText();
    } catch (e) {
        console.error('Failed to load KB list:', e);
    }
}

function renderKbDropdownList() {
    const listEl = document.getElementById('kbDropdownList');
    if (!listEl) return;
    
    // Sort: builtin first, then user, then other
    const typeOrder = { builtin: 0, user: 1, other: 2 };
    const sorted = [...availableKbs].sort((a, b) => 
        (typeOrder[a.type] || 9) - (typeOrder[b.type] || 9)
    );
    
    const builtinLabel = getT('builtin_kb_type') || 'Built-in';
    const userLabel = getT('user_kb_type') || 'User';
    
    listEl.innerHTML = sorted.map(kb => {
        const checked = selectedKbs.has(kb.name) ? 'checked' : '';
        const badgeClass = kb.type === 'user' ? 'user' : 'builtin';
        const badgeText = kb.type === 'user' ? userLabel : builtinLabel;
        return `<label class="kb-dropdown-item">
            <input type="checkbox" ${checked} onchange="toggleKbSelection('${kb.name}')">
            <span>${escapeHtml(kb.display_name)}</span>
            <span class="kb-type-badge ${badgeClass}">${badgeText}</span>
        </label>`;
    }).join('');
}

function toggleKbDropdown() {
    const menu = document.getElementById('kbDropdownMenu');
    const isOpen = menu.classList.contains('open');
    
    if (isOpen) {
        menu.classList.remove('open');
    } else {
        menu.classList.add('open');
        // Close on outside click
        setTimeout(() => {
            document.addEventListener('click', closeKbDropdownOutside, { once: true });
        }, 0);
    }
}

function closeKbDropdownOutside(e) {
    const wrapper = document.getElementById('kbSelectorWrapper');
    if (wrapper && !wrapper.contains(e.target)) {
        document.getElementById('kbDropdownMenu').classList.remove('open');
    } else {
        // Re-attach if click was inside
        document.addEventListener('click', closeKbDropdownOutside, { once: true });
    }
}

function selectAllKbs(select) {
    selectedKbs.clear();
    if (select) {
        for (const kb of availableKbs) {
            selectedKbs.add(kb.name);
        }
    }
    renderKbDropdownList();
    updateKbSelectionText();
}

function toggleKbSelection(name) {
    if (selectedKbs.has(name)) {
        selectedKbs.delete(name);
    } else {
        selectedKbs.add(name);
    }
    updateKbSelectionText();
}

function updateKbSelectionText() {
    const el = document.getElementById('kbSelectionText');
    if (!el) return;
    
    const total = availableKbs.length;
    const selected = selectedKbs.size;
    
    if (total === 0) {
        el.textContent = '-';
    } else if (selected === total) {
        el.textContent = getT('all_kbs_selected') || 'All';
    } else if (selected === 0) {
        el.textContent = getT('none_selected') || 'None';
    } else {
        el.textContent = `${selected}/${total}`;
    }
}

// ============================================
// Strict KB Mode Toggle
// ============================================

async function updateStrictKbMode() {
    const checkbox = document.getElementById('strictKbMode');
    const strictMode = checkbox ? checkbox.checked : false;
    
    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ strict_kb_mode: strictMode })
        });
        const data = await response.json();
        if (data.success) {
            showToast(strictMode ? 'Strict KB mode enabled' : 'Strict KB mode disabled', 'success');
        }
    } catch (e) {
        console.error('Failed to update strict KB mode:', e);
        showToast('Failed to update setting', 'error');
    }
}

// ============================================
// Literature Review Generation
// ============================================

async function generateLiteratureReview() {
    // Check if any KBs are selected
    if (selectedKbs.size === 0) {
        showToast(getT('no_kb_selected') || 'Please select a knowledge base first', 'error');
        return;
    }
    
    if (isGenerating) {
        showToast('Please wait for current generation to complete', 'warning');
        return;
    }
    
    isGenerating = true;
    document.getElementById('sendBtn').style.display = 'none';
    document.getElementById('stopBtn').style.display = 'inline-block';
    
    // Add a message indicating literature review is being generated
    const headerMsg = getT('generating_lit_review') || 'Generating literature review...';
    addMessage('user', `📝 ${getT('generate_lit_review') || 'Generate Literature Review'}`);
    const assistantDiv = addMessage('assistant', '<span class="loading"></span> ' + headerMsg);
    
    try {
        const response = await fetch('/api/kb/literature-review', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                kb_names: Array.from(selectedKbs),
                language: window.SERVER_CONFIG.lang || 'en'
            })
        });
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const text = decoder.decode(value);
            const lines = text.split('\n');
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.content) {
                            fullText += data.content;
                            assistantDiv.innerHTML = renderStreamingText(fullText);
                        }
                        if (data.done || data.stopped) break;
                    } catch (e) {}
                }
            }
        }
        
        // Final render with LaTeX and markdown
        assistantDiv.innerHTML = renderMarkdown(fullText);
        renderLatex(assistantDiv);
        
        showToast(getT('lit_review_complete') || 'Literature review complete', 'success');
        
    } catch (e) {
        assistantDiv.innerHTML = 'Error: ' + e.message;
        showToast('Error generating literature review', 'error');
    }
    
    isGenerating = false;
    document.getElementById('sendBtn').style.display = 'inline-block';
    document.getElementById('stopBtn').style.display = 'none';
}
