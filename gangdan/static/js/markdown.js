// ============================================
// Markdown & LaTeX Rendering
// ============================================

let codeBlockId = 0;

function renderStreamingText(content) {
    // Safe renderer for partial/streaming content - no placeholder pattern
    // Avoids %%CODEBLOCK%% issues with incomplete code blocks during SSE
    let html = escapeHtml(content);
    // Render complete code blocks directly (no extraction/restoration)
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (match, lang, code) => {
        const blockId = 'stream-code-' + (++codeBlockId);
        return `<div class="code-block"><div class="code-block-header"><span class="lang">${lang || 'code'}</span></div><pre><code id="${blockId}">${code}</code></pre></div>`;
    });
    // Bold
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    // Inline code
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Line breaks
    html = html.replace(/\n/g, '<br>');
    return html;
}

function renderMarkdown(content) {
    // First, protect code blocks and LaTeX from other processing
    const codeBlocks = [];
    const latexBlocks = [];
    
    // Extract and protect code blocks
    content = content.replace(/```(\w*)\n([\s\S]*?)```/g, (match, lang, code) => {
        const id = codeBlocks.length;
        codeBlocks.push({ lang, code });
        return `%%CODEBLOCK${id}%%`;
    });
    
    // Extract and protect LaTeX block formulas ($$...$$)
    content = content.replace(/\$\$([\s\S]*?)\$\$/g, (match, formula) => {
        const id = latexBlocks.length;
        latexBlocks.push({ formula, block: true });
        return `%%LATEX${id}%%`;
    });
    
    // Extract and protect LaTeX inline formulas ($...$)
    content = content.replace(/\$([^$\n]+?)\$/g, (match, formula) => {
        const id = latexBlocks.length;
        latexBlocks.push({ formula, block: false });
        return `%%LATEX${id}%%`;
    });
    
    // Render tables
    content = renderTables(content);
    
    // Render other markdown elements
    content = renderInlineMarkdown(content);
    
    // Restore code blocks with enhanced rendering
    content = content.replace(/%%CODEBLOCK(\d+)%%/g, (match, id) => {
        const { lang, code } = codeBlocks[parseInt(id)];
        const blockId = 'code-' + (++codeBlockId);
        const canRun = ['python', 'py', 'javascript', 'js', 'node', 'bash', 'sh', 'shell'].includes((lang || '').toLowerCase());
        
        return `<div class="code-block" id="${blockId}-container">
            <div class="code-block-header">
                <span class="lang">${lang || 'code'}</span>
                <div class="actions">
                    <button class="btn-copy" onclick="copyCode('${blockId}')">📋 Copy</button>
                    ${canRun ? `<button class="btn-run" onclick="runCodeBlock('${blockId}', '${lang}')">▶️ Run</button>` : ''}
                </div>
            </div>
            <pre><code id="${blockId}">${escapeHtml(code)}</code></pre>
        </div>`;
    });
    
    // Restore LaTeX formulas
    content = content.replace(/%%LATEX(\d+)%%/g, (match, id) => {
        const { formula, block } = latexBlocks[parseInt(id)];
        if (block) {
            return `<div class="math-block" data-latex="${escapeHtml(formula)}">$$${escapeHtml(formula)}$$</div>`;
        } else {
            return `<span class="math-inline" data-latex="${escapeHtml(formula)}">$${escapeHtml(formula)}$</span>`;
        }
    });
    
    return content;
}

function renderTables(text) {
    // Match markdown tables
    const tableRegex = /^(\|.+\|\r?\n)(\|[-:| ]+\|\r?\n)((\|.+\|\r?\n?)+)/gm;
    
    return text.replace(tableRegex, (match, headerRow, separatorRow, bodyRows) => {
        // Parse header
        const headers = headerRow.trim().split('|').filter(c => c.trim());
        
        // Parse alignment from separator
        const alignments = separatorRow.trim().split('|').filter(c => c.trim()).map(cell => {
            cell = cell.trim();
            if (cell.startsWith(':') && cell.endsWith(':')) return 'center';
            if (cell.endsWith(':')) return 'right';
            return 'left';
        });
        
        // Parse body rows
        const rows = bodyRows.trim().split('\n').filter(r => r.trim());
        
        let html = '<table><thead><tr>';
        headers.forEach((h, i) => {
            const align = alignments[i] || 'left';
            html += `<th style="text-align:${align}">${escapeHtml(h.trim())}</th>`;
        });
        html += '</tr></thead><tbody>';
        
        rows.forEach(row => {
            const cells = row.split('|').filter(c => c !== '');
            html += '<tr>';
            cells.forEach((cell, i) => {
                const align = alignments[i] || 'left';
                html += `<td style="text-align:${align}">${escapeHtml(cell.trim())}</td>`;
            });
            html += '</tr>';
        });
        
        html += '</tbody></table>';
        return html;
    });
}

function renderInlineMarkdown(text) {
    return text
        // Blockquotes
        .replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>')
        // Horizontal rule
        .replace(/^---$/gm, '<hr>')
        .replace(/^\*\*\*$/gm, '<hr>')
        // Headers
        .replace(/^#### (.+)$/gm, '<h5>$1</h5>')
        .replace(/^### (.+)$/gm, '<h4>$1</h4>')
        .replace(/^## (.+)$/gm, '<h3>$1</h3>')
        .replace(/^# (.+)$/gm, '<h2>$1</h2>')
        // Bold and italic
        .replace(/\*\*\*([^*]+)\*\*\*/g, '<strong><em>$1</em></strong>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/\*([^*]+)\*/g, '<em>$1</em>')
        .replace(/__([^_]+)__/g, '<strong>$1</strong>')
        .replace(/_([^_]+)_/g, '<em>$1</em>')
        // Strikethrough
        .replace(/~~([^~]+)~~/g, '<del>$1</del>')
        // Inline code
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        // Links
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" style="color:#4fc3f7">$1</a>')
        // Unordered lists
        .replace(/^[\*\-] (.+)$/gm, '<li>$1</li>')
        // Ordered lists
        .replace(/^\d+\. (.+)$/gm, '<li>$1</li>')
        // Line breaks
        .replace(/\n/g, '<br>');
}

function escapeHtml(text) {
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function renderLatex(element) {
    // Render LaTeX in the element using KaTeX
    if (typeof renderMathInElement !== 'undefined') {
        renderMathInElement(element, {
            delimiters: [
                {left: '$$', right: '$$', display: true},
                {left: '$', right: '$', display: false},
                {left: '\\[', right: '\\]', display: true},
                {left: '\\(', right: '\\)', display: false}
            ],
            throwOnError: false
        });
    }
}
