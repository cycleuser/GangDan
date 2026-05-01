// ============================================
// Terminal & AI Command Assistant
// ============================================

// Terminal functions
async function runTerminalCommand() {
    const input = document.getElementById('terminalInput');
    const cmd = input.value.trim();
    if (!cmd) return;
    
    input.value = '';
    const output = document.getElementById('terminalOutput');
    output.innerHTML += `<span class="cmd">$ ${escapeHtml(cmd)}</span>\n`;
    
    try {
        const response = await fetch('/api/terminal', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command: cmd })
        });
        const data = await response.json();
        
        if (data.stdout) {
            output.innerHTML += `<span class="stdout">${escapeHtml(data.stdout)}</span>`;
        }
        if (data.stderr) {
            output.innerHTML += `<span class="stderr">${escapeHtml(data.stderr)}</span>`;
        }
        if (data.error) {
            output.innerHTML += `<span class="stderr">Error: ${escapeHtml(data.error)}</span>\n`;
        }
    } catch (e) {
        output.innerHTML += `<span class="stderr">Error: ${escapeHtml(e.message)}</span>\n`;
    }
    
    output.scrollTop = output.scrollHeight;
}

function clearTerminal() {
    document.getElementById('terminalOutput').innerHTML = `<span class="cmd">${T.terminal_ready}</span>\n`;
}

function clearAiChat() {
    document.getElementById('aiTerminalChat').innerHTML = `
        <div class="ai-message system">
            <div class="ai-message-content">
                <p>${T.ai_cleared}</p>
                <p>${T.ai_intro}</p>
            </div>
        </div>
    `;
    // Clear all context tracking
    aiExecutionContext = [];
    aiChatHistory = [];
    lastInteractionTime = null;
}

// AI Command Assistant with full Markdown support
let aiExecutionContext = []; // Store recent command executions for context
let aiChatHistory = []; // Store AI chat history with timestamps
let lastInteractionTime = null; // Track last interaction time
const COLLAPSE_LINE_THRESHOLD = 5; // Collapse if more than 5 lines
const CONTEXT_STALE_MINUTES = 5; // Context older than 5 minutes is considered stale
const MIN_RELEVANCE_THRESHOLD = 0.3; // Minimum relevance score to use existing context

function shouldCollapse(content) {
    // Check if content has more than threshold lines or is very long
    const lines = content.split('\n').length;
    return lines > COLLAPSE_LINE_THRESHOLD || content.length > 400;
}

function addAiMessage(role, content, options = {}) {
    const chat = document.getElementById('aiTerminalChat');
    const div = document.createElement('div');
    div.className = 'ai-message ' + role;
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'ai-message-content';
    
    if (role === 'user') {
        contentDiv.textContent = content;
    } else {
        // Full markdown rendering for assistant messages
        const renderedContent = renderMarkdown(content);
        
        // Check if content should be collapsible (not for short responses or commands)
        const isLongContent = shouldCollapse(content) && !options.noCollapse;
        
        if (isLongContent) {
            const collapseId = 'collapse-' + Date.now();
            contentDiv.innerHTML = `
                <div class="collapsible-content collapsed" id="${collapseId}">
                    ${renderedContent}
                </div>
                <button class="collapse-toggle" onclick="toggleCollapse('${collapseId}', this)">
                    📖 ${T.expand_content}
                </button>
            `;
        } else {
            contentDiv.innerHTML = renderedContent;
        }
    }
    
    div.appendChild(contentDiv);
    chat.appendChild(div);
    
    // Render LaTeX if present
    if (role === 'assistant') {
        renderLatex(contentDiv);
    }
    
    chat.scrollTop = chat.scrollHeight;
    return div;
}

function toggleCollapse(id, btn) {
    const el = document.getElementById(id);
    if (el.classList.contains('collapsed')) {
        el.classList.remove('collapsed');
        btn.textContent = '📕 ' + T.collapse_content;
    } else {
        el.classList.add('collapsed');
        btn.textContent = '📖 ' + T.expand_content;
    }
}

