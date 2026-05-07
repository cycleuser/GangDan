// ============================================
// Chat Panel Functions
// ============================================

var isGenerating = false;
var availableKbs = [];
var selectedKbs = new Set();
var chatHistory = [];

// ============================================
// Chat Scroll Controller - Prevents layout jumping
// ============================================

var ChatScrollController = {
    NEAR_BOTTOM_THRESHOLD: 100,
    _container: null,
    _pendingUpdate: false,
    
    getContainer: function() {
        if (!this._container) {
            this._container = document.getElementById('chatMessages');
        }
        return this._container;
    },
    
    isNearBottom: function() {
        var container = this.getContainer();
        if (!container) return true;
        return container.scrollHeight - container.scrollTop - container.clientHeight < this.NEAR_BOTTOM_THRESHOLD;
    },
    
    scrollToBottom: function(smooth) {
        var container = this.getContainer();
        if (!container) return;
        
        if (smooth === true) {
            container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
        } else {
            container.scrollTop = container.scrollHeight;
        }
    },
    
    onContentUpdate: function() {
        if (this.isNearBottom()) {
            this.scrollToBottom(false);
        }
    },
    
    // Batched update using requestAnimationFrame
    batchedUpdate: function(element, renderFn) {
        var self = this;
        return function(content) {
            if (!self._pendingUpdate) {
                self._pendingUpdate = true;
                requestAnimationFrame(function() {
                    renderFn(content);
                    self.onContentUpdate();
                    self._pendingUpdate = false;
                });
            }
        };
    }
};

function addMessage(role, content) {
    var div = document.createElement('div');
    div.className = 'message ' + role;
    div.innerHTML = renderMarkdown(content);
    document.getElementById('chatMessages').appendChild(div);
    renderLatex(div);
    ChatScrollController.scrollToBottom(true);
    if (role !== 'system') {
        chatHistory.push({ role: role, content: content });
    }
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
        const useImages = document.getElementById('useImages')?.checked || false;
        const outputWordLimit = parseInt(document.getElementById('outputWordLimit')?.value) || 0;
        
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                message, 
                use_kb: useKb, 
                use_web: useWeb,
                use_images: useImages,
                output_word_limit: outputWordLimit,
                kb_scope: useKb ? Array.from(selectedKbs) : null 
            })
        });
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';
        let hasImages = false;
        
        // Create batched update function for streaming
        var batchedRenderer = ChatScrollController.batchedUpdate(assistantDiv, function(text) {
            assistantDiv.innerHTML = renderStreamingText(text);
        });
        
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
                            batchedRenderer(fullText);
                        }
                        // Handle images in response
                        if (data.images && Array.isArray(data.images)) {
                            hasImages = true;
                            const imageContainer = document.createElement('div');
                            imageContainer.className = 'chat-images';
                            imageContainer.style.cssText = 'margin:10px 0; padding:10px; background:rgba(79,195,247,0.1); border-left:3px solid var(--primary); border-radius:4px;';
                            
                            const title = document.createElement('p');
                            title.style.cssText = 'margin:0 0 10px 0; font-weight:600; color:var(--primary);';
                            title.textContent = '📷 相关图片：';
                            imageContainer.appendChild(title);
                            
                            const grid = document.createElement('div');
                            grid.style.cssText = 'display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:10px;';
                            
                            data.images.forEach(img => {
                                const imgCard = document.createElement('div');
                                imgCard.style.cssText = 'cursor:pointer; background:var(--bg-secondary); border-radius:4px; overflow:hidden;';
                                imgCard.onclick = () => showChatImageModal(img);
                                
                                const imgUrl = `/api/kb/image/${encodeURIComponent(img.kb)}/${img.path}`;
                                imgCard.innerHTML = `
                                    <img src="${imgUrl}" alt="${img.alt_text}" style="width:100%; height:100px; object-fit:cover;">
                                    <p style="margin:5px; font-size:0.75em; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${img.alt_text || '图片'}</p>
                                    <p style="margin:0 0 5px 5px; font-size:0.7em; color:var(--text-muted);">📄 ${img.source_file}</p>
                                `;
                                grid.appendChild(imgCard);
                            });
                            
                            imageContainer.appendChild(grid);
                            assistantDiv.appendChild(imageContainer);
                        }
                        if (data.done || data.stopped) break;
                    } catch (e) {}
                }
            }
        }
        
        // Final render with LaTeX and markdown
        assistantDiv.innerHTML = renderMarkdown(fullText);
        renderLatex(assistantDiv);
        ChatScrollController.scrollToBottom(false);
        
        // Update chatHistory with final assistant text
        if (chatHistory.length > 0 && chatHistory[chatHistory.length - 1].role === 'assistant' && chatHistory[chatHistory.length - 1].content === '<span class="loading"></span>') {
            chatHistory[chatHistory.length - 1].content = fullText;
        } else {
            chatHistory.push({ role: 'assistant', content: fullText });
        }
        
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
    renderKbDropdownList();
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
    
    const headerMsg = getT('generating_lit_review') || 'Generating literature review...';
    addMessage('user', `📝 ${getT('generate_lit_review') || 'Generate Literature Review'}`);
    
    // Create progress header
    const progressBar = `<div class="lit-progress" style="margin-bottom:10px; padding:8px 12px; background:var(--accent-soft); border-radius:6px; border:1px solid var(--accent-border); font-size:0.85em;">
        <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
            <span>📊 <span id="litProgressLabel">${headerMsg}</span></span>
            <span style="color:var(--text-muted);"><span id="litTokens">0</span> tokens | <span id="litSpeed">0</span> t/s | <span id="litSections">0</span> sections</span>
        </div>
        <div style="background:var(--bg-tertiary); border-radius:4px; height:4px; overflow:hidden;">
            <div id="litProgressBar" style="background:var(--accent); height:100%; width:0%; transition:width 0.3s;"></div>
        </div>
        <div style="font-size:0.75em; color:var(--text-muted); margin-top:4px;" id="litModelInfo"></div>
    </div>`;
    
    const assistantDiv = addMessage('assistant', progressBar + '<span class="loading"></span> ' + headerMsg);
    const startTime = Date.now();
    
    try {
        const response = await fetch('/api/kb/literature-review', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                kb_names: Array.from(selectedKbs),
                language: window.SERVER_CONFIG.lang || 'en',
                output_size: 'medium'
            })
        });
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';
        let totalTokens = 0, totalSections = 0, totalSources = 0;
        
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
                            assistantDiv.innerHTML = progressBar + renderStreamingText(fullText);
                        }
                        if (data.type === 'context') {
                            totalTokens = data.tokens || 0;
                            totalSections = data.sections || 0;
                            totalSources = data.sources || 0;
                            updateLitProgress(totalTokens, totalSections, totalSources, startTime);
                        }
                        if (data.model) {
                            document.getElementById('litModelInfo').textContent = '🤖 Model: ' + data.model;
                        }
                        if (data.done || data.stopped) break;
                    } catch (e) {}
                }
            }
        }
        
        assistantDiv.innerHTML = renderMarkdown(fullText);
        renderLatex(assistantDiv);
        showToast(getT('lit_review_complete') || 'Literature review complete', 'success');
        
    } catch (e) {
        assistantDiv.innerHTML = progressBar + '<p style="color:var(--danger);">Error: ' + e.message + '</p>';
        showToast('Error generating literature review', 'error');
    }
    
    isGenerating = false;
    document.getElementById('sendBtn').style.display = 'inline-block';
    document.getElementById('stopBtn').style.display = 'none';
}

