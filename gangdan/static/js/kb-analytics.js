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

    async function apiCall(url, body = null, opts = null) {
        const fetchOpts = {
            method: body ? 'POST' : 'GET',
            headers: { 'Content-Type': 'application/json' },
        };
        if (body) fetchOpts.body = JSON.stringify(body);
        if (opts && opts.signal) fetchOpts.signal = opts.signal;
        const resp = await fetch(url, fetchOpts);
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
            await loadDocuments(false);
            allDocs.forEach(doc => selectedDocs.add(doc.doc_id));
            renderDocDropdown();
            updateSelectedCount();
        }
    }

    function toggleAnalyticsDocDropdown() {
        const menu = document.getElementById('analyticsDocDropdownMenu');
        if (menu) {
            menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
        }
    }

    async function loadDocuments(shouldRender = true) {
        if (!currentKb) return;
        try {
            const data = await apiCall(`/api/kb/${encodeURIComponent(currentKb)}/documents`);
            allDocs = data.documents || [];
            if (shouldRender) {
                renderDocList();
                renderDocDropdown();
            }
        } catch (e) {
            showToast('Failed to load documents: ' + e.message, true);
        }
    }

    let _docsLoadAbortController = null;
    let _docsLoadCache = {};
    let _docsLoadCacheTTL = 10000;

    async function loadDocsForSelectedKbs() {
        const selectedKbs = typeof window.selectedKbs !== 'undefined' ? window.selectedKbs : new Set();
        const kbNames = Array.from(selectedKbs);
        const prevSelectedDocs = new Set(selectedDocs);
        selectedDocs.clear();
        updateSelectedCount();
        
        if (kbNames.length === 0) {
            allDocs = [];
            renderDocDropdown();
            return;
        }

        if (_docsLoadAbortController) {
            _docsLoadAbortController.abort();
        }
        _docsLoadAbortController = new AbortController();
        const signal = _docsLoadAbortController.signal;

        allDocs = [];
        const now = Date.now();

        for (const kbName of kbNames) {
            if (signal.aborted) return;
            const cacheKey = kbName;
            const cached = _docsLoadCache[cacheKey];
            if (cached && (now - cached.time) < _docsLoadCacheTTL) {
                const docs = cached.docs.map(d => ({...d, _kb: kbName}));
                allDocs = allDocs.concat(docs);
                continue;
            }
            try {
                const fetchOpts = signal ? { signal } : undefined;
                const data = await apiCall(`/api/kb/${encodeURIComponent(kbName)}/documents`, null, fetchOpts);
                if (signal.aborted) return;
                const docs = (data.documents || []).map(d => ({...d, _kb: kbName}));
                _docsLoadCache[cacheKey] = { docs: data.documents || [], time: now };
                allDocs = allDocs.concat(docs);
            } catch (e) {
                if (e.name === 'AbortError') return;
                if (!e.message || !e.message.includes('KB not found')) {
                    console.error('[KbAnalytics] Failed to load docs for', kbName, e);
                }
            }
        }
        for (const doc of allDocs) {
            if (prevSelectedDocs.has(doc.doc_id)) {
                selectedDocs.add(doc.doc_id);
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
        const showKbLabel = new Set(allDocs.map(d => d._kb)).size > 1;
        container.innerHTML = allDocs.map(doc => {
            const filename = (doc.markdown_path || '').replace(/\\/g, '/').split('/').pop() || doc.title;
            const displayName = filename.replace(/\.(md|txt)$/i, '');
            const kbLabel = showKbLabel && doc._kb ? `<span style="font-size:0.75em;color:var(--text-muted);margin-right:4px;">[${doc._kb}]</span>` : '';
            const checked = selectedDocs.has(doc.doc_id) ? 'checked' : '';
            return `<label style="display:flex; align-items:center; gap:8px; padding:6px 8px; cursor:pointer; border-radius:4px; font-size:0.85em;">
                <input type="checkbox" class="analytics-doc-cb" value="${doc.doc_id}" data-kb="${doc._kb || ''}" ${checked} onchange="KbAnalytics.onDocToggle(this)">
                <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${displayName}">${kbLabel}${displayName}</span>
            </label>`;
        }).join('');
    }

    function renderDocList() {
        const container = document.getElementById('analyticsDocList');
        if (!container) return;
        if (allDocs.length === 0) {
            container.innerHTML = '<div class="empty-state" style="font-size:0.85em; grid-column:1/-1;">No documents in this KB.</div>';
            updateSelectedCount();
            return;
        }
        container.innerHTML = allDocs.map(doc => {
            const listChecked = selectedDocs.has(doc.doc_id) ? 'checked' : '';
            return `<label style="display:flex; align-items:center; gap:8px; padding:6px 8px; cursor:pointer; border-radius:4px; transition:background 0.1s;" 
                   onmouseover="this.style.background='var(--bg-hover)'" onmouseout="this.style.background='transparent'">
                <input type="checkbox" class="analytics-doc-cb" value="${doc.doc_id}" ${listChecked} onchange="KbAnalytics.onDocToggle(this)">
                <span style="font-size:0.85em; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1;" title="${doc.title}">${doc.title}</span>
            </label>
        `}).join('');
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
        const container = canvas.parentElement;
        const rect = container.getBoundingClientRect();
        canvas.width = rect.width;
        canvas.height = 500;
        const W = canvas.width, H = canvas.height;

        // 3D rotation state
        let rotX = 0, rotY = 0, dragging = false, dragStart = { x: 0, y: 0 };

        const clusterColors = [
            '#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f',
            '#edc948', '#b07aa1', '#ff9da7', '#9c755f', '#bab0ac',
        ];
        const clusterBgColors = clusterColors.map(c => c + '33'); // transparent versions

        function project3D(px, py, pz) {
            const cosX = Math.cos(rotX), sinX = Math.sin(rotX);
            const cosY = Math.cos(rotY), sinY = Math.sin(rotY);
            // Rotate around Y axis
            let x = px * cosY + pz * sinY;
            let z = -px * sinY + pz * cosY;
            // Rotate around X axis
            let y = py * cosX - z * sinX;
            return { x, y };
        }

        function computeBounds(pts) {
            if (pc.dimensions === 3) {
                const projected = pts.map(p => project3D(p.x || 0, p.y || 0, p.z || 0));
                const xs = projected.map(p => p.x), ys = projected.map(p => p.y);
                return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
            }
            const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
            return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
        }

        function draw() {
            ctx.clearRect(0, 0, W, H);

            // Background
            ctx.fillStyle = 'var(--bg-tertiary, #1a1a2e)';
            ctx.fillRect(0, 0, W, H);

            // Grid
            ctx.strokeStyle = 'rgba(128,128,128,0.1)';
            ctx.lineWidth = 0.5;
            for (let i = 40; i < W; i += 40) { ctx.beginPath(); ctx.moveTo(i, 40); ctx.lineTo(i, H - 40); ctx.stroke(); }
            for (let i = 40; i < H; i += 40) { ctx.beginPath(); ctx.moveTo(40, i); ctx.lineTo(W - 40, i); ctx.stroke(); }

            const points = pc.points;
            const bounds = computeBounds(points);
            const padding = 60;
            const rangeX = bounds.maxX - bounds.minX || 1, rangeY = bounds.maxY - bounds.minY || 1;

            function toScreen(px, py) {
                return {
                    sx: padding + ((px - bounds.minX) / rangeX) * (W - 2 * padding),
                    sy: H - padding - ((py - bounds.minY) / rangeY) * (H - 2 * padding),
                };
            }

            // Build cluster data
            const clusters = {};
            points.forEach(p => {
                if (!clusters[p.cluster]) clusters[p.cluster] = { points: [], label: '' };
                clusters[p.cluster].points.push(p);
            });

            // Assign cluster labels from most common keyword
            Object.keys(clusters).forEach(cid => {
                const pts = clusters[cid].points;
                const labels = pts.map(p => p.label || '').filter(Boolean);
                if (labels.length > 0) {
                    const words = labels.join(' ').split(/[\s-]+/).filter(w => w.length > 3);
                    const freq = {};
                    words.forEach(w => { freq[w] = (freq[w] || 0) + 1; });
                    const top = Object.entries(freq).sort((a, b) => b[1] - a[1]).slice(0, 2);
                    clusters[cid].label = top.map(t => t[0]).join('/') || 'C' + cid;
                }
            });

            // Draw cluster hulls
            Object.entries(clusters).forEach(([cid, cl]) => {
                const color = clusterColors[parseInt(cid) % clusterColors.length];
                if (cl.points.length >= 3) {
                    const screenPts = cl.points.map(p => {
                        if (pc.dimensions === 3) {
                            const p3 = project3D(p.x || 0, p.y || 0, p.z || 0);
                            return toScreen(p3.x, p3.y);
                        }
                        return toScreen(p.x, p.y);
                    });
                    // Compute convex hull (simple: average center + radius)
                    const cx = screenPts.reduce((s, p) => s + p.sx, 0) / screenPts.length;
                    const cy = screenPts.reduce((s, p) => s + p.sy, 0) / screenPts.length;
                    const maxDist = Math.max(...screenPts.map(p => Math.hypot(p.sx - cx, p.sy - cy)));
                    ctx.beginPath();
                    ctx.ellipse(cx, cy, maxDist + 15, maxDist + 12, 0, 0, Math.PI * 2);
                    ctx.fillStyle = clusterBgColors[parseInt(cid) % clusterBgColors.length];
                    ctx.fill();
                    ctx.strokeStyle = color + '66';
                    ctx.setLineDash([4, 4]);
                    ctx.stroke();
                    ctx.setLineDash([]);
                }
            });

            // Draw points
            points.forEach(p => {
                let px = p.x, py = p.y;
                if (pc.dimensions === 3) {
                    const p3 = project3D(p.x || 0, p.y || 0, p.z || 0);
                    px = p3.x; py = p3.y;
                }
                const { sx, sy } = toScreen(px, py);
                const color = clusterColors[p.cluster % clusterColors.length];

                // Glow
                ctx.beginPath();
                ctx.arc(sx, sy, 9, 0, Math.PI * 2);
                ctx.fillStyle = color + '44';
                ctx.fill();

                // Point
                ctx.beginPath();
                ctx.arc(sx, sy, 6, 0, Math.PI * 2);
                ctx.fillStyle = color;
                ctx.fill();
                ctx.strokeStyle = '#fff';
                ctx.lineWidth = 1.5;
                ctx.stroke();

                // Short label
                const label = (p.label || p.doc_id || '').replace(/\.md$/, '');
                const shortLabel = label.length > 18 ? label.substring(0, 16) + '..' : label;
                ctx.fillStyle = 'rgba(255,255,255,0.9)';
                ctx.font = '9px monospace';
                ctx.fillText(shortLabel, sx - 25, sy - 12);
            });

            // Legend
            ctx.fillStyle = 'rgba(0,0,0,0.7)';
            ctx.fillRect(W - 180, 8, 172, 28 + Object.keys(clusters).length * 22);
            ctx.font = '11px sans-serif';
            ctx.fillStyle = '#fff';
            ctx.fillText('📊 Clusters', W - 170, 28);
            Object.entries(clusters).forEach(([cid, cl], i) => {
                const color = clusterColors[parseInt(cid) % clusterColors.length];
                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(W - 165, 45 + i * 22, 5, 0, Math.PI * 2);
                ctx.fill();
                ctx.fillStyle = '#ddd';
                ctx.fillText(cl.label + ' (' + cl.points.length + ')', W - 155, 49 + i * 22);
            });

            // 3D hint
            if (pc.dimensions === 3) {
                ctx.fillStyle = 'rgba(255,255,255,0.5)';
                ctx.font = '10px sans-serif';
                ctx.fillText('🖱️ Drag to rotate 3D view', 8, H - 8);
            }
        }

        // Mouse events
        canvas.onmousedown = (e) => {
            if (pc.dimensions === 3) {
                dragging = true;
                dragStart = { x: e.clientX, y: e.clientY };
            }
        };
        window.addEventListener('mousemove', (e) => {
            if (dragging && pc.dimensions === 3) {
                rotY += (e.clientX - dragStart.x) * 0.005;
                rotX += (e.clientY - dragStart.y) * 0.005;
                dragStart = { x: e.clientX, y: e.clientY };
                draw();
            }
            // Tooltip
            const r = canvas.getBoundingClientRect();
            const mx = e.clientX - r.left, my = e.clientY - r.top;
            const points = pc.points;
            const bounds = computeBounds(points);
            const rangeX = bounds.maxX - bounds.minX || 1, rangeY = bounds.maxY - bounds.minY || 1;
            const padding = 60;
            let found = null;
            for (const p of points) {
                let px = p.x, py = p.y;
                if (pc.dimensions === 3) {
                    const p3 = project3D(p.x || 0, p.y || 0, p.z || 0);
                    px = p3.x; py = p3.y;
                }
                const sx = padding + ((px - bounds.minX) / rangeX) * (W - 2 * padding);
                const sy = H - padding - ((py - bounds.minY) / rangeY) * (H - 2 * padding);
                if (Math.hypot(mx - sx, my - sy) < 12) { found = p; break; }
            }
            const tooltip = document.getElementById('analyticsPcTooltip');
            if (tooltip && found) {
                tooltip.style.display = 'block';
                tooltip.style.left = (e.clientX - r.left + 15) + 'px';
                tooltip.style.top = (e.clientY - r.top - 10) + 'px';
                const label = (found.label || found.doc_id).replace(/\.md$/, '');
                tooltip.innerHTML = '<strong>' + label + '</strong><br><span style="font-size:0.75em;">Cluster ' + found.cluster + '</span>';
            } else if (tooltip) {
                tooltip.style.display = 'none';
            }
        });
        window.addEventListener('mouseup', () => { dragging = false; });
        canvas.onmouseleave = () => {
            const tooltip = document.getElementById('analyticsPcTooltip');
            if (tooltip) tooltip.style.display = 'none';
        };

        // Click handler: show document summary
        canvas.onclick = (e) => {
            const r = canvas.getBoundingClientRect();
            const mx = e.clientX - r.left, my = e.clientY - r.top;
            const points = pc.points;
            const bounds = computeBounds(points);
            const rangeX = bounds.maxX - bounds.minX || 1, rangeY = bounds.maxY - bounds.minY || 1;
            const padding = 60;
            let found = null;
            for (const p of points) {
                let px = p.x, py = p.y;
                if (pc.dimensions === 3) {
                    const p3 = project3D(p.x || 0, p.y || 0, p.z || 0);
                    px = p3.x; py = p3.y;
                }
                const sx = padding + ((px - bounds.minX) / rangeX) * (W - 2 * padding);
                const sy = H - padding - ((py - bounds.minY) / rangeY) * (H - 2 * padding);
                if (Math.hypot(mx - sx, my - sy) < 12) { found = p; break; }
            }
            if (found) {
                const label = (found.label || found.doc_id).replace(/\.md$/, '');
                const summary = found.summary || 'No summary available.';
                showDocDetailPopup(label, summary, e.clientX, e.clientY);
            }
        };

        draw();
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

    function showDocDetailPopup(title, summary, cx, cy) {
        // Remove existing popup
        const existing = document.getElementById('analyticsPcPopup');
        if (existing) existing.remove();

        const popup = document.createElement('div');
        popup.id = 'analyticsPcPopup';
        popup.style.cssText = `
            position:fixed; background:rgba(10,10,30,0.95); color:#eee; padding:14px 18px;
            border-radius:10px; font-size:0.85em; max-width:380px; z-index:9999;
            box-shadow:0 4px 24px rgba(0,0,0,0.5); border:1px solid rgba(255,255,255,0.15);
            left:${Math.min(cx, window.innerWidth - 400)}px; top:${Math.max(10, cy - 200)}px;
            line-height:1.5; pointer-events:auto;
        `;
        popup.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <strong style="color:#4ea7f2; font-size:0.95em;">📄 ${escapeHtml(title)}</strong>
                <button onclick="this.parentElement.parentElement.remove()" style="background:none;border:none;color:#999;cursor:pointer;font-size:1.2em;">&times;</button>
            </div>
            <div style="font-size:0.85em; color:#ccc; white-space:pre-wrap;">${escapeHtml(summary)}</div>
        `;
        document.body.appendChild(popup);

        // Close on outside click
        setTimeout(() => {
            document.addEventListener('click', function closePopup(e) {
                if (!popup.contains(e.target)) {
                    popup.remove();
                    document.removeEventListener('click', closePopup);
                }
            });
        }, 0);
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
        invalidateDocsCache: function(kbName) {
            if (kbName) {
                delete _docsLoadCache[kbName];
            } else {
                _docsLoadCache = {};
            }
        },
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