function addAiCommandBlock(command, explanation) {
    const chat = document.getElementById('aiTerminalChat');
    const cmdId = 'aicmd-' + Date.now();
    
    const div = document.createElement('div');
    div.className = 'ai-message assistant';
    div.innerHTML = `
        <div class="ai-message-content">
            <p>${renderMarkdown(explanation)}</p>
            <div class="ai-exec-command">
                <div class="cmd-header">
                    <span>📎 ${T.cmd_drag_hint}</span>
                </div>
                <div class="cmd-code" id="${cmdId}" 
                    draggable="true" 
                    ondragstart="dragCommand(event, '${escapeHtml(command).replace(/'/g, "\\'")}')">
                    ${escapeHtml(command)}
                </div>
                <div class="cmd-actions">
                    <button class="btn-run-cmd" onclick="executeAiCommand('${escapeHtml(command).replace(/'/g, "\\'")}')">▶️ Run</button>
                    <button class="btn-copy-cmd" onclick="copyAiCommand('${escapeHtml(command).replace(/'/g, "\\'")}')">📋 Copy</button>
                    <button class="btn-auto-exec" onclick="autoExecuteAndSummarize('${escapeHtml(command).replace(/'/g, "\\'")}')">⚡ ${T.run_summarize}</button>
                </div>
            </div>
        </div>
    `;
    
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
}

function addAiExecutionResult(command, output, isError = false) {
    const chat = document.getElementById('aiTerminalChat');
    const timestamp = new Date().toLocaleTimeString();
    
    // Store in context
    aiExecutionContext.push({
        command: command,
        output: output,
        timestamp: Date.now(),
        isError: isError
    });
    
    // Keep only last 10 executions
    if (aiExecutionContext.length > 10) {
        aiExecutionContext.shift();
    }
    
    const div = document.createElement('div');
    div.className = 'ai-exec-result' + (isError ? ' error' : '');
    div.innerHTML = `
        <div class="result-header">
            ${isError ? '❌ Error' : '✅ Executed'} at ${timestamp}: <code>${escapeHtml(command)}</code>
        </div>
        <pre>${escapeHtml(output)}</pre>
    `;
    
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
}

function copyAiCommand(cmd) {
    navigator.clipboard.writeText(cmd);
    showToast('Command copied to clipboard', 'success');
}

async function executeAiCommand(cmd) {
    // Add to terminal and run
    document.getElementById('terminalInput').value = cmd;
    await runTerminalCommand();
}

async function autoExecuteAndSummarize(cmd) {
    showToast(T.executing, 'success');
    
    // Add loading message
    const loadingDiv = addAiMessage('assistant', '⏳ ' + T.executing);
    
    try {
        // Execute command
        const response = await fetch('/api/terminal', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command: cmd })
        });
        const data = await response.json();
        
        // Also show in terminal panel
        const termOutput = document.getElementById('terminalOutput');
        termOutput.innerHTML += `<span class="cmd">$ ${escapeHtml(cmd)}</span>\n`;
        if (data.stdout) {
            termOutput.innerHTML += `<span class="stdout">${escapeHtml(data.stdout)}</span>`;
        }
        if (data.stderr) {
            termOutput.innerHTML += `<span class="stderr">${escapeHtml(data.stderr)}</span>`;
        }
        termOutput.scrollTop = termOutput.scrollHeight;
        
        const output = data.stdout || data.stderr || data.error || 'No output';
        const isError = !!data.error || !!data.stderr;
        
        // Store execution result
        addAiExecutionResult(cmd, output, isError);
        
        // Remove loading message
        loadingDiv.remove();
        
        // Ask AI to summarize the result
        await summarizeExecution(cmd, output, isError);
        
    } catch (e) {
        loadingDiv.remove();
        addAiMessage('assistant', `❌ Execution error: ${e.message}`);
    }
}

async function summarizeExecution(command, output, isError) {
    if (!output || output.trim().length < 10) {
        addAiMessage('assistant', 'Command completed with no significant output.');
        return;
    }
    
    // Ask AI to summarize
    const summaryDiv = addAiMessage('assistant', '📊 ' + T.analyzing_results);
    
    try {
        const response = await fetch('/api/ai-summarize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                command: command,
                output: output,
                is_error: isError,
                language: currentLang
            })
        });
        const data = await response.json();
        
        if (data.summary) {
            summaryDiv.querySelector('.ai-message-content').innerHTML = renderMarkdown(data.summary);
            renderLatex(summaryDiv);
        } else {
            summaryDiv.querySelector('.ai-message-content').textContent = 'Could not generate summary.';
        }
    } catch (e) {
        summaryDiv.querySelector('.ai-message-content').textContent = 'Summary failed: ' + e.message;
    }
}

