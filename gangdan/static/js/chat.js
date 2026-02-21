// ============================================
// Chat Panel Functions
// ============================================

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
            body: JSON.stringify({ message, use_kb: useKb, use_web: useWeb })
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