function updateLitProgress(tokens, sections, sources, startTime) {
    const elapsed = (Date.now() - startTime) / 1000;
    const speed = elapsed > 0 ? Math.round(tokens / elapsed) : 0;
    const el = (n, id) => { const e = document.getElementById(id); if (e) e.textContent = n; };
    el(tokens, 'litTokens');
    el(speed, 'litSpeed');
    el(sections, 'litSections');

    // Simple progress based on sections (most reviews have 4-6 sections)
    const maxSections = Math.max(sections || 1, 5);
    const pct = Math.min(90, Math.round((sections || 0) / maxSections * 100));
    const pb = document.getElementById('litProgressBar');
    if (pb) pb.style.width = pct + '%';

    if (sections >= 1) {
        const label = document.getElementById('litProgressLabel');
        if (label) label.textContent = (getT('writing_section') || 'Writing section') + ' ' + sections + ' of ~' + maxSections;
    }
}

async function generatePaper() {
    if (selectedKbs.size === 0) {
        showToast(getT('no_kb_selected') || 'Please select a knowledge base first', 'error');
        return;
    }
    
    if (isGenerating) {
        showToast('Please wait for current generation to complete', 'warning');
        return;
    }
    
    let userInput = document.getElementById('chatInput')?.value?.trim() || '';
    if (!userInput) {
        showToast((getT('paper_title') || 'Paper title') + ': ' + (getT('please_enter_topic') || 'Please enter a topic in the chat input'), 'warning');
        return;
    }
    
    // AI Refine: translate & expand query if checked
    const aiRefine = document.getElementById('useAiRefinePaper')?.checked;
    if (aiRefine) {
        try {
            const resp = await fetch('/api/kb/refine-query', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: userInput, context: 'academic paper title' })
            });
            const data = await resp.json();
            if (data.success && data.refined_query && data.refined_query !== userInput) {
                userInput = data.refined_query;
                showToast((getT('query_refined') || 'Topic refined') + ': ' + userInput, 'success');
            }
        } catch (e) {}
    }
    
    isGenerating = true;
    document.getElementById('sendBtn').style.display = 'none';
    document.getElementById('stopBtn').style.display = 'inline-block';
    
    addMessage('user', `✍️ ${getT('paper_writer') || '撰写论文'}: ${userInput}`);
    const assistantDiv = addMessage('assistant', '<span class="loading"></span> ' + (getT('generating_paper') || '正在撰写论文...'));
    
    try {
        const response = await fetch('/api/kb/paper', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                kb_names: Array.from(selectedKbs),
                topic: userInput,
                language: currentLang || 'zh'
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
        
        assistantDiv.innerHTML = renderMarkdown(fullText);
        renderLatex(assistantDiv);
        
    } catch (e) {
        assistantDiv.innerHTML = 'Error: ' + e.message;
        showToast('Error generating paper', 'error');
    }
    
    isGenerating = false;
    document.getElementById('sendBtn').style.display = 'inline-block';
    document.getElementById('stopBtn').style.display = 'none';
}