// Get relevant context from recent executions with time awareness
function getRelevantContext(query) {
    const now = Date.now();
    const staleThreshold = CONTEXT_STALE_MINUTES * 60 * 1000;
    const keywords = query.toLowerCase().split(/\s+/).filter(w => w.length > 2);
    let relevantContext = [];
    
    for (const exec of aiExecutionContext) {
        // Check if context is too old
        const age = now - exec.timestamp;
        const isFresh = age < staleThreshold;
        const timeFactor = isFresh ? 1.0 : Math.max(0.3, 1 - (age / (staleThreshold * 3)));
        
        const combined = (exec.command + ' ' + exec.output).toLowerCase();
        const matches = keywords.filter(kw => combined.includes(kw));
        
        if (matches.length > 0) {
            const baseRelevance = matches.length / keywords.length;
            relevantContext.push({
                ...exec,
                relevance: baseRelevance * timeFactor,
                isFresh: isFresh,
                ageMinutes: Math.round(age / 60000)
            });
        }
    }
    
    // Sort by relevance (time-weighted) and recency
    relevantContext.sort((a, b) => {
        if (b.relevance !== a.relevance) return b.relevance - a.relevance;
        return b.timestamp - a.timestamp;
    });
    
    return relevantContext.slice(0, 3); // Top 3 most relevant
}

// Check if we should regenerate command based on context freshness
function shouldRegenerateCommand(query, relevantExecs) {
    // If no previous context, always generate new
    if (relevantExecs.length === 0) {
        return { regenerate: true, reason: 'no_context' };
    }
    
    // Check if context is too old
    const now = Date.now();
    const staleThreshold = CONTEXT_STALE_MINUTES * 60 * 1000;
    const latestExec = relevantExecs[0];
    const age = now - latestExec.timestamp;
    
    if (age > staleThreshold) {
        return { 
            regenerate: true, 
            reason: 'stale',
            message: `${T.context_stale} (${Math.round(age / 60000)} ${T.min_ago})`
        };
    }
    
    // Check relevance score
    const maxRelevance = Math.max(...relevantExecs.map(e => e.relevance));
    if (maxRelevance < MIN_RELEVANCE_THRESHOLD) {
        return { 
            regenerate: true, 
            reason: 'low_relevance',
            message: T.context_low_match
        };
    }
    
    // Check if last chat was too long ago
    if (lastInteractionTime && (now - lastInteractionTime > staleThreshold)) {
        return {
            regenerate: true,
            reason: 'session_stale',
            message: T.context_session_stale
        };
    }
    
    return { 
        regenerate: false, 
        reason: 'valid_context',
        relevance: maxRelevance,
        freshness: latestExec.isFresh
    };
}

// AI Command Assistant
function getTerminalContext() {
    // Get the last few commands and their output from the terminal
    const terminalOutput = document.getElementById('terminalOutput');
    const text = terminalOutput.innerText || terminalOutput.textContent;
    // Get last 2000 chars of terminal context
    return text.slice(-2000);
}

