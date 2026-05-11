// ============================================
// KB Analytics Frontend Module
// ============================================

const KbAnalytics = (() => {
    let currentKb = '';
    let currentTab = 'topics';
    let kbList = [];
    let allDocs = [];
    let pointCloudData = null;
    let selectedDocs = new Set();

    function showToast(msg, isError = false) {
        const toast = document.getElementById('toast');
        if (toast) {
            toast.textContent = msg;
            toast.className = 'toast show' + (isError ? ' error' : '');
            setTimeout(() => toast.classList.remove('show'), 3000);
        }
    }

    async function apiCall(url, body = null) {
        const opts = {
            method: body ? 'POST' : 'GET',
            headers: { 'Content-Type': 'application/json' },
        };
        if (body) opts.body = JSON.stringify(body);
        const resp = await fetch(url, opts);
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ error: resp.statusText }));
            throw new Error(err.error || resp.statusText);
        }
        return resp.json();
    }

    async function loadKbList() {
        try {
            const data = await apiCall('/api/kb/list');
            kbList = data.kbs || [];
            const sel = document.getElementById('analyticsKbSelect');
            if (!sel) return;
            sel.innerHTML = '<option value="">' + (getT ? getT('select_kb_analytics') : '-- Select KB --') + '</option>';
            kbList.forEach(kb => {
                const opt = document.createElement('option');
                opt.value = kb.name;
                opt.textContent = kb.display_name || kb.name;
                sel.appendChild(opt);
            });
        } catch (e) {
            showToast('Failed to load KB list: ' + e.message, true);
        }
    }

    async function onKbChange() {
        const sel = document.getElementById('analyticsKbSelect');
        currentKb = sel ? sel.value : '';
        selectedDocs.clear();
        updateSelectedCount();
        const wrapper = document.getElementById('analyticsDocToggleWrapper');
        const menu = document.getElementById('analyticsDocDropdownMenu');
        if (wrapper) wrapper.style.display = currentKb ? 'inline-block' : 'none';
        if (menu) menu.style.display = 'none';
        if (currentKb) {
            await loadDocuments();
        }
    }

    function toggleAnalyticsDocDropdown() {
        const menu = document.getElementById('analyticsDocDropdownMenu');
        if (menu) {
            menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
        }
    }

    async function loadDocuments() {
        if (!currentKb) return;
        try {
            const data = await apiCall(`/api/kb/${encodeURIComponent(currentKb)}/documents`);
            allDocs = data.documents || [];
            renderDocList();
            renderDocDropdown();
        } catch (e) {
            showToast('Failed to load documents: ' + e.message, true);
        }
    }

    async function loadDocsForSelectedKbs() {
        const selectedKbs = typeof window.selectedKbs !== 'undefined' ? window.selectedKbs : new Set();
        const kbNames = Array.from(selectedKbs);
        // Clear previous selections when KB list changes
        selectedDocs.clear();
        updateSelectedCount();
        
        if (kbNames.length === 0) {
            allDocs = [];
            renderDocDropdown();
            return;
        }
        allDocs = [];
        for (const kbName of kbNames) {
            try {
                const data = await apiCall(`/api/kb/${encodeURIComponent(kbName)}/documents`);
                const docs = (data.documents || []).map(d => ({...d, _kb: kbName}));
                allDocs = allDocs.concat(docs);
            } catch (e) {
                // Silently skip KBs that don't exist or have errors
                if (!e.message.includes('KB not found')) {
                    console.error('[KbAnalytics] Failed to load docs for', kbName, e);
                }
            }
        }
        renderDocDropdown();
        updateSelectedCount();
    }

    function renderDocDropdown() {
        const container = document.getElementById('analyticsDocDropdownList');
        if (!container) return;
        if (allDocs.length === 0) {
            container.innerHTML = '<div class="empty-state" style="font-size:0.85em;">No documents.</div>';
            return;
        }
        container.innerHTML = allDocs.map(doc => {
            // Use markdown filename (contains author/year) instead of title
            const filename = (doc.markdown_path || '').replace(/\\/g, '/').split('/').pop() || doc.title;
            const displayName = filename.replace(/\.(md|txt)$/i, '');
            return `<label style="display:flex; align-items:center; gap:8px; padding:6px 8px; cursor:pointer; border-radius:4px; font-size:0.85em;">
                <input type="checkbox" class="analytics-doc-cb" value="${doc.doc_id}" onchange="KbAnalytics.onDocToggle(this)">
                <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${displayName}">${displayName}</span>
            </label>`;
        }).join('');
    }

    async function loadDocuments() {
        if (!currentKb) return;
        try {
            const data = await apiCall(`/api/kb/${encodeURIComponent(currentKb)}/documents`);
            allDocs = data.documents || [];
            renderDocList();
        } catch (e) {
            showToast('Failed to load documents: ' + e.message, true);
        }
    }

    function renderDocList() {
        const container = document.getElementById('analyticsDocList');
        if (!container) return;
        if (allDocs.length === 0) {
            container.innerHTML = '<div class="empty-state" style="font-size:0.85em; grid-column:1/-1;">No documents in this KB.</div>';
            updateSelectedCount();
            return;
        }
        container.innerHTML = allDocs.map(doc => `
            <label style="display:flex; align-items:center; gap:8px; padding:6px 8px; cursor:pointer; border-radius:4px; transition:background 0.1s;" 
                   onmouseover="this.style.background='var(--bg-hover)'" onmouseout="this.style.background='transparent'">
                <input type="checkbox" class="analytics-doc-cb" value="${doc.doc_id}" onchange="KbAnalytics.onDocToggle(this)">
                <span style="font-size:0.85em; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1;" title="${doc.title}">${doc.title}</span>
            </label>
        `).join('');
        updateSelectedCount();
    }

    function onDocToggle(cb) {
        if (cb.checked) {
            selectedDocs.add(cb.value);
        } else {
            selectedDocs.delete(cb.value);
        }
        updateSelectedCount();
    }

    function updateSelectedCount() {
        const el = document.getElementById('analyticsSelectedCount');
        if (el) el.textContent = selectedDocs.size + ' / ' + allDocs.length + ' selected';
        const header = document.getElementById('analyticsSelectedCountHeader');
        if (header) header.textContent = selectedDocs.size;
    }

    function selectAllDocs(val) {
        document.querySelectorAll('.analytics-doc-cb').forEach(cb => {
            cb.checked = val;
            if (val) selectedDocs.add(cb.value);
            else selectedDocs.delete(cb.value);
        });
        updateSelectedCount();
    }

    function getSelectedDocIds() {
        return Array.from(selectedDocs);
    }

    function switchTab(tab, btn) {
        currentTab = tab;
        document.querySelectorAll('.analytics-tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.analytics-tab-content').forEach(c => c.classList.remove('active'));
        if (btn) btn.classList.add('active');
        const content = document.getElementById('analytics-tab-' + tab);
        if (content) content.classList.add('active');
    }

    async function runTopicClustering() {
        if (!currentKb) { showToast('Please select a KB first.', true); return; }
        const nClusters = document.getElementById('analyticsNumClusters').value;
        const method = document.getElementById('analyticsClusterMethod').value;
        const body = {};
        if (nClusters) body.n_clusters = parseInt(nClusters);
        if (method) body.method = method;
        const docIds = getSelectedDocIds();
        if (docIds.length > 0) body.doc_ids = docIds;

        const container = document.getElementById('analyticsTopicResults');
        container.innerHTML = '<div class="learning-loading">Running clustering...</div>';

        try {
            const data = await apiCall(`/api/kb/${encodeURIComponent(currentKb)}/analytics/topics`, body);
            renderTopicClusters(data.clusters || []);
        } catch (e) {
            container.innerHTML = '<div class="empty-state" style="color:var(--error);">Error: ' + e.message + '</div>';
        }
    }

    function renderTopicClusters(clusters) {
        const container = document.getElementById('analyticsTopicResults');
        if (!container) return;
        if (clusters.length === 0) {
            container.innerHTML = '<div class="empty-state">No clusters found.</div>';
            return;
        }
        container.innerHTML = clusters.map(c => `
            <div class="analytics-cluster-card" style="background:var(--bg-tertiary); border-radius:8px; padding:16px; border:1px solid var(--border);">
                <h4 style="margin:0 0 8px; font-size:0.95em;">🏷️ ${c.name || 'Topic ' + c.cluster_id}</h4>
                ${c.keywords && c.keywords.length > 0 ? '<div style="margin-bottom:8px;">' + c.keywords.map(k => '<span style="display:inline-block; background:var(--primary); color:#fff; padding:2px 8px; border-radius:12px; font-size:0.75em; margin-right:4px;">' + k + '</span>').join('') + '</div>' : ''}
                <div style="font-size:0.8em; color:var(--text-muted); margin-bottom:8px;">${c.size} documents</div>
                <div style="max-height:120px; overflow-y:auto; font-size:0.8em;">
                    ${c.doc_ids.slice(0, 10).map(id => '<div style="padding:2px 0; border-bottom:1px solid var(--border);">' + (getDocTitle(id) || id) + '</div>').join('')}
                    ${c.doc_ids.length > 10 ? '<div style="color:var(--text-muted);">... and ' + (c.doc_ids.length - 10) + ' more</div>' : ''}
                </div>
            </div>
        `).join('');
    }

    function getDocTitle(docId) {
        const doc = allDocs.find(d => d.doc_id === docId);
        return doc ? doc.title : null;
    }

    async function runPointCloud() {
        if (!currentKb) { showToast('Please select a KB first.', true); return; }
        const dimensions = parseInt(document.getElementById('analyticsPcDimensions').value);
        const method = document.getElementById('analyticsPcMethod').value;
        const includeClusters = document.getElementById('analyticsPcClusters').checked;
        const body = { dimensions, method, include_clusters: includeClusters };
        const docIds = getSelectedDocIds();
        if (docIds.length > 0) body.doc_ids = docIds;

        const statsEl = document.getElementById('analyticsPcStats');
        if (statsEl) statsEl.textContent = 'Generating point cloud...';

        try {
            const data = await apiCall(`/api/kb/${encodeURIComponent(currentKb)}/analytics/point-cloud`, body);
            pointCloudData = data.point_cloud;
            renderPointCloud(pointCloudData);
            if (statsEl) statsEl.textContent = pointCloudData.points.length + ' points projected using ' + pointCloudData.method.toUpperCase() + ' (' + pointCloudData.dimensions + 'D)';
        } catch (e) {
            if (statsEl) statsEl.textContent = 'Error: ' + e.message;
        }
    }

    function renderPointCloud(pc) {
        const canvas = document.getElementById('analyticsPointCloudCanvas');
        if (!canvas || !pc || !pc.points.length) return;

        const ctx = canvas.getContext('2d');
        const rect = canvas.parentElement.getBoundingClientRect();
        canvas.width = rect.width;
        canvas.height = 400;

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        const points = pc.points;
        const xs = points.map(p => p.x);
        const ys = points.map(p => p.y);
        const minX = Math.min(...xs), maxX = Math.max(...xs);
        const minY = Math.min(...ys), maxY = Math.max(...ys);
        const rangeX = maxX - minX || 1, rangeY = maxY - minY || 1;
        const padding = 40;

        const clusterColors = [
            '#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f',
            '#edc948', '#b07aa1', '#ff9da7', '#9c755f', '#bab0ac',
        ];

        points.forEach(p => {
            const x = padding + ((p.x - minX) / rangeX) * (canvas.width - 2 * padding);
            const y = padding + ((p.y - minY) / rangeY) * (canvas.height - 2 * padding);
            const color = clusterColors[p.cluster % clusterColors.length];

            ctx.beginPath();
            ctx.arc(x, y, 6, 0, Math.PI * 2);
            ctx.fillStyle = color;
            ctx.fill();
            ctx.strokeStyle = 'rgba(0,0,0,0.2)';
            ctx.lineWidth = 1;
            ctx.stroke();
        });

        canvas.onmousemove = (e) => {
            const r = canvas.getBoundingClientRect();
            const mx = e.clientX - r.left;
            const my = e.clientY - r.top;
            let found = null;
            for (const p of points) {
                const px = padding + ((p.x - minX) / rangeX) * (canvas.width - 2 * padding);
                const py = padding + ((p.y - minY) / rangeY) * (canvas.height - 2 * padding);
                if (Math.hypot(mx - px, my - py) < 10) { found = p; break; }
            }
            const tooltip = document.getElementById('analyticsPcTooltip');
            if (tooltip && found) {
                tooltip.style.display = 'block';
                tooltip.style.left = (e.clientX - r.left + 15) + 'px';
                tooltip.style.top = (e.clientY - r.top - 10) + 'px';
                tooltip.innerHTML = '<strong>' + (found.label || found.doc_id) + '</strong><br><span style="font-size:0.75em;">' + found.doc_id + '</span>';
            } else if (tooltip) {
                tooltip.style.display = 'none';
            }
        };
        canvas.onmouseleave = () => {
            const tooltip = document.getElementById('analyticsPcTooltip');
            if (tooltip) tooltip.style.display = 'none';
        };
    }

    async function runOpinionClustering() {
        if (!currentKb) { showToast('Please select a KB first.', true); return; }
        const topic = document.getElementById('analyticsOpinionTopic').value;
        const maxClusters = parseInt(document.getElementById('analyticsOpinionMax').value);
        const useLlm = document.getElementById('analyticsOpinionLlm').checked;
        const body = { topic, max_clusters: maxClusters, use_llm: useLlm };
        const docIds = getSelectedDocIds();
        if (docIds.length > 0) body.doc_ids = docIds;

        const container = document.getElementById('analyticsOpinionResults');
        container.innerHTML = '<div class="learning-loading">Analyzing opinions...</div>';

        try {
            const data = await apiCall(`/api/kb/${encodeURIComponent(currentKb)}/analytics/opinions`, body);
            renderOpinionClusters(data.opinion_clusters || []);
        } catch (e) {
            container.innerHTML = '<div class="empty-state" style="color:var(--error);">Error: ' + e.message + '</div>';
        }
    }

    function renderOpinionClusters(clusters) {
        const container = document.getElementById('analyticsOpinionResults');
        if (!container) return;
        if (clusters.length === 0) {
            container.innerHTML = '<div class="empty-state">No opinion clusters found.</div>';
            return;
        }
        const stanceColors = {
            'positive': '#22c55e',
            'negative': '#ef4444',
            'neutral': '#6b7280',
        };

        container.innerHTML = clusters.map(c => {
            let color = '#4e79a7';
            for (const [key, val] of Object.entries(stanceColors)) {
                if (c.stance.toLowerCase().includes(key)) { color = val; break; }
            }
            return `
                <div class="analytics-opinion-card" style="background:var(--bg-tertiary); border-radius:8px; padding:16px; border:1px solid var(--border); margin-bottom:12px;">
                    <div style="display:flex; align-items:center; gap:12px; margin-bottom:8px;">
                        <span style="display:inline-block; width:12px; height:12px; border-radius:50%; background:${color};"></span>
                        <h4 style="margin:0; font-size:0.95em;">${c.stance}</h4>
                        <span style="font-size:0.75em; color:var(--text-muted);">(${c.doc_ids.length} docs, confidence: ${(c.confidence * 100).toFixed(0)}%)</span>
                    </div>
                    ${c.summary ? '<p style="font-size:0.85em; color:var(--text-muted); margin:0 0 8px 24px;">' + c.summary + '</p>' : ''}
                    <div style="max-height:100px; overflow-y:auto; font-size:0.8em; margin-left:24px;">
                        ${c.doc_ids.slice(0, 8).map(id => '<div style="padding:2px 0; border-bottom:1px solid var(--border);">' + (getDocTitle(id) || id) + '</div>').join('')}
                        ${c.doc_ids.length > 8 ? '<div style="color:var(--text-muted);">... and ' + (c.doc_ids.length - 8) + ' more</div>' : ''}
                    </div>
                </div>
            `;
        }).join('');
    }

    async function generateCitedResponse() {
        if (!currentKb) { showToast('Please select a KB first.', true); return; }
        const query = document.getElementById('analyticsCiteQuery').value;
        if (!query) { showToast('Please enter a question.', true); return; }
        if (selectedDocs.size === 0) { showToast('Please select at least one article to cite.', true); return; }

        const context = document.getElementById('analyticsCiteContext').value;
        const body = {
            query,
            required_doc_ids: getSelectedDocIds(),
            additional_context: context,
        };

        const container = document.getElementById('analyticsCiteResults');
        container.innerHTML = '<div class="learning-loading">Generating cited response...</div>';

        try {
            const data = await apiCall(`/api/kb/${encodeURIComponent(currentKb)}/analytics/cite`, body);
            renderCitedResponse(data);
        } catch (e) {
            container.innerHTML = '<div class="empty-state" style="color:var(--error);">Error: ' + e.message + '</div>';
        }
    }

    function renderCitedResponse(data) {
        const container = document.getElementById('analyticsCiteResults');
        if (!container) return;

        let html = '';

        if (data.missing_citations && data.missing_citations.length > 0) {
            html += '<div style="background:var(--bg-warning); border-radius:6px; padding:10px; margin-bottom:12px; font-size:0.85em;">';
            html += '⚠️ Could not find these documents: ' + data.missing_citations.join(', ');
            html += '</div>';
        }

        html += '<div style="background:var(--bg-tertiary); border-radius:8px; padding:16px; border:1px solid var(--border);">';
        html += '<h4 style="margin:0 0 12px;">📎 Cited Response</h4>';
        html += '<div style="white-space:pre-wrap; font-size:0.9em; line-height:1.6;">' + escapeHtml(data.response || '') + '</div>';
        html += '</div>';

        if (data.citations && data.citations.length > 0) {
            html += '<div style="margin-top:12px; font-size:0.85em;">';
            html += '<strong>References:</strong>';
            html += '<ol style="margin:8px 0 0 20px;">';
            data.citations.forEach(c => {
                html += '<li>' + escapeHtml(c.filename || c.title || c.doc_id) + '</li>';
            });
            html += '</ol></div>';
        }

        container.innerHTML = html;
    }

    async function generateReview() {
        if (!currentKb) { showToast('Please select a KB first.', true); return; }
        if (selectedDocs.size === 0) { showToast('Please select at least one article.', true); return; }

        const topic = document.getElementById('analyticsReviewTopic').value;
        const mode = document.getElementById('analyticsReviewMode').value;
        const style = document.getElementById('analyticsReviewStyle').value;
        const language = document.getElementById('analyticsReviewLang').value;
        const body = {
            doc_ids: getSelectedDocIds(),
            topic,
            mode,
            style,
            language,
        };

        const container = document.getElementById('analyticsReviewResults');
        const loadingText = mode === 'paper' ? 'Generating academic paper...' : 'Generating literature review...';
        container.innerHTML = '<div class="learning-loading">' + loadingText + '</div>';

        try {
            const data = await apiCall(`/api/kb/${encodeURIComponent(currentKb)}/analytics/review`, body);
            renderReview(data);
        } catch (e) {
            container.innerHTML = '<div class="empty-state" style="color:var(--error);">Error: ' + e.message + '</div>';
        }
    }

    function renderReview(data) {
        const container = document.getElementById('analyticsReviewResults');
        if (!container) return;

        let html = '';

        if (data.missing_citations && data.missing_citations.length > 0) {
            html += '<div style="background:var(--bg-warning); border-radius:6px; padding:10px; margin-bottom:12px; font-size:0.85em;">';
            html += '⚠️ Could not find these documents: ' + data.missing_citations.join(', ');
            html += '</div>';
        }

        html += '<div style="background:var(--bg-tertiary); border-radius:8px; padding:16px; border:1px solid var(--border);">';
        html += '<h4 style="margin:0 0 12px;">📝 Literature Review</h4>';
        html += '<div style="white-space:pre-wrap; font-size:0.9em; line-height:1.6;">' + escapeHtml(data.review || '') + '</div>';
        html += '</div>';

        if (data.citations && data.citations.length > 0) {
            html += '<div style="margin-top:12px; font-size:0.85em;">';
            html += '<strong>References (' + data.citations.length + '):</strong>';
            html += '<ol style="margin:8px 0 0 20px;">';
            data.citations.forEach(c => {
                html += '<li>' + escapeHtml(c.filename || c.title || c.doc_id) + '</li>';
            });
            html += '</ol></div>';
        }

        container.innerHTML = html;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    async function loadDimensionInfo() {
        if (!currentKb) { showToast('Please select a KB first.', true); return; }
        const container = document.getElementById('analyticsDimInfo');
        container.innerHTML = '<div class="learning-loading">Loading dimension info...</div>';
        try {
            const data = await apiCall(`/api/kb/${encodeURIComponent(currentKb)}/dimension-info`);
            const compatible = data.compatible;
            const statusColor = compatible ? '#22c55e' : '#ef4444';
            const statusText = compatible ? '✅ Compatible' : '❌ Incompatible';
            container.innerHTML = `
                <div style="background:var(--bg-tertiary); border-radius:8px; padding:16px; border:1px solid var(--border);">
                    <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(200px, 1fr)); gap:12px;">
                        <div><strong>KB Name</strong><div style="font-size:0.9em; margin-top:4px;">${escapeHtml(data.kb_display || data.kb_name)}</div></div>
                        <div><strong>Embedding Model</strong><div style="font-size:0.9em; margin-top:4px;">${escapeHtml(data.embedding_model || 'N/A')}</div></div>
                        <div><strong>Dimension</strong><div style="font-size:0.9em; margin-top:4px;">${data.dimension || 0}</div></div>
                        <div><strong>Documents</strong><div style="font-size:0.9em; margin-top:4px;">${data.doc_count || 0}</div></div>
                        <div><strong>Current Model</strong><div style="font-size:0.9em; margin-top:4px;">${escapeHtml(data.current_model || 'N/A')}</div></div>
                        <div><strong>Compatibility</strong><div style="font-size:0.9em; margin-top:4px; color:${statusColor};">${statusText}</div></div>
                    </div>
                    ${!compatible && data.dimension > 0 ? '<div style="margin-top:12px; font-size:0.85em; color:var(--text-muted);">💡 Consider re-indexing this KB with the current model for best results.</div>' : ''}
                </div>`;
        } catch (e) {
            container.innerHTML = '<div class="empty-state" style="color:var(--error);">Error: ' + e.message + '</div>';
        }
    }

    async function loadDimensionMatrix() {
        const container = document.getElementById('analyticsDimMatrix');
        const content = document.getElementById('analyticsDimMatrixContent');
        container.style.display = 'block';
        content.innerHTML = '<div class="learning-loading">Loading matrix...</div>';
        try {
            const data = await apiCall('/api/kb/dimension-matrix');
            if (data.knowledge_bases.length === 0) {
                content.innerHTML = '<div class="empty-state">No KBs found.</div>';
                return;
            }
            let html = `<div style="font-size:0.85em; margin-bottom:12px; color:var(--text-muted);">Current model: <strong>${escapeHtml(data.current_model || 'N/A')}</strong> (${data.current_dimension}D) — Compatible: ${data.compatible_count}/${data.total}</div>`;
            html += '<table style="width:100%; border-collapse:collapse; font-size:0.85em;">';
            html += '<thead><tr style="border-bottom:2px solid var(--border);"><th style="text-align:left; padding:8px;">KB</th><th style="text-align:left; padding:8px;">Type</th><th style="text-align:left; padding:8px;">Model</th><th style="text-align:right; padding:8px;">Dim</th><th style="text-align:right; padding:8px;">Docs</th><th style="text-align:center; padding:8px;">Status</th></tr></thead>';
            html += '<tbody>';
            data.knowledge_bases.forEach(kb => {
                const compatColor = kb.compatible ? '#22c55e' : (kb.dimension > 0 ? '#ef4444' : '#6b7280');
                const compatText = kb.compatible ? '✅' : (kb.dimension > 0 ? '❌' : '—');
                html += `<tr style="border-bottom:1px solid var(--border);">`;
                html += `<td style="padding:8px;">${escapeHtml(kb.display_name || kb.name)}</td>`;
                html += `<td style="padding:8px;">${kb.type}</td>`;
                html += `<td style="padding:8px;">${escapeHtml(kb.embedding_model || 'N/A')}</td>`;
                html += `<td style="padding:8px; text-align:right;">${kb.dimension || 0}</td>`;
                html += `<td style="padding:8px; text-align:right;">${kb.doc_count || 0}</td>`;
                html += `<td style="padding:8px; text-align:center; color:${compatColor};">${compatText}</td>`;
                html += '</tr>';
            });
            html += '</tbody></table>';
            content.innerHTML = html;
        } catch (e) {
            content.innerHTML = '<div class="empty-state" style="color:var(--error);">Error: ' + e.message + '</div>';
        }
    }

    async function reindexKb() {
        if (!currentKb) { showToast('Please select a KB first.', true); return; }
        const model = document.getElementById('analyticsReindexModel').value.trim();
        const statusEl = document.getElementById('analyticsReindexStatus');
        statusEl.innerHTML = '<div class="learning-loading">Re-indexing... this may take a while.</div>';
        const body = {};
        if (model) body.model = model;
        try {
            const data = await apiCall(`/api/kb/${encodeURIComponent(currentKb)}/reindex`, body);
            if (data.success) {
                statusEl.innerHTML = '<span style="color:#22c55e;">✅ Re-indexed successfully! ' + (data.re_embedded || 0) + ' documents re-embedded.</span>';
                await loadDimensionInfo();
            } else {
                statusEl.innerHTML = '<span style="color:#ef4444;">❌ Failed: ' + escapeHtml(data.error || 'Unknown error') + '</span>';
            }
        } catch (e) {
            statusEl.innerHTML = '<span style="color:#ef4444;">❌ Error: ' + e.message + '</span>';
        }
    }

    return {
        loadKbList,
        onKbChange,
        switchTab,
        runTopicClustering,
        runPointCloud,
        runOpinionClustering,
        generateCitedResponse,
        generateReview,
        selectAllDocs,
        onDocToggle,
        toggleAnalyticsDocDropdown,
        loadDocsForSelectedKbs,
        loadDimensionInfo,
        loadDimensionMatrix,
        reindexKb,
        getSelectedDocIds,
    };
})();

// Expose KbAnalytics globally
window.KbAnalytics = KbAnalytics;

// Expose loadDocsForSelectedKbs globally for chat.js to call
window.loadAnalyticsDocs = function() {
    if (window.KbAnalytics && window.KbAnalytics.loadDocsForSelectedKbs) {
        window.KbAnalytics.loadDocsForSelectedKbs();
    }
};

document.addEventListener('DOMContentLoaded', () => {
    window.KbAnalytics.loadKbList();
    
    // Poll for selectedKbs and load docs
    let pollCount = 0;
    function pollAndLoad() {
        pollCount++;
        if (pollCount > 100) return;
        
        const selectedKbs = typeof window.selectedKbs !== 'undefined' ? window.selectedKbs : new Set();
        console.log('[pollAndLoad] poll', pollCount, 'selectedKbs size:', selectedKbs.size);
        if (selectedKbs.size > 0) {
            window.KbAnalytics.loadDocsForSelectedKbs();
        } else {
            setTimeout(pollAndLoad, 300);
        }
    }
    setTimeout(pollAndLoad, 500);
});
