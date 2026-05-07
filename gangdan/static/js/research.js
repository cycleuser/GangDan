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
    var memoryCheckInterval = null;
    
    window._selectedKbs = window._selectedKbs || new Set();

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
            debugLog.innerHTML = debugLogEntries.slice(-100).map(function(e) {
                var color = 'var(--text-muted)';
                if (e.indexOf('Error') >= 0 || e.indexOf('FAIL') >= 0) color = '#ef5350';
                else if (e.indexOf('成功') >= 0) color = '#4caf50';
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
    }

    function init() {
        if (_inited) return;
        _inited = true;
        
        log('初始化研究模块...');
        loadReports();
        
        var reportActions = el('reportActions');
        if (reportActions) reportActions.style.display = 'none';
        
        loadKbList();
        loadSavedConfig();
        startMemoryMonitor();

        log('研究模块初始化完成');
    }
    
    function startMemoryMonitor() {
        updateMemoryUsage();
        if (memoryCheckInterval) clearInterval(memoryCheckInterval);
        memoryCheckInterval = setInterval(updateMemoryUsage, 5000);
    }
    
    async function updateMemoryUsage() {
        try {
            var res = await fetch('/api/memory');
            var data = await res.json();
            
            var memoryUsedEl = document.getElementById('r-memoryUsed');
            
            if (memoryUsedEl) {
                memoryUsedEl.textContent = data.total_memory_gb + ' GB';
            }
        } catch (e) {
            console.log('[Research] Memory check error:', e);
        }
    }
    
    async function updateModelInfo(modelName) {
        if (!modelName) return;
        
        var modelInfoEl = document.getElementById('r-modelInfo');
        if (!modelInfoEl) return;
        
        try {
            var res = await fetch('/api/model/info/' + encodeURIComponent(modelName));
            var data = await res.json();
            
            var info = '';
            if (data.context_length) {
                var ctxK = Math.round(data.context_length / 1024);
                info += ctxK + 'K ctx';
            }
            if (data.memory_required_gb) {
                info += (info ? ' | ' : '') + '~' + data.memory_required_gb + 'GB VRAM';
            }
            if (data.parameter_size && data.parameter_size !== 'unknown') {
                info += (info ? ' | ' : '') + data.parameter_size;
            }
            
            modelInfoEl.textContent = info || '-';
            log('模型信息: ' + modelName + ' - ' + info);
        } catch (e) {
            modelInfoEl.textContent = '-';
        }
    }
    
    function loadSavedConfig() {
        var cfg = window.SERVER_CONFIG || {};
        var providerEl = document.getElementById('r-provider');
        var apiKeyEl = document.getElementById('r-apiKey');
        var customUrlInput = document.getElementById('r-customUrlInput');
        
        var savedProvider = cfg.researchProvider || 'ollama';
        var savedApiKey = cfg.researchApiKey || '';
        var savedBaseUrl = cfg.researchApiBaseUrl || '';
        
        log('加载保存的配置: provider=' + savedProvider);
        
        if (providerEl) {
            providerEl.value = savedProvider;
        }
        
        if (apiKeyEl && savedApiKey) {
            apiKeyEl.value = savedApiKey;
        }
        
        if (customUrlInput && savedBaseUrl) {
            customUrlInput.value = savedBaseUrl;
        }
        
        onProviderChange();
    }
    
    async function loadKbList() {
        try {
            var res = await fetch('/api/learning/kb/list');
            var data = await res.json();
            var container = el('kbCheckList');
            if (!container) return;
            
            var kbs = data.kbs || [];
            if (kbs.length === 0) {
                container.innerHTML = '<div class="empty-state">没有知识库</div>';
                return;
            }
            
            container.innerHTML = kbs.map(function(kb) {
                return '<label class="kb-check-item">' +
                    '<input type="checkbox" value="' + kb.name + '" onchange="toggleKb(this)">' +
                    '<span>' + kb.display_name + ' <small>(' + kb.doc_count + ')</small></span>' +
                    '</label>';
            }).join('');
            
            log('加载了 ' + kbs.length + ' 个知识库');
        } catch (e) {
            log('加载知识库错误: ' + e.message, 'error');
        }
    }
    
    window.toggleKb = function(cb) {
        if (!window._selectedKbs) window._selectedKbs = new Set();
        if (cb.checked) {
            window._selectedKbs.add(cb.value);
        } else {
            window._selectedKbs.delete(cb.value);
        }
        log('KB 切换: ' + (cb.checked ? '选中' : '取消') + ' ' + cb.value + ', 总数: ' + window._selectedKbs.size);
    };

    function onProviderChange() {
        var providerEl = document.getElementById('r-provider');
        var provider = providerEl ? providerEl.value : 'ollama';
        var config = getProviderConfig(provider);
        var modelSelect = document.getElementById('r-modelSelect');
        var apiStatusEl = document.getElementById('r-apiStatus');
        var apiKeyEl = document.getElementById('r-apiKey');
        var customUrlDiv = document.getElementById('r-customUrl');
        
        if (customUrlDiv) customUrlDiv.style.display = provider === 'custom' ? 'block' : 'none';
        
        if (apiKeyEl) {
            apiKeyEl.placeholder = config.requires_key ? 'API Key (必填)' : 'API Key (本地无需)';
        }
        
        if (apiStatusEl) {
            var helpHtml = '<small>' + (config.help || '') + '</small>';
            if (config.key_url && config.requires_key) {
                helpHtml += ' <a href="' + config.key_url + '" target="_blank">获取Key</a>';
            }
            apiStatusEl.innerHTML = helpHtml;
        }
        
        log('切换到: ' + provider);
        
        loadModels();
    }

    async function loadModels() {
        var providerEl = document.getElementById('r-provider');
        var provider = providerEl ? providerEl.value : 'ollama';
        var config = getProviderConfig(provider);
        var modelSelect = document.getElementById('r-modelSelect');
        var apiStatusEl = document.getElementById('r-apiStatus');
        var apiKeyEl = document.getElementById('r-apiKey');
        var apiKey = apiKeyEl ? apiKeyEl.value.trim() : '';
        var customUrlInput = document.getElementById('r-customUrlInput');
        var customUrl = customUrlInput ? customUrlInput.value.trim() : '';
        var serverCfg = window.SERVER_CONFIG || {};
        
        var baseUrl = config.base_url;
        if (provider === 'custom') {
            baseUrl = customUrl;
        } else if (provider === 'ollama') {
            baseUrl = serverCfg.ollamaUrl || config.base_url;
        }
        
        log('loadModels: provider=' + provider + ', baseUrl=' + baseUrl);
        
        if (!baseUrl && provider === 'custom') {
            if (apiStatusEl) apiStatusEl.innerHTML = '<span style="color:#ef5350;">请输入 API URL</span>';
            return;
        }
        
        if (config.models && config.models.length > 0 && provider !== 'ollama') {
            if (modelSelect) {
                modelSelect.innerHTML = '<option value="">-- 选择模型 --</option>' +
                    config.models.map(function(m) { return '<option value="' + m + '">' + m + '</option>'; }).join('');
                if (config.default_model) modelSelect.value = config.default_model;
            }
            if (apiStatusEl) apiStatusEl.innerHTML = '<span style="color:#4caf50;">✓ ' + config.models.length + ' 个预设模型</span>';
            log('使用预设模型: ' + config.models.length);
            return;
        }
        
        if (config.requires_key && !apiKey) {
            if (apiStatusEl) apiStatusEl.innerHTML = '<span style="color:#ef5350;">请输入 API Key</span>';
            return;
        }
        
        if (apiStatusEl) apiStatusEl.innerHTML = '<span>加载模型中...</span>';
        log('调用 API: ' + baseUrl);
        
        try {
            var res = await fetch('/api/test-api', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    base_url: baseUrl + '/v1',
                    api_key: ''
                })
            });
            var data = await res.json();
            log('API 响应: success=' + data.success + ', models=' + (data.models ? data.models.length : 0));
            
            if (data.success && data.models && data.models.length > 0) {
                var chatModels = data.models.filter(function(m) {
                    var ml = m.toLowerCase();
                    return ml.indexOf('embed') < 0 && ml.indexOf('bge') < 0 && ml.indexOf('e5') < 0 && ml.indexOf('rerank') < 0;
                });
                if (modelSelect) {
                    modelSelect.innerHTML = '<option value="">-- 选择模型 --</option>' +
                        chatModels.map(function(m) { return '<option value="' + m + '">' + m + '</option>'; }).join('');
                    if (chatModels.length > 0) {
                        modelSelect.value = chatModels[0];
                        log('自动选择模型: ' + chatModels[0]);
                        updateModelInfo(chatModels[0]);
                    }
                    modelSelect.addEventListener('change', function() {
                        if (modelSelect.value) {
                            updateModelInfo(modelSelect.value);
                        }
                    });
                }
                if (apiStatusEl) apiStatusEl.innerHTML = '<span style="color:#4caf50;">' + chatModels.length + ' 个模型</span>';
            } else {
                if (modelSelect) modelSelect.innerHTML = '<option value="">-- 无可用模型 --</option>';
                if (apiStatusEl) apiStatusEl.innerHTML = '<span style="color:#ff9800;">' + (data.message || '无法加载模型') + '</span>';
                log('加载失败: ' + (data.message || '未知'));
            }
        } catch (e) {
            if (apiStatusEl) apiStatusEl.innerHTML = '<span style="color:#ef5350;">错误: ' + e.message + '</span>';
            log('加载错误: ' + e.message, 'error');
        }
    }

    async function testConnection() {
        var providerEl = document.getElementById('r-provider');
        var provider = providerEl ? providerEl.value : 'ollama';
        var config = getProviderConfig(provider);
        var modelSelect = document.getElementById('r-modelSelect');
        var apiStatusEl = document.getElementById('r-apiStatus');
        var apiKeyEl = document.getElementById('r-apiKey');
        var apiKey = apiKeyEl ? apiKeyEl.value.trim() : '';
        var customUrlInput = document.getElementById('r-customUrlInput');
        var customUrl = customUrlInput ? customUrlInput.value.trim() : '';
        
        var modelName = modelSelect ? modelSelect.value : '';
        if (!modelName) {
            if (apiStatusEl) apiStatusEl.innerHTML = '<span style="color:#ff9800;">请先选择模型</span>';
            return;
        }
        
        var baseUrl = config.base_url;
        if (provider === 'custom') baseUrl = customUrl;
        
        if (!baseUrl) {
            if (apiStatusEl) apiStatusEl.innerHTML = '<span style="color:#ef5350;">请输入 API URL</span>';
            return;
        }
        
        if (config.requires_key && !apiKey) {
            if (apiStatusEl) apiStatusEl.innerHTML = '<span style="color:#ef5350;">请输入 API Key</span>';
            return;
        }
        
        if (apiStatusEl) apiStatusEl.innerHTML = '<span>测试连接...</span>';
        log('测试: ' + baseUrl + ' 模型: ' + modelName);
        
        try {
            var res = await fetch('/api/test-api', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    base_url: baseUrl + (provider === 'ollama' ? '/v1' : ''),
                    api_key: apiKey,
                    model: modelName,
                    test_chat: true,
                    api_type: config.api_type || 'openai'
                })
            });
            var data = await res.json();
            
            if (data.success) {
                if (apiStatusEl) apiStatusEl.innerHTML = '<span style="color:#4caf50;">✓ 连接成功!</span>';
                log('✓ 连接成功');
                showToast('连接成功', 'success');
            } else {
                if (apiStatusEl) apiStatusEl.innerHTML = '<span style="color:#ef5350;">✗ ' + (data.error || '失败') + '</span>';
                log('连接失败: ' + (data.error || '未知'), 'error');
            }
        } catch (e) {
            if (apiStatusEl) apiStatusEl.innerHTML = '<span style="color:#ef5350;">错误: ' + e.message + '</span>';
            log('测试错误: ' + e.message, 'error');
        }
    }

    async function startResearch() {
        if (isResearching) return;
        
        var topicInput = el('topicInput');
        var topic = topicInput ? topicInput.value.trim() : '';
        if (!topic) {
            showToast('请输入研究主题', 'error');
            return;
        }
        
        log('检查 KB: _selectedKbs = ' + (typeof window._selectedKbs) + ', size = ' + (window._selectedKbs ? window._selectedKbs.size : 'N/A'));
        
        if (!window._selectedKbs || window._selectedKbs.size === 0) {
            showToast('请选择至少一个知识库', 'error');
            return;
        }
        
        var providerEl = document.getElementById('r-provider');
        var provider = providerEl ? providerEl.value : 'ollama';
        var config = getProviderConfig(provider);
        var modelSelect = document.getElementById('r-modelSelect');
        var apiKeyEl = document.getElementById('r-apiKey');
        var customUrlInput = document.getElementById('r-customUrlInput');
        var serverCfg = window.SERVER_CONFIG || {};
        
        var modelName = modelSelect ? modelSelect.value : '';
        var apiKey = apiKeyEl ? apiKeyEl.value.trim() : '';
        var customUrl = customUrlInput ? customUrlInput.value.trim() : '';
        
        if (!modelName) {
            showToast('请选择模型', 'error');
            return;
        }
        
        var baseUrl = config.base_url;
        if (provider === 'custom') {
            baseUrl = customUrl;
        } else if (provider === 'ollama') {
            baseUrl = serverCfg.ollamaUrl || config.base_url;
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

        var warningEl = el('kbWarning');
        if (warningEl) { warningEl.style.display = 'none'; warningEl.innerHTML = ''; }
        
        var startBtn = el('startBtn');
        var stopBtn = el('stopBtn');
        if (startBtn) startBtn.disabled = true;
        if (stopBtn) stopBtn.style.display = 'block';
        
        var reportContent = el('reportContent');
        if (reportContent) reportContent.innerHTML = '<div class="research-placeholder"><span class="loading"></span> <span>准备研究中...</span></div>';
        
        var emptyState = el('emptyState');
        if (emptyState) emptyState.style.display = 'none';
        
        var phaseSection = el('phaseSection');
        if (phaseSection) phaseSection.style.display = 'block';
        
        var subtopicList = el('subtopicList');
        if (subtopicList) subtopicList.innerHTML = '';
        
        var debugSection = el('debugSection');
        if (debugSection) debugSection.style.display = 'block';
        
        updateContextMonitor({tokens: 0, sections: 0, sources: 0});

        setPhase('rephrasing');
        setStatus('开始研究...');
        log('开始: ' + topic);
        log('Provider: ' + provider + ', Model: ' + modelName);

        var outputSizeEl = document.getElementById('r-outputSizeSelect');
        var outputSize = outputSizeEl ? outputSizeEl.value : 'medium';
        
        var depthEl = el('depthSelect');
        var depth = depthEl ? depthEl.value : 'medium';

        var requestBody = {
            topic: topic,
            kb_names: Array.from(window._selectedKbs),
            depth: depth,
            output_size: outputSize,
            model_name: modelName,
            api_url: baseUrl + (provider === 'ollama' ? '/v1' : ''),
            api_key: apiKey,
            provider: provider,
            api_type: config.api_type || 'openai'
        };

        try {
            log('发送请求...');
            var res = await fetch('/api/learning/research/run', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(requestBody)
            });

            if (!res.ok) {
                var errText = await res.text();
                log('服务器错误: ' + res.status, 'error');
                throw new Error('服务器错误: ' + res.status);
            }
            
            log('已连接，接收数据流...');

            await createSSEReader(res, {
                phase: function(event) { 
                    currentPhase = event.phase;
                    setPhase(event.phase); 
                    setStatus(event.message);
                    log('阶段: ' + event.phase);
                },
                status: function(event) { 
                    setStatus(event.message);
                },
                warning: function(event) {
                    var warningEl = el('kbWarning');
                    if (warningEl) {
                        warningEl.innerHTML = '<div style="padding:12px 16px;background:#fff3cd;border:1px solid #ffc107;border-radius:8px;margin:10px 0;font-size:0.9em;color:#856404;">⚠️ ' + escapeHtml(event.message) + '</div>';
                        warningEl.style.display = 'block';
                    }
                    setStatus(event.message);
                    showToast(event.message, 'warning');
                    log('WARNING: ' + event.message);
                },
                debug: function(event) {
                    log('DEBUG: ' + event.message);
                },
                subtopic: function(event) { 
                    updateSubtopic(event.data);
                    if (event.data.status === 'COMPLETED') subtopicsCompleted++;
                    if (event.data.sources) {
                        sourcesUsed = Math.max(sourcesUsed, event.data.sources.length);
                        updateContextMonitor({sources: sourcesUsed});
                    }
                },
                content: function(event) {
                    var contentEl = el('reportContent');
                    if (!contentEl) return;
                    
                    if (event.content) {
                        currentReportMarkdown += event.content;
                        tokenEstimate = Math.ceil(currentReportMarkdown.length / 4);
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
                            contentEl.innerHTML = '<pre>' + escapeHtml(currentReportMarkdown) + '</pre>';
                        }
                        contentEl.scrollTop = contentEl.scrollHeight;
                    }
                    if (event.section_done) {
                        sectionsWritten++;
                        updateContextMonitor({sections: sectionsWritten});
                    }
                    if (event.done) {
                        var reportActions = el('reportActions');
                        if (reportActions) reportActions.style.display = 'flex';
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
                    setStatus('研究完成');
                    setPhase('done');
                    loadReports();
                    showToast('研究完成', 'success');
                    log('✓ 完成! ID: ' + event.report_id);
                },
                error: function(event) {
                    log('ERROR: ' + event.message, 'error');
                    showToast(event.message || '错误', 'error');
                    setStatus('错误: ' + (event.message || '未知'));
                }
            }, function(errMsg) { 
                log('SSE 错误: ' + errMsg, 'error');
                showToast(errMsg, 'error');
                setStatus('错误: ' + errMsg); 
            });
        } catch (e) {
            log('错误: ' + e.message, 'error');
            showToast('错误: ' + e.message, 'error');
            setStatus('错误: ' + e.message);
        } finally {
            isResearching = false;
            var startBtn = el('startBtn');
            var stopBtn = el('stopBtn');
            if (startBtn) startBtn.disabled = false;
            if (stopBtn) stopBtn.style.display = 'none';
        }
    }

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function updateContextMonitor(stats) {
        var monitor = document.getElementById('contextMonitor');
        if (!monitor) return;
        monitor.style.display = 'block';
        
        if (stats.tokens !== undefined) {
            var tokenEl = document.getElementById('tokenCount');
            if (tokenEl) tokenEl.textContent = stats.tokens.toLocaleString();
        }
        if (stats.sections !== undefined) {
            var sectionsEl = document.getElementById('sectionsWritten');
            if (sectionsEl) sectionsEl.textContent = stats.sections;
        }
        if (stats.sources !== undefined) {
            var sourcesEl = document.getElementById('sourcesUsed');
            if (sourcesEl) sourcesEl.textContent = stats.sources;
        }
    }

    function stopResearch() {
        fetch('/api/stop', {method: 'POST'});
        setStatus('停止中...');
        showToast('已停止', 'warning');
        log('用户停止');
        isResearching = false;
        var stopBtn = el('stopBtn');
        var startBtn = el('startBtn');
        if (stopBtn) stopBtn.style.display = 'none';
        if (startBtn) startBtn.disabled = false;
    }

    function setPhase(phase) {
        ['preflight', 'rephrasing', 'planning', 'researching', 'reporting'].forEach(function(p) {
            var phEl = el('phase-' + p);
            if (phEl) phEl.classList.remove('active', 'completed');
        });
        var refiningEl = el('phase-refining');
        if (refiningEl) refiningEl.classList.remove('active', 'completed');

        // Show/hide preflight elements
        var preflightEl = el('phase-preflight');
        var preflightArrow = el('preflight-arrow');
        if (phase === 'preflight') {
            if (preflightEl) { preflightEl.style.display = 'inline'; preflightEl.classList.add('active'); }
            if (preflightArrow) preflightArrow.style.display = 'inline';
        } else if (phase !== 'preflight' && preflightEl) {
            if (preflightEl.style.display !== 'none') {
                preflightEl.classList.add('completed');
                preflightEl.classList.remove('active');
            }
        }

        var phases = ['preflight', 'rephrasing', 'planning', 'researching', 'reporting'];
        if (refiningEl && !phases.includes('refining')) phases.splice(3, 0, 'refining');

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
        }

        card.className = 'subtopic-card ' + (data.status || 'pending');
    }

    function exportReport() {
        if (!currentReportMarkdown) {
            showToast('没有报告可导出', 'warning');
            return;
        }
        exportMarkdown(currentReportMarkdown, 'research_report.md');
        showToast('已导出', 'success');
    }

    function copyReport() {
        if (!currentReportMarkdown) {
            showToast('没有报告可复制', 'warning');
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
                container.innerHTML = '<div class="empty-state">没有保存的报告</div>';
                return;
            }
            container.innerHTML = data.reports.map(function(r) {
                return '<div class="history-item" onclick="ResearchModule.loadReport(\'' + r.report_id + '\')">' +
                    '<div>' +
                        '<div class="hi-title">' + escapeHtml(r.topic) + '</div>' +
                        '<div class="hi-meta">' + r.depth + ' • ' + r.subtopic_count + ' 子主题</div>' +
                    '</div>' +
                    '<button class="hi-delete" onclick="event.stopPropagation(); ResearchModule.deleteReport(\'' + r.report_id + '\')">×</button>' +
                '</div>';
            }).join('');
        } catch (e) {
            log('加载报告错误: ' + e.message, 'error');
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

            var emptyState = el('emptyState');
            if (emptyState) emptyState.style.display = 'none';
            
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

            var reportActions = el('reportActions');
            if (reportActions) reportActions.style.display = 'flex';
            setStatus('已加载: ' + data.topic);

            var phaseSection = el('phaseSection');
            if (phaseSection) phaseSection.style.display = 'block';
            setPhase('done');
            
            showToast('报告已加载', 'success');
        } catch (e) {
            showToast('错误: ' + e.message, 'error');
        }
    }

    async function deleteReport(reportId) {
        if (!confirm('删除此报告？')) return;
        
        try {
            var res = await fetch('/api/learning/research/report/' + reportId, {method: 'DELETE'});
            var data = await res.json();
            if (data.success) {
                showToast('已删除', 'success');
                loadReports();
            } else {
                showToast(data.error || '删除失败', 'error');
            }
        } catch (e) {
            showToast('错误: ' + e.message, 'error');
        }
    }

    function setStatus(msg) {
        var statusEl = el('statusMsg');
        if (statusEl) statusEl.textContent = msg;
    }

    window.ResearchModule = {
        init: init,
        startResearch: startResearch,
        stopResearch: stopResearch,
        exportReport: exportReport,
        copyReport: copyReport,
        loadReport: loadReport,
        deleteReport: deleteReport,
        toggleDebugLog: toggleDebugLog,
        onProviderChange: onProviderChange,
        loadModels: loadModels,
        testConnection: testConnection,
    };
})();