async function askAiCommand() {
    const input = document.getElementById('aiTerminalInput');
    const query = input.value.trim();
    if (!query) return;
    
    input.value = '';
    
    // Add user message with markdown support
    addAiMessage('user', query);
    
    // Store in chat history with timestamp
    aiChatHistory.push({ role: 'user', content: query, timestamp: Date.now() });
    
    // Get terminal context
    const terminalContext = getTerminalContext();
    
    // Get relevant execution context
    const relevantExecs = getRelevantContext(query);
    
    // Check if we should regenerate command
    const regenCheck = shouldRegenerateCommand(query, relevantExecs);
    
    // Show appropriate thinking indicator
    let thinkingMsg = '💭 ' + T.analyzing;
    if (regenCheck.regenerate && regenCheck.reason === 'stale') {
        thinkingMsg = '💭 ' + T.context_stale;
    } else if (regenCheck.regenerate && regenCheck.reason === 'low_relevance') {
        thinkingMsg = '💭 ' + T.context_low_match;
    } else if (regenCheck.regenerate && regenCheck.reason === 'session_stale') {
        thinkingMsg = '💭 ' + T.context_session_stale;
    } else if (!regenCheck.regenerate && relevantExecs.length > 0) {
        thinkingMsg = '💭 ' + T.context_found;
    }
    const thinkingDiv = addAiMessage('assistant', thinkingMsg);
    
    // Build execution context only if relevant and fresh
    let execContext = '';
    let contextInfo = '';
    
    if (!regenCheck.regenerate && relevantExecs.length > 0) {
        execContext = '\n\nRECENT RELEVANT EXECUTIONS (use this context):\n';
        for (const exec of relevantExecs) {
            const ageStr = exec.ageMinutes < 1 ? '<1 min' : `${exec.ageMinutes} ${T.min_ago}`;
            execContext += `\n[${ageStr}] Command: ${exec.command}\nOutput (truncated): ${exec.output.slice(0, 500)}\n---`;
        }
        contextInfo = `\n\nCONTEXT STATUS: Using fresh context (relevance: ${Math.round(regenCheck.relevance * 100)}%)`;
    } else {
        contextInfo = `\n\nCONTEXT STATUS: ${regenCheck.reason === 'no_context' ? 'No previous context' : 'Regenerating due to: ' + regenCheck.reason}. Generate new command.`;
    }
    
    try {
        const response = await fetch('/api/ai-command', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                query, 
                terminal_context: terminalContext + execContext + contextInfo,
                chat_history: aiChatHistory.slice(-6),
                force_regenerate: regenCheck.regenerate,
                context_status: regenCheck,
                language: currentLang
            })
        });
        const data = await response.json();
        
        // Remove thinking indicator
        thinkingDiv.remove();
        
        // Update last interaction time
        lastInteractionTime = Date.now();
        
        if (data.command) {
            // Show context status if relevant
            if (!regenCheck.regenerate && relevantExecs.length > 0) {
                addAiMessage('assistant', `📋 ${T.based_on_history} (${relevantExecs.length}) - ${relevantExecs[0].ageMinutes || '<1'} ${T.min_ago}`, {noCollapse: true});
            }
            
            // Add command block with execution options
            addAiCommandBlock(data.command, data.explanation);
            
            // Store in chat history with timestamp
            aiChatHistory.push({ 
                role: 'assistant', 
                content: `Command: ${data.command}\nExplanation: ${data.explanation}`,
                timestamp: Date.now()
            });
        } else if (data.response) {
            // General response (no command needed)
            addAiMessage('assistant', data.response);
            aiChatHistory.push({ role: 'assistant', content: data.response, timestamp: Date.now() });
        } else {
            addAiMessage('assistant', '❌ ' + (data.error || 'Failed to process request'));
        }
        
    } catch (e) {
        thinkingDiv.remove();
        addAiMessage('assistant', '❌ Error: ' + e.message);
    }
    
    // Keep chat history limited
    if (aiChatHistory.length > 20) {
        aiChatHistory = aiChatHistory.slice(-20);
    }
}

// Drag and drop for commands
function dragCommand(event, cmd) {
    event.dataTransfer.setData('text/plain', cmd);
    event.dataTransfer.effectAllowed = 'copy';
}

function allowDrop(event) {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
    event.target.style.borderColor = '#66bb6a';
    event.target.style.boxShadow = '0 0 10px rgba(102,187,106,0.5)';
}

function handleDragLeave(event) {
    event.target.style.borderColor = '#4fc3f7';
    event.target.style.boxShadow = 'none';
}

function dropCommand(event) {
    event.preventDefault();
    const cmd = event.dataTransfer.getData('text/plain');
    document.getElementById('terminalInput').value = cmd;
    event.target.style.borderColor = '#4fc3f7';
    event.target.style.boxShadow = 'none';
    showToast(T.cmd_dropped, 'success');
}

function useAiCommand(cmd) {
    document.getElementById('terminalInput').value = cmd;
    showToast('Command copied to terminal', 'success');
}
