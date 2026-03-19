/* GangDan - Deep Research Module */
(function() {
    'use strict';
    var P = 'r-';
    var _inited = false;
    var isResearching = false;
    var currentReportMarkdown = '';
    var tokenEstimate = 0;
    var sectionsWritten = 0;
    var sourcesUsed = 0;
    var currentPhase = '';
    var subtopicsCompleted = 0;
    var subtopicsTotal = 0;

    function el(id) { return document.getElementById(P + id); }

    function init() {
        if (_inited) return;
        _inited = true;
        loadReports();
        el('reportActions').style.display = 'none';

        var depthSelect = document.getElementById('depthSelect');
        if (depthSelect) {
            depthSelect.addEventListener('change', function() {
                var isAuto = depthSelect.value === 'auto';
                var refiningEl = el('phase-refining');
                var refiningArrow = el('refining-arrow');
                if (refiningEl) refiningEl.style.display = isAuto ? '' : 'none';
                if (refiningArrow) refiningArrow.style.display = isAuto ? '' : 'none';
            });
        }
    }

    function updateContextMonitor(stats) {
        var monitor = document.getElementById('contextMonitor');
        if (!monitor) return;
        monitor.style.display = 'block';
        
        if (stats.tokens !== undefined) {
            tokenEstimate = stats.tokens;
            var tokenEl = document.getElementById('tokenCount');
            if (tokenEl) tokenEl.textContent = tokenEstimate.toLocaleString();
        }
        if (stats.sections !== undefined) {
            sectionsWritten = stats.sections;
            var sectionsEl = document.getElementById('sectionsWritten');
            if (sectionsEl) sectionsEl.textContent = sectionsWritten;
        }
        if (stats.sources !== undefined) {
            sourcesUsed = stats.sources;
            var sourcesEl = document.getElementById('sourcesUsed');
            if (sourcesEl) sourcesEl.textContent = sourcesUsed;
        }
    }

    function updateProgressBar() {
        var progressEl = el('progressBar');
        var progressFill = progressEl ? progressEl.querySelector('.progress-bar-fill') : null;
        
        if (!progressFill) return;
        
        var progress = 0;
        if (currentPhase === 'rephrasing') progress = 5;
        else if (currentPhase === 'planning') progress = 15;
        else if (currentPhase === 'researching') {
            if (subtopicsTotal > 0) {
                progress = 15 + Math.round((subtopicsCompleted / subtopicsTotal) * 35);
            } else {
                progress = 25;
            }
        } else if (currentPhase === 'refining') {
            progress = 55;
        } else if (currentPhase === 'reporting') {
            if (sectionsWritten > 0) {
                progress = 55 + Math.min(40, sectionsWritten * 8);
            } else {
                progress = 60;
            }
        } else if (currentPhase === 'done') {
            progress = 100;
        }
        
        progressFill.style.width = progress + '%';
    }

    function estimateTokens(text) {
        return Math.ceil(text.length / 4);
    }

    async function startResearch() {
        if (isResearching) return;
        var topic = el('topicInput').value.trim();
        if (!topic) {
            showToast(getT('enter_topic') || 'Please enter a research topic', 'error');
            return;
        }
        if (window._learningSelectedKbs.size === 0) {
            showToast(getT('no_kb_selected') || 'Please select a knowledge base', 'error');
            return;
        }

        isResearching = true;
        currentReportMarkdown = '';
        tokenEstimate = 0;
        sectionsWritten = 0;
        sourcesUsed = 0;
        subtopicsCompleted = 0;
        subtopicsTotal = 0;
        currentPhase = '';
        
        el('startBtn').disabled = true;
        el('stopBtn').style.display = 'block';
        el('reportContent').innerHTML = '<div class="research-placeholder"><span class="loading"></span> <span data-i18n="preparing_research">Preparing research...</span></div>';
        el('emptyState').style.display = 'none';
        el('phaseSection').style.display = 'block';
        el('subtopicList').innerHTML = '';
        el('reportActions').style.display = 'none';
        
        var statsEl = el('progressStats');
        if (statsEl) statsEl.textContent = '';
        
        var contextMonitor = document.getElementById('contextMonitor');
        if (contextMonitor) contextMonitor.style.display = 'block';
        updateContextMonitor({tokens: 0, sections: 0, sources: 0});

        var isAuto = el('depthSelect') ? el('depthSelect').value === 'auto' : false;
        var refiningEl = el('phase-refining');
        var refiningArrow = el('refining-arrow');
        if (refiningEl) refiningEl.style.display = isAuto ? '' : 'none';
        if (refiningArrow) refiningArrow.style.display = isAuto ? '' : 'none';
        setPhase('rephrasing');
        setStatus(getT('start_research') || 'Starting research...');

        var outputSize = document.getElementById('outputSizeSelect') ? document.getElementById('outputSizeSelect').value : 'medium';
        var depth = el('depthSelect') ? el('depthSelect').value : 'medium';
        var webSearch = el('webSearchToggle') ? el('webSearchToggle').checked : false;

        try {
            var res = await fetch('/api/learning/research/run', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    topic: topic,
                    kb_names: Array.from(window._learningSelectedKbs),
                    depth: depth,
                    web_search: webSearch,
                    output_size: outputSize
                })
            });

            if (!res.ok) {
                throw new Error('Server error: ' + res.status);
            }

            await createSSEReader(res, {
                phase: function(event) { 
                    currentPhase = event.phase;
                    setPhase(event.phase); 
                    setStatus(event.message);
                    updateProgressBar();
                    console.log('[Research] Phase:', event.phase, event.message);
                },
                status: function(event) { 
                    setStatus(event.message);
                    console.log('[Research] Status:', event.message);
                },
                subtopic: function(event) { 
                    updateSubtopic(event.data);
                    if (event.data.status === 'COMPLETED') {
                        subtopicsCompleted++;
                    }
                    if (event.data.sources) {
                        sourcesUsed = Math.max(sourcesUsed, event.data.sources.length);
                        updateContextMonitor({sources: sourcesUsed});
                    }
                    if (subtopicsTotal === 0 && event.data.status === 'PENDING') {
                        subtopicsTotal++;
                    }
                    updateProgressBar();
                    console.log('[Research] Subtopic:', event.data.title, event.data.status);
                },
                iteration: function(event) {
                    var sEl = el('progressStats');
                    if (sEl) {
                        var text = 'Iteration ' + event.current + '/' + event.max;
                        if (event.weak_count > 0) text += ' \u2022 ' + event.weak_count + ' weak subtopics';
                        if (event.sufficient) text += ' \u2022 Findings sufficient';
                        sEl.textContent = text;
                    }
                    console.log('[Research] Iteration:', event);
                },
                content: function(event) {
                    console.log('[Research] Content event, done:', event.done, 'section_done:', event.section_done, 'content length:', (event.content || '').length);
                    var contentEl = el('reportContent');
                    if (!contentEl) {
                        console.error('[Research] reportContent element not found');
                        return;
                    }
                    
                    if (event.content) {
                        currentReportMarkdown += event.content;
                        tokenEstimate = estimateTokens(currentReportMarkdown);
                        updateContextMonitor({tokens: tokenEstimate});
                        
                        // Render markdown
                        try {
                            if (typeof renderMarkdown === 'function') {
                                contentEl.innerHTML = renderMarkdown(currentReportMarkdown);
                            } else if (typeof marked !== 'undefined') {
                                contentEl.innerHTML = marked.parse(currentReportMarkdown);
                            } else {
                                contentEl.innerHTML = '<pre>' + escapeHtml(currentReportMarkdown) + '</pre>';
                            }
                        } catch (e) {
                            console.error('[Research] Markdown render error:', e);
                            contentEl.innerHTML = '<pre>' + escapeHtml(currentReportMarkdown) + '</pre>';
                        }
                        
                        // Scroll to show new content
                        contentEl.scrollTop = contentEl.scrollHeight;
                    }
                    if (event.section_done) {
                        sectionsWritten++;
                        updateContextMonitor({sections: sectionsWritten});
                        updateProgressBar();
                    }
                    if (event.done) {
                        // Final render with math
                        try {
                            if (typeof renderMathInElement === 'function') {
                                renderMathInElement(contentEl, {delimiters: [
                                    {left: '$$', right: '$$', display: true},
                                    {left: '$', right: '$', display: false},
                                ]});
                            }
                        } catch (e) {
                            console.error('[Research] Math render error:', e);
                        }
                        el('reportActions').style.display = 'flex';
                        updateProgressBar();
                    }
                },
                context: function(event) {
                    console.log('[Research] Context stats:', event);
                    if (event.tokens !== undefined || event.sections !== undefined || event.sources !== undefined) {
                        updateContextMonitor({
                            tokens: event.tokens,
                            sections: event.sections,
                            sources: event.sources
                        });
                    }
                },
                done: function(event) {
                    currentPhase = 'done';
                    setStatus(getT('research_complete') || 'Research Complete');
                    setPhase('done');
                    updateProgressBar();
                    loadReports();
                    showToast(getT('research_complete') || 'Research Complete', 'success');
                    console.log('[Research] Done:', event.report_id);
                },
                error: function(event) {
                    console.error('[Research] Error:', event.message);
                    showToast(event.message || 'Research error', 'error');
                    setStatus('Error: ' + (event.message || 'Unknown error'));
                }
            }, function(errMsg) { 
                console.error('[Research] SSE Error:', errMsg);
                showToast(errMsg, 'error');
                setStatus('Error: ' + errMsg); 
            });
        } catch (e) {
            console.error('[Research] Fetch error:', e);
            showToast('Error: ' + e.message, 'error');
            setStatus('Error: ' + e.message);
        } finally {
            isResearching = false;
            el('startBtn').disabled = false;
            el('stopBtn').style.display = 'none';
        }
    }

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function stopResearch() {
        fetch('/api/stop', {method: 'POST'});
        setStatus(getT('generation_stopped') || 'Stopping...');
        showToast(getT('generation_stopped') || 'Generation stopped', 'warning');
        isResearching = false;
        el('stopBtn').style.display = 'none';
        el('startBtn').disabled = false;
    }

    function setPhase(phase) {
        ['rephrasing', 'planning', 'researching', 'reporting'].forEach(function(p) {
            var phEl = el('phase-' + p);
            if (phEl) phEl.classList.remove('active', 'completed');
        });
        var refiningEl = el('phase-refining');
        if (refiningEl) refiningEl.classList.remove('active', 'completed');

        var phases = ['rephrasing', 'planning', 'researching', 'reporting'];
        if (refiningEl) phases.splice(3, 0, 'refining');

        var idx = phases.indexOf(phase);
        if (idx >= 0) {
            for (var i = 0; i < idx; i++) {
                var phEl = el('phase-' + phases[i]);
                if (phEl) phEl.classList.add('completed');
            }
            var activeEl = el('phase-' + phase);
            if (activeEl) activeEl.classList.add('active');
        } else if (phase === 'done') {
            phases.forEach(function(p) {
                var phEl = el('phase-' + p);
                if (phEl) phEl.classList.add('completed');
            });
        }
    }

    function updateSubtopic(data) {
        var container = el('subtopicList');
        if (!container) return;
        
        var cardId = P + 'st-' + data.title.replace(/\s+/g, '_').replace(/[^a-zA-Z0-9_-]/g, '');
        var card = document.getElementById(cardId);

        if (!card) {
            card = document.createElement('div');
            card.className = 'subtopic-card pending';
            card.id = cardId;
            card.innerHTML =
                '<div class="subtopic-title">' + escapeHtml(data.title) + '</div>' +
                '<div class="subtopic-overview">' + escapeHtml(data.overview || '') + '</div>';
            container.appendChild(card);
            
            // Count total subtopics
            if (data.status === 'PENDING') {
                subtopicsTotal++;
            }
        }

        card.className = 'subtopic-card ' + (data.status || 'pending');

        if (data.source_detail) {
            var detailEl = card.querySelector('.subtopic-sources-detail');
            if (!detailEl) {
                detailEl = document.createElement('div');
                detailEl.className = 'subtopic-sources-detail';
                card.appendChild(detailEl);
            }
            detailEl.textContent = data.source_detail;
        }

        if (data.iteration && data.iteration > 0) {
            var badge = card.querySelector('.iteration-badge');
            if (!badge) {
                badge = document.createElement('span');
                badge.className = 'iteration-badge';
                var titleEl = card.querySelector('.subtopic-title');
                if (titleEl) titleEl.appendChild(badge);
            }
            if (badge) badge.textContent = ' \u21BB' + (data.iteration + 1);
        }

        if (data.sources && data.sources.length > 0 && !data.source_detail) {
            var existing = card.querySelector('.subtopic-sources');
            if (!existing) {
                var sourcesDiv = document.createElement('div');
                sourcesDiv.className = 'subtopic-sources';
                sourcesDiv.style.cssText = 'font-size:0.78em; color:var(--text-muted); margin-top:3px;';
                sourcesDiv.textContent = 'Sources: ' + data.sources.slice(0, 3).join(', ') + (data.sources.length > 3 ? '...' : '');
                card.appendChild(sourcesDiv);
            }
        }
    }

    function exportReport() {
        if (!currentReportMarkdown) {
            showToast('No report to export', 'warning');
            return;
        }
        exportMarkdown(currentReportMarkdown, 'research_report.md');
        showToast('Report exported', 'success');
    }

    function copyReport() {
        if (!currentReportMarkdown) {
            showToast('No report to copy', 'warning');
            return;
        }
        copyToClipboard(currentReportMarkdown, function(msg) {
            showToast(msg, 'success');
        });
    }

    async function loadReports() {
        try {
            var res = await fetch('/api/learning/research/reports');
            var data = await res.json();
            var container = el('reportList');
            if (!container) return;
            
            if (!data.reports || data.reports.length === 0) {
                container.innerHTML = '<div class="empty-state" style="padding:10px;color:var(--text-muted);">' + (getT('no_reports') || 'No saved reports') + '</div>';
                return;
            }
            container.innerHTML = data.reports.map(function(r) {
                return '<div class="history-item" onclick="ResearchModule.loadReport(\'' + r.report_id + '\')">' +
                    '<div>' +
                        '<div class="hi-title">' + escapeHtml(r.topic) + '</div>' +
                        '<div class="hi-meta">' + r.depth + ' \u2022 ' + r.subtopic_count + ' subtopics \u2022 ' + r.created_at.split('T')[0] + '</div>' +
                    '</div>' +
                    '<button class="hi-delete" onclick="event.stopPropagation(); ResearchModule.deleteReport(\'' + r.report_id + '\')">\u00D7</button>' +
                '</div>';
            }).join('');
        } catch (e) {
            console.error('[Research] Load reports error:', e);
        }
    }

    async function loadReport(reportId) {
        try {
            var res = await fetch('/api/learning/research/report/' + reportId);
            var data = await res.json();
            if (data.error) { 
                showToast(data.error, 'error');
                return; 
            }

            el('emptyState').style.display = 'none';
            currentReportMarkdown = data.report_markdown || '';
            var content = el('reportContent');
            if (!content) return;
            
            try {
                if (typeof renderMarkdown === 'function') {
                    content.innerHTML = renderMarkdown(currentReportMarkdown);
                } else {
                    content.innerHTML = '<pre>' + escapeHtml(currentReportMarkdown) + '</pre>';
                }
            } catch (e) {
                content.innerHTML = '<pre>' + escapeHtml(currentReportMarkdown) + '</pre>';
            }

            try {
                if (typeof renderMathInElement === 'function') {
                    renderMathInElement(content, {delimiters: [
                        {left: '$$', right: '$$', display: true},
                        {left: '$', right: '$', display: false},
                    ]});
                }
            } catch (e) {}

            el('reportActions').style.display = 'flex';
            setStatus('Loaded: ' + data.topic);

            el('phaseSection').style.display = 'block';
            setPhase('done');
            var stContainer = el('subtopicList');
            if (stContainer) {
                stContainer.innerHTML = (data.subtopics || []).map(function(s) {
                    return '<div class="subtopic-card completed">' +
                        '<div class="subtopic-title">' + escapeHtml(s.title) + '</div>' +
                        '<div class="subtopic-overview">' + escapeHtml(s.overview || '') + '</div>' +
                    '</div>';
                }).join('');
            }
            
            updateContextMonitor({
                tokens: estimateTokens(currentReportMarkdown),
                sections: (data.subtopics || []).length,
                sources: (data.citations || []).length
            });
            
            showToast('Report loaded', 'success');
        } catch (e) {
            console.error('[Research] Load report error:', e);
            showToast('Error: ' + e.message, 'error');
        }
    }

    async function deleteReport(reportId) {
        if (!confirm(getT('confirm_delete') || 'Delete this report?')) return;
        
        try {
            var res = await fetch('/api/learning/research/report/' + reportId, {method: 'DELETE'});
            var data = await res.json();
            if (data.success) {
                showToast('Report deleted', 'success');
                loadReports();
            } else {
                showToast(data.error || 'Delete failed', 'error');
            }
        } catch (e) {
            showToast('Error: ' + e.message, 'error');
        }
    }

    function setStatus(msg) {
        setStatusCommon(msg, P + 'statusMsg');
    }

    window.ResearchModule = {
        init: init,
        startResearch: startResearch,
        stopResearch: stopResearch,
        exportReport: exportReport,
        copyReport: copyReport,
        loadReport: loadReport,
        deleteReport: deleteReport,
    };
})();