// Show image modal from chat
function showChatImageModal(img) {
    const modal = document.createElement('div');
    modal.id = 'chatImageModal';
    modal.style.cssText = 'display:block; position:fixed; z-index:1000; left:0; top:0; width:100%; height:100%; background:rgba(0,0,0,0.8);';
    modal.onclick = () => modal.remove();
    
    const imgUrl = `/api/kb/image/${encodeURIComponent(img.kb)}/${img.path}`;
    
    modal.innerHTML = `
        <div style="position:relative; background:transparent; margin:2% auto; padding:0; width:90%; max-width:1200px; max-height:90vh; overflow:auto;" onclick="event.stopPropagation()">
            <span onclick="this.closest('#chatImageModal').remove()" style="position:absolute; top:10px; right:25px; color:#f1f1f1; font-size:35px; font-weight:bold; cursor:pointer; z-index:1001;">&times;</span>
            <div style="display:flex; flex-direction:column; align-items:center;">
                <img src="${imgUrl}" alt="${img.alt_text || '图片'}" style="max-width:100%; max-height:70vh; object-fit:contain; border-radius:8px;">
                <div style="background:var(--bg-secondary); padding:15px; border-radius:8px; margin-top:15px; width:100%; max-width:800px;">
                    <h4 style="margin:0 0 10px 0; color:var(--text-primary);">${img.alt_text || '无标题'}</h4>
                    <p style="margin:5px 0; color:var(--text-muted);">
                        <strong>源文件：</strong> ${img.source_file || '未知'}
                    </p>
                    <p style="margin:5px 0; color:var(--text-muted);">
                        <strong>文件名：</strong> ${img.name || img.path}
                    </p>
                    <p style="margin:5px 0; color:var(--text-muted);">
                        <strong>知识库：</strong> ${img.kb}
                    </p>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
}

// Close chat image modal with Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const chatModal = document.getElementById('chatImageModal');
        if (chatModal) chatModal.remove();
    }
});

// ============================================
// Stop and Clear Functions
// ============================================

function stopGeneration() {
    console.log('[Chat] Stop button clicked');
    
    // Call stop API
    fetch('/api/stop', { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            console.log('[Chat] Stop response:', data);
            if (data.success) {
                // Update UI
                isGenerating = false;
                document.getElementById('sendBtn').style.display = 'inline-block';
                document.getElementById('stopBtn').style.display = 'none';
                
                // Add stopped message
                const chatMessages = document.getElementById('chatMessages');
                const stoppedMsg = document.createElement('div');
                stoppedMsg.className = 'message assistant';
                stoppedMsg.innerHTML = '<em>⏹️ Generation stopped</em>';
                chatMessages.appendChild(stoppedMsg);
                ChatScrollController.scrollToBottom(false);
                
                showToast(getT('stopped') || 'Generation stopped', 'success');
            }
        })
        .catch(err => {
            console.error('[Chat] Stop failed:', err);
            showToast('Failed to stop generation', 'error');
        });
}

function clearChat() {
    console.log('[Chat] Clear button clicked');
    
    if (!confirm(getT('confirm_clear_chat') || 'Clear all chat messages?')) {
        return;
    }
    
    // Clear UI
    const chatMessages = document.getElementById('chatMessages');
    chatMessages.innerHTML = '';
    chatHistory = [];
    
    // Clear conversation on server
    fetch('/api/clear', { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            console.log('[Chat] Clear response:', data);
            if (data.success) {
                showToast(getT('chat_cleared') || 'Chat cleared', 'success');
            }
        })
        .catch(err => {
            console.error('[Chat] Clear failed:', err);
            showToast('Failed to clear chat', 'error');
        });
}

// Add translations for stop/clear
const additionalTranslations = {
    zh: {
        stopped: '已停止生成',
        confirm_clear_chat: '确定要清除所有聊天记录吗？',
        chat_cleared: '聊天记录已清除',
    },
    en: {
        stopped: 'Generation stopped',
        confirm_clear_chat: 'Clear all chat messages?',
        chat_cleared: 'Chat cleared',
    }
};

// Merge with existing getT function
const originalGetT = window.getT || (key => key);
window.getT = function(key) {
    const lang = window.SERVER_CONFIG?.lang || 'en';
    return additionalTranslations[lang]?.[key] || originalGetT(key) || key;
};

// ============================================
// Export and Save/Load Conversation Functions
// ============================================

function getChatHistory() {
    return chatHistory.filter(m => m.role === 'user' || m.role === 'assistant');
}

async function exportChat() {
    console.log('[Chat] Export button clicked');
    
    const messages = getChatHistory();
    if (messages.length === 0) {
        showToast(getT('export_failed') || 'No messages to export', 'error');
        return;
    }

    try {
        const now = new Date();
        const timestamp = now.toISOString().replace('T', ' ').slice(0, 19);
        
        let mdContent = `# ${getT('app_title') || 'GangDan'} - Chat Export\n*Exported: ${timestamp}*\n\n---\n\n`;
        
        for (const msg of messages) {
            const role = msg.role === 'user' ? '🧑 User' : '🤖 Assistant';
            mdContent += `### ${role}\n\n${msg.content}\n\n---\n\n`;
        }

        const conversationData = {
            version: "1.0",
            app: "GangDan",
            exported_at: now.toISOString().slice(0, 19),
            messages: messages,
        };
        mdContent += `\n<!-- GANGDAN_CONVERSATION_DATA\n${JSON.stringify(conversationData)}\nEND_GANGDAN_CONVERSATION_DATA -->`;

        const filename = `chat_export_${now.toISOString().slice(0, 10).replace(/-/g, '')}_${now.toTimeString().slice(0, 8).replace(/:/g, '')}.md`;
        const blob = new Blob([mdContent], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        showToast(getT('export_success') || 'Chat exported successfully', 'success');
    } catch (err) {
        console.error('[Chat] Export failed:', err);
        showToast('Failed to export chat', 'error');
    }
}

