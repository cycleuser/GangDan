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
    var debugLogVisible = false;
    var debugLogEntries = [];

    function el(id) { return document.getElementById(P + id); }

    function log(msg, type) {
        var timestamp = new Date().toLocaleTimeString();
        var entry = '[' + timestamp + '] ' + msg;
        debugLogEntries.push(entry);
        console.log('[Research]', msg);
        
        var debugLog = el('debugLog');
        var debugSection = el('debugSection');
        if (debugSection) debugSection.style.display = 'block';
        
        if (debugLog && debugLogVisible) {
            var maxEntries = 100;
            if (debugLogEntries.length > maxEntries) {
                debugLogEntries = debugLogEntries.slice(-maxEntries);
            }
            debugLog.innerHTML = debugLogEntries.map(function(e) {
                var color = 'var(--text-muted)';
                if (e.indexOf('Error') >= 0 || e.indexOf('FAIL') >= 0) color = '#ef5350';
                else if (e.indexOf('✓') >= 0 || e.indexOf('Complete') >= 0) color = '#4caf50';
                else if (e.indexOf('...') >= 0) color = '#ff9800';
                return '<div style="color:' + color + '">' + escapeHtml(e) + '</div>';
            }).join('');
            debugLog.scrollTop = debugLog.scrollHeight;
        }
    }

    function toggleDebugLog() {
        debugLogVisible = !debugLogVisible;
        var debugLog = el('debugLog');
        var toggle = el('debugToggle');
        if (debugLog) debugLog.style.display = debugLogVisible ? 'block' : 'none';
        if (toggle) toggle.textContent = debugLogVisible ? '▲' : '▼';
        
        if (debugLogVisible && debugLog) {
            debugLog.innerHTML = debugLogEntries.map(function(e) {
                return '<div style="color:var(--text-muted)">' + escapeHtml(e) + '</div>';
            }).join('');
            debugLog.scrollTop = debugLog.scrollHeight;
        }
    }

    function init() {
        if (_inited) return;
        _inited = true;
        loadReports();
        el('reportActions').style.display = 'none';
        loadLocalModels();

        var depthSelect = el('depthSelect');
        if (depthSelect) {
            depthSelect.addEventListener('change', function() {
                var isAuto = depthSelect.value === 'auto';
                var refiningEl = el('phase-refining');
                var refiningArrow = el('refining-arrow');
                if (refiningEl) refiningEl.style.display = isAuto ? '' : 'none';
                if (refiningArrow) refiningArrow.style.display = isAuto ? '' : 'none';
            });
        }
        
        log('Research module initialized');
    }

    async function loadLocalModels() {
        try {
            log('Loading local models...');
            var res = await fetch('/api/models');
            var data = await res.json();
            var select = el('localModel');
            if (!select) {
                log('localModel select not found', 'error');
                return;
            }
            
            var models = data.chat_models || [];
            select.innerHTML = '<option value="">-- Select Model --</option>' +
                models.map(function(m) {
                    var selected = m === data.current_chat ? ' selected' : '';
                    return '<option value="' + m + '"' + selected + '>' + m + '</option>';
                }).join('');
            
            log('Loaded ' + models.length + ' local models');
            
            if (models.length > 0 && !select.value) {
                select.value = data.current_chat || models[0];
            }
        } catch (e) {
            log('Error loading models: ' + e.message, 'error');
            var select = el('localModel');
            if (select) {
                select.innerHTML = '<option value="">Error loading models</option>';
            }
        }
    }

    async function loadOnlineModels() {
        var providerEl = document.getElementById('r-onlineProvider');
        if (!providerEl) return;
        var provider = providerEl.value;
        
        var dataList = document.getElementById('r-onlineModelList');
        var modelInput = el('onlineModel');
        
        log('Loading models for ' + provider + '...');
        
        try {
            var res = await fetch('/api/test-provider', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({provider: provider})
            });
            var data = await res.json();
            
            if (data.success && data.models) {
                if (dataList) {
                    dataList.innerHTML = data.models.map(function(m) {
                        return '<option value="' + m + '">';
                    }).join('');
                }
                if (modelInput && data.models.length > 0) {
                    modelInput.placeholder = 'e.g., ' + data.models[0];
                }
                log('Loaded ' + data.models.length + ' models from ' + provider);
            } else {
                if (modelInput) {
                    modelInput.placeholder = 'Type model name (e.g., qwen-max)';
                }
                log('Using default models for ' + provider);
            }
        } catch (e) {
            log('Error loading online models: ' + e.message, 'error');
            if (modelInput) {
                modelInput.placeholder = 'Type model name';
            }
        }
    }

    function onModelTypeChange() {
        var modelType = document.getElementById('r-modelType');
        if (!modelType) return;
        modelType = modelType.value;
        
        var localModel = el('localModel');
        var onlineModel = el('onlineModel');
        var onlineSettings = el('onlineSettings');
        
        if (modelType === 'local') {
            if (localModel) localModel.style.display = '';
            if (onlineModel) onlineModel.style.display = 'none';
            if (onlineSettings) onlineSettings.style.display = 'none';
            log('Switched to local model');
        } else {
            if (localModel) localModel.style.display = 'none';
            if (onlineModel) onlineModel.style.display = '';
            if (onlineSettings) onlineSettings.style.display = 'block';
            log('Switched to online model');
            loadOnlineModels();
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
        
        log('Progress: ' + progress + '% (' + currentPhase + ')');
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

        var modelType = document.getElementById('r-modelType');
        modelType = modelType ? modelType.value : 'local';
        
        var modelName = '';
        var provider = '';
        
        if (modelType === 'local') {
            var localModel = el('localModel');
            modelName = localModel ? localModel.value : '';
            if (!modelName) {
                showToast('Please select a model', 'error');
                return;
            }
            provider = 'ollama';
            log('Using local model: ' + modelName);
        } else {
            var onlineModel = el('onlineModel');
            var onlineProvider = document.getElementById('r-onlineProvider');
            modelName = onlineModel ? onlineModel.value : '';
            provider = onlineProvider ? onlineProvider.value : 'dashscope';
            if (!modelName) {
                showToast('Please enter a model name', 'error');
                return;
            }
            log('Using online model: ' + modelName + ' (' + provider + ')');
        }

        isResearching = true;
        currentReportMarkdown = '';
        tokenEstimate = 0;
        sectionsWritten = 0;
        sourcesUsed = 0;
        subtopicsCompleted = 0;
        subtopicsTotal = 0;
        currentPhase = '';
        debugLogEntries = [];
        
        el('startBtn').disabled = true;
        el('stopBtn').style.display = 'block';
        el('reportContent').innerHTML = '<div class="research-placeholder"><span class="loading"></span> <span>Preparing research...</span></div>';
        el('emptyState').style.display = 'none';
        el('phaseSection').style.display = 'block';
        el('subtopicList').innerHTML = '';
        el('reportActions').style.display = 'none';
        el('debugSection').style.display = 'block';
        
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
        setStatus('Starting research...');
        log('Starting research on: ' + topic);

        var outputSize = document.getElementById('r-outputSizeSelect') ? document.getElementById('r-outputSizeSelect').value : 'medium';
        var depth = el('depthSelect') ? el('depthSelect').value : 'medium';
        var webSearch = false;
        
        var apiKey = '';
        if (modelType === 'online') {
            var apiKeyInput = document.getElementById('r-onlineApiKey');
            apiKey = apiKeyInput ? apiKeyInput.value : '';
        }

        var requestBody = {
            topic: topic,
            kb_names: Array.from(window._learningSelectedKbs),
            depth: depth,
            web_search: webSearch,
            output_size: outputSize,
            model_type: modelType,
            model_name: modelName,
            provider: provider,
            api_key: apiKey
        };
        log('Request: model=' + modelName + ', provider=' + provider + ', type=' + modelType);

        try {
            log('Sending request to server...');
            var res = await fetch('/api/learning/research/run', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(requestBody)
            });

            if (!res.ok) {
                var errText = await res.text();
                log('Server error: ' + res.status + ' ' + errText, 'error');
                throw new Error('Server error: ' + res.status);
            }
            
            log('Connection established, receiving stream...');

            await createSSEReader(res, {
                phase: function(event) { 
                    currentPhase = event.phase;
                    setPhase(event.phase); 
                    setStatus(event.message);
                    updateProgressBar();
                    log('Phase: ' + event.phase + ' - ' + event.message);
                },
                status: function(event) { 
                    setStatus(event.message);
                    log('Status: ' + event.message);
                },
                debug: function(event) {
                    log('DEBUG: ' + event.message);
                },
                subtopic: function(event) { 
                    updateSubtopic(event.data);
                    if (event.data.status === 'COMPLETED') {
                        subtopicsCompleted++;
                        log('✓ Subtopic complete: ' + event.data.title);
                    }
                    if (event.data.sources) {
                        sourcesUsed = Math.max(sourcesUsed, event.data.sources.length);
                        updateContextMonitor({sources: sourcesUsed});
                    }
                    if (subtopicsTotal === 0 && event.data.status === 'PENDING') {
                        subtopicsTotal++;
                    }
                    updateProgressBar();
                },
                iteration: function(event) {
                    var sEl = el('progressStats');
                    if (sEl) {
                        var text = 'Iteration ' + event.current + '/' + event.max;
                        if (event.weak_count > 0) text += ' • ' + event.weak_count + ' weak subtopics';
                        if (event.sufficient) text += ' • Findings sufficient';
                        sEl.textContent = text;
                    }
                    log('Iteration ' + event.current + '/' + event.max);
                },
                content: function(event) {
                    var contentEl = el('reportContent');
                    if (!contentEl) {
                        log('ERROR: reportContent element not found', 'error');
                        return;
                    }
                    
                    if (event.content) {
                        currentReportMarkdown += event.content;
                        tokenEstimate = estimateTokens(currentReportMarkdown);
                        updateContextMonitor({tokens: tokenEstimate});
                        
                        try {
                            if (typeof renderMarkdown === 'function') {
                                contentEl.innerHTML = renderMarkdown(currentReportMarkdown);
                            } else if (typeof marked !== 'undefined') {
                                contentEl.innerHTML = marked.parse(currentReportMarkdown);
                            } else {
                                contentEl.innerHTML = '<pre>' + escapeHtml(currentReportMarkdown) + '</pre>';
                            }
                        } catch (e) {
                            log('Markdown render error: ' + e.message, 'error');
                            contentEl.innerHTML = '<pre>' + escapeHtml(currentReportMarkdown) + '</pre>';
                        }
                        
                        contentEl.scrollTop = contentEl.scrollHeight;
                    }
                    if (event.section_done) {
                        sectionsWritten++;
                        updateContextMonitor({sections: sectionsWritten});
                        updateProgressBar();
                        log('Section ' + sectionsWritten + ' complete');
                    }
                    if (event.done) {
                        try {
                            if (typeof renderMathInElement === 'function') {
                                renderMathInElement(contentEl, {delimiters: [
                                    {left: '$$', right: '$$', display: true},
                                    {left: '$', right: '$', display: false},
                                ]});
                            }
                        } catch (e) {
                            log('Math render error: ' + e.message);
                        }
                        el('reportActions').style.display = 'flex';
                        updateProgressBar();
                    }
                },
                context: function(event) {
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
                    log('✓ Research complete! Report ID: ' + event.report_id);
                },
                error: function(event) {
                    log('ERROR: ' + event.message, 'error');
                    showToast(event.message || 'Research error', 'error');
                    setStatus('Error: ' + (event.message || 'Unknown error'));
                }
            }, function(errMsg) { 
                log('SSE Error: ' + errMsg, 'error');
                showToast(errMsg, 'error');
                setStatus('Error: ' + errMsg); 
            });
        } catch (e) {
            log('Fetch error: ' + e.message, 'error');
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
        log('Generation stopped by user');
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
            if (badge) badge.textContent = ' ↻' + (data.iteration + 1);
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
                        '<div class="hi-meta">' + r.depth + ' • ' + r.subtopic_count + ' subtopics • ' + r.created_at.split('T')[0] + '</div>' +
                    '</div>' +
                    '<button class="hi-delete" onclick="event.stopPropagation(); ResearchModule.deleteReport(\'' + r.report_id + '\')">×</button>' +
                '</div>';
            }).join('');
        } catch (e) {
            log('Load reports error: ' + e.message, 'error');
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
            log('Loaded report: ' + reportId);
        } catch (e) {
            log('Load report error: ' + e.message, 'error');
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
                log('Deleted report: ' + reportId);
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
        onModelTypeChange: onModelTypeChange,
        toggleDebugLog: toggleDebugLog,
        loadOnlineModels: loadOnlineModels,
    };
})();

function onModelTypeChange() {
    ResearchModule.onModelTypeChange();
}

function toggleDebugLog() {
    ResearchModule.toggleDebugLog();
}