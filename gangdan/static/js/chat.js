// ============================================
// Chat Panel Functions
// ============================================

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

async function stopGeneration() {
    await fetch('/api/stop', { method: 'POST' });
    showToast(T.generation_stopped);
}

async function clearChat() {
    await fetch('/api/clear', { method: 'POST' });
    document.getElementById('chatMessages').innerHTML = '';
    showToast('Cleared');
}

async function exportChat() {
    const response = await fetch('/api/export');
    const data = await response.json();
    
    const blob = new Blob([data.content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = data.filename;
    a.click();
    URL.revokeObjectURL(url);
}

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