async function saveConversation() {
    console.log('[Chat] Save conversation button clicked');
    
    const messages = getChatHistory();
    if (messages.length === 0) {
        showToast(getT('save_failed') || 'No messages to save', 'error');
        return;
    }

    try {
        const now = new Date();
        const conversationData = {
            version: "1.0",
            app: "GangDan",
            exported_at: now.toISOString().slice(0, 19),
            messages: messages,
        };

        const filename = `conversation_${now.toISOString().slice(0, 10).replace(/-/g, '')}_${now.toTimeString().slice(0, 8).replace(/:/g, '')}.json`;
        const blob = new Blob([JSON.stringify(conversationData, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        showToast(getT('save_success') || 'Conversation saved successfully', 'success');
    } catch (err) {
        console.error('[Chat] Save failed:', err);
        showToast('Failed to save conversation', 'error');
    }
}

function triggerLoadConversation() {
    console.log('[Chat] Trigger load conversation');
    const fileInput = document.getElementById('conversationFileInput');
    if (fileInput) {
        fileInput.click();
    } else {
        console.error('[Chat] File input not found');
        showToast('File input not found', 'error');
    }
}

async function loadConversation(input) {
    console.log('[Chat] Load conversation triggered');
    
    if (!input || !input.files || input.files.length === 0) {
        console.log('[Chat] No file selected');
        return;
    }
    
    const file = input.files[0];
    console.log('[Chat] Loading file:', file.name);
    
    const isJson = file.name.endsWith('.json');
    const isMd = file.name.endsWith('.md');
    
    if (!isJson && !isMd) {
        showToast(getT('invalid_file_type') || 'Please select a JSON or MD file', 'error');
        input.value = '';
        return;
    }
    
    try {
        const text = await file.text();
        let conversationData = null;
        
        if (isJson) {
            const fileContent = JSON.parse(text);
            
            if (fileContent.messages && Array.isArray(fileContent.messages)) {
                conversationData = fileContent;
            } else if (fileContent.conversation && fileContent.conversation.messages) {
                conversationData = fileContent.conversation;
            } else if (Array.isArray(fileContent)) {
                conversationData = { messages: fileContent };
            } else {
                showToast(getT('invalid_conversation_file') || 'Invalid conversation file format', 'error');
                input.value = '';
                return;
            }
        } else if (isMd) {
            const dataMatch = text.match(/<!--\s*GANGDAN_CONVERSATION_DATA\s*\n([\s\S]*?)\nEND_GANGDAN_CONVERSATION_DATA\s*-->/);
            if (!dataMatch) {
                showToast(getT('invalid_conversation_file') || 'No embedded conversation data found in MD file', 'error');
                input.value = '';
                return;
            }
            try {
                const parsed = JSON.parse(dataMatch[1]);
                if (parsed.messages && Array.isArray(parsed.messages)) {
                    conversationData = parsed;
                } else {
                    showToast(getT('invalid_conversation_file') || 'Invalid embedded data in MD file', 'error');
                    input.value = '';
                    return;
                }
            } catch (parseErr) {
                showToast(getT('invalid_json') || 'Invalid embedded data in MD file', 'error');
                input.value = '';
                return;
            }
        }
        
        const response = await fetch('/api/load-conversation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ conversation: conversationData })
        });
        
        const data = await response.json();
        
        if (data.success) {
            const chatMessages = document.getElementById('chatMessages');
            chatMessages.innerHTML = '';
            
            for (const msg of conversationData.messages) {
                const div = document.createElement('div');
                div.className = 'message ' + msg.role;
                div.innerHTML = renderMarkdown(msg.content);
                chatMessages.appendChild(div);
                renderLatex(div);
            }
            
            ChatScrollController.scrollToBottom(false);
            
            const loadedMsg = (getT('conversation_loaded') || 'Loaded {0} messages').replace('{0}', data.message_count || conversationData.messages.length);
            showToast(loadedMsg, 'success');
        } else {
            showToast(data.error || getT('load_failed') || 'Failed to load conversation', 'error');
        }
    } catch (err) {
        console.error('[Chat] Load failed:', err);
        if (err instanceof SyntaxError) {
            showToast(getT('invalid_json') || 'Invalid JSON file', 'error');
        } else {
            showToast('Failed to load conversation: ' + err.message, 'error');
        }
    }
    
    input.value = '';
}

// Translation for generated text
async function translateLastMessage() {
    const lang = document.getElementById('translateLang')?.value;
    if (!lang) {
        showToast('Please select a target language first', 'warning');
        return;
    }

    const msgs = document.getElementById('chatMessages').querySelectorAll('.message.assistant');
    if (msgs.length === 0) {
        showToast('No generated text to translate', 'warning');
        return;
    }

    const lastMsg = msgs[msgs.length - 1];
    const originalHTML = lastMsg.innerHTML;

    // Check if it's already a translation
    if (lastMsg.dataset.translated === 'true') {
        if (!confirm((getT('retranslate_confirm') || 'This message was already translated. Translate again?'))) return;
    }

    lastMsg.innerHTML = '<span class="loading"></span> ' + (getT('translating') || 'Translating...');
    const translateBtn = document.getElementById('translateBtn');
    if (translateBtn) translateBtn.disabled = true;

    try {
        const resp = await fetch('/api/kb/translate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: originalHTML, target_lang: lang })
        });
        const data = await resp.json();

        if (data.success) {
            lastMsg.innerHTML = renderMarkdown(data.translated_text);
            renderLatex(lastMsg);
            lastMsg.dataset.translated = 'true';
            lastMsg.dataset.originalText = originalHTML;
            showToast((getT('translation_complete') || 'Translation complete') + ' 🎉', 'success');
        } else {
            lastMsg.innerHTML = originalHTML;
            showToast((getT('translation_failed') || 'Translation failed') + ': ' + (data.error || ''), 'error');
        }
    } catch (err) {
        lastMsg.innerHTML = originalHTML;
        showToast('Error: ' + err.message, 'error');
    }

    if (translateBtn) translateBtn.disabled = false;
}

// Initialize KB list on page load
document.addEventListener('DOMContentLoaded', function() {
    loadKbList();
});

// Advanced parameters toggle
function toggleAdvancedParams() {
    var panel = document.getElementById('advancedParamsPanel');
    if (panel) {
        panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
    }
}
