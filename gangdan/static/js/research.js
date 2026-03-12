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

    function el(id) { return document.getElementById(P + id); }

    function init() {
        if (_inited) return;
        _inited = true;
        loadReports();
        el('reportActions').style.display = 'none';

        var depthSelect = document.getElementById('depthSelect');
        depthSelect.addEventListener('change', function() {
            var isAuto = depthSelect.value === 'auto';
            var refiningEl = el('phase-refining');
            var refiningArrow = el('refining-arrow');
            if (refiningEl) refiningEl.style.display = isAuto ? '' : 'none';
            if (refiningArrow) refiningArrow.style.display = isAuto ? '' : 'none';
        });
    }

    function updateContextMonitor(stats) {
        var monitor = document.getElementById('contextMonitor');
        if (!monitor) return;
        monitor.style.display = 'block';
        
        if (stats.tokens !== undefined) {
            tokenEstimate = stats.tokens;
            document.getElementById('tokenCount').textContent = tokenEstimate.toLocaleString();
        }
        if (stats.sections !== undefined) {
            sectionsWritten = stats.sections;
            document.getElementById('sectionsWritten').textContent = sectionsWritten;
        }
        if (stats.sources !== undefined) {
            sourcesUsed = stats.sources;
            document.getElementById('sourcesUsed').textContent = sourcesUsed;
        }
    }

    function estimateTokens(text) {
        return Math.ceil(text.length / 4);
    }

    async function startResearch() {
        if (isResearching) return;
        var topic = el('topicInput').value.trim();
        if (!topic) return;
        if (window._learningSelectedKbs.size === 0) {
            setStatus(getT('no_kb_selected') || 'Please select a knowledge base');
            return;
        }

        isResearching = true;
        currentReportMarkdown = '';
        tokenEstimate = 0;
        sectionsWritten = 0;
        sourcesUsed = 0;
        
        el('startBtn').disabled = true;
        el('stopBtn').style.display = 'block';
        el('reportContent').innerHTML = '';
        el('emptyState').style.display = 'none';
        el('phaseSection').style.display = 'block';
        el('subtopicList').innerHTML = '';
        el('reportActions').style.display = 'none';
        
        var statsEl = el('progressStats');
        if (statsEl) statsEl.textContent = '';
        
        var contextMonitor = document.getElementById('contextMonitor');
        if (contextMonitor) contextMonitor.style.display = 'block';
        updateContextMonitor({tokens: 0, sections: 0, sources: 0});

        var isAuto = el('depthSelect').value === 'auto';
        var refiningEl = el('phase-refining');
        var refiningArrow = el('refining-arrow');
        if (refiningEl) refiningEl.style.display = isAuto ? '' : 'none';
        if (refiningArrow) refiningArrow.style.display = isAuto ? '' : 'none';
        setPhase('rephrasing');
        setStatus(getT('start_research') || 'Starting research...');

        var outputSize = document.getElementById('outputSizeSelect').value;

        try {
            var res = await fetch('/api/learning/research/run', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    topic: topic,
                    kb_names: Array.from(window._learningSelectedKbs),
                    depth: el('depthSelect').value,
                    web_search: el('webSearchToggle') ? el('webSearchToggle').checked : false,
                    output_size: outputSize
                })
            });

            await createSSEReader(res, {
                phase: function(event) { setPhase(event.phase); setStatus(event.message); },
                status: function(event) { setStatus(event.message); },
                subtopic: function(event) { 
                    updateSubtopic(event.data);
                    if (event.data.sources) {
                        sourcesUsed = Math.max(sourcesUsed, event.data.sources.length);
                        updateContextMonitor({sources: sourcesUsed});
                    }
                },
                iteration: function(event) {
                    var sEl = el('progressStats');
                    if (sEl) {
                        var text = 'Iteration ' + event.current + '/' + event.max;
                        if (event.weak_count > 0) text += ' \u2022 ' + event.weak_count + ' weak subtopics';
                        if (event.sufficient) text += ' \u2022 Findings sufficient';
                        sEl.textContent = text;
                    }
                },
                content: function(event) {
                    var contentEl = el('reportContent');
                    if (event.content) {
                        currentReportMarkdown += event.content;
                        tokenEstimate = estimateTokens(currentReportMarkdown);
                        updateContextMonitor({tokens: tokenEstimate});
                        contentEl.innerHTML = typeof renderMarkdown === 'function' ? renderMarkdown(currentReportMarkdown) : currentReportMarkdown;
                    }
                    if (event.section_done) {
                        sectionsWritten++;
                        updateContextMonitor({sections: sectionsWritten});
                    }
                    if (event.done) {
                        if (typeof renderMathInElement === 'function') {
                            renderMathInElement(contentEl, {delimiters: [
                                {left: '$$', right: '$$', display: true},
                                {left: '$', right: '$', display: false},
                            ]});
                        }
                        el('reportActions').style.display = 'flex';
                    }
                },
                context: function(event) {
                    if (event.tokens || event.sections || event.sources) {
                        updateContextMonitor({
                            tokens: event.tokens,
                            sections: event.sections,
                            sources: event.sources
                        });
                    }
                },
                done: function(event) {
                    setStatus(getT('research_complete') || 'Research Complete');
                    setPhase('done');
                    loadReports();
                },
            }, function(errMsg) { setStatus(errMsg); });
        } catch (e) {
            setStatus('Error: ' + e.message);
        } finally {
            isResearching = false;
            el('startBtn').disabled = false;
            el('stopBtn').style.display = 'none';
        }
    }

    function stopResearch() {
        fetch('/api/stop', {method: 'POST'});
        setStatus(getT('generation_stopped') || 'Stopping...');
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
        var cardId = P + 'st-' + data.title.replace(/\s+/g, '_');
        var card = document.getElementById(cardId);

        if (!card) {
            card = document.createElement('div');
            card.className = 'subtopic-card pending';
            card.id = cardId;
            card.innerHTML =
                '<div class="subtopic-title">' + data.title + '</div>' +
                '<div class="subtopic-overview">' + (data.overview || '') + '</div>';
            container.appendChild(card);
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
                card.querySelector('.subtopic-title').appendChild(badge);
            }
            badge.textContent = ' \u21BB' + (data.iteration + 1);
        }

        if (data.sources && data.sources.length > 0 && !data.source_detail) {
            var existing = card.querySelector('.subtopic-sources');
            if (!existing) {
                card.innerHTML += '<div class="subtopic-sources" style="font-size:0.78em; color:var(--text-muted); margin-top:3px;">Sources: ' + data.sources.join(', ') + '</div>';
            }
        }
    }

    function exportReport() {
        exportMarkdown(currentReportMarkdown, 'research_report.md');
    }

    function copyReport() {
        copyToClipboard(currentReportMarkdown, function(msg) {
            setStatus(msg);
            setTimeout(function() { setStatus(''); }, 2000);
        });
    }

    async function loadReports() {
        try {
            var res = await fetch('/api/learning/research/reports');
            var data = await res.json();
            var container = el('reportList');
            if (!data.reports || data.reports.length === 0) {
                container.innerHTML = '<div class="empty-state" style="padding:10px;">No reports</div>';
                return;
            }
            container.innerHTML = data.reports.map(function(r) {
                return '<div class="history-item" onclick="ResearchModule.loadReport(\'' + r.report_id + '\')">' +
                    '<div>' +
                        '<div class="hi-title">' + r.topic + '</div>' +
                        '<div class="hi-meta">' + r.depth + ' &middot; ' + r.subtopic_count + ' subtopics &middot; ' + r.created_at.split('T')[0] + '</div>' +
                    '</div>' +
                    '<button class="hi-delete" onclick="event.stopPropagation(); ResearchModule.deleteReport(\'' + r.report_id + '\')">&#215;</button>' +
                '</div>';
            }).join('');
        } catch (e) {}
    }

    async function loadReport(reportId) {
        try {
            var res = await fetch('/api/learning/research/report/' + reportId);
            var data = await res.json();
            if (data.error) { setStatus(data.error); return; }

            el('emptyState').style.display = 'none';
            currentReportMarkdown = data.report_markdown || '';
            var content = el('reportContent');
            content.innerHTML = typeof renderMarkdown === 'function' ? renderMarkdown(currentReportMarkdown) : currentReportMarkdown;

            if (typeof renderMathInElement === 'function') {
                renderMathInElement(content, {delimiters: [
                    {left: '$$', right: '$$', display: true},
                    {left: '$', right: '$', display: false},
                ]});
            }

            el('reportActions').style.display = 'flex';
            setStatus('Loaded: ' + data.topic);

            el('phaseSection').style.display = 'block';
            setPhase('done');
            var stContainer = el('subtopicList');
            stContainer.innerHTML = (data.subtopics || []).map(function(s) {
                return '<div class="subtopic-card completed">' +
                    '<div class="subtopic-title">' + s.title + '</div>' +
                    '<div class="subtopic-overview">' + (s.overview || '') + '</div>' +
                '</div>';
            }).join('');
            
            updateContextMonitor({
                tokens: estimateTokens(currentReportMarkdown),
                sections: (data.subtopics || []).length,
                sources: (data.citations || []).length
            });
        } catch (e) {
            setStatus('Error: ' + e.message);
        }
    }

    async function deleteReport(reportId) {
        await fetch('/api/learning/research/report/' + reportId, {method: 'DELETE'});
        loadReports();
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
