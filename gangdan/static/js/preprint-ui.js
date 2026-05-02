/**
 * Preprint Intelligence UI
 * Handles preprint search with categories, AI refinement, scheduler, subscriptions.
 */

const PreprintUI = (() => {
    let currentResults = [];
    let currentModalPaper = null;
    let schedulerRunning = false;
    let subscriptions = [];
    let allCategories = {};
    let selectedCategories = [];
    let selectedItems = new Set();
    let currentSort = "relevance";
    let itemStatus = new Map();  // preprint_id -> status string

    function getT(key) {
        if (window.i18n && window.i18n.t) return window.i18n.t(key);
        return key;
    }

    function getPlatforms() {
        const platforms = [];
        if (document.getElementById("pp-arxiv")?.checked) platforms.push("arxiv");
        if (document.getElementById("pp-biorxiv")?.checked) platforms.push("biorxiv");
        if (document.getElementById("pp-medrxiv")?.checked) platforms.push("medrxiv");
        if (document.getElementById("pp-s2")?.checked) platforms.push("semantic_scholar");
        if (document.getElementById("pp-crossref")?.checked) platforms.push("crossref");
        if (document.getElementById("pp-openalex")?.checked) platforms.push("openalex");
        if (document.getElementById("pp-dblp")?.checked) platforms.push("dblp");
        if (document.getElementById("pp-pubmed")?.checked) platforms.push("pubmed");
        if (document.getElementById("pp-github")?.checked) platforms.push("github");
        return platforms.length ? platforms : ["arxiv"];
    }

    function getPreprintPlatforms() {
        const platforms = [];
        if (document.getElementById("pp-arxiv")?.checked) platforms.push("arxiv");
        if (document.getElementById("pp-biorxiv")?.checked) platforms.push("biorxiv");
        if (document.getElementById("pp-medrxiv")?.checked) platforms.push("medrxiv");
        return platforms;
    }

    function getPaperSources() {
        const sources = [];
        if (document.getElementById("pp-s2")?.checked) sources.push("semantic_scholar");
        if (document.getElementById("pp-crossref")?.checked) sources.push("crossref");
        if (document.getElementById("pp-openalex")?.checked) sources.push("openalex");
        if (document.getElementById("pp-dblp")?.checked) sources.push("dblp");
        if (document.getElementById("pp-pubmed")?.checked) sources.push("pubmed");
        if (document.getElementById("pp-github")?.checked) sources.push("github");
        return sources;
    }

    function getSelectedCategories() {
        const sel = document.getElementById("pp-categorySelect");
        if (!sel) return [];
        return Array.from(sel.selectedOptions).map(o => o.value);
    }

    async function loadCategories() {
        const platforms = getPlatforms();
        if (!platforms.includes("arxiv")) {
            document.getElementById("pp-categorySection").style.display = "none";
            return;
        }

        document.getElementById("pp-categorySection").style.display = "block";

        try {
            const resp = await fetch("/api/preprint/categories?platform=arxiv");
            const data = await resp.json();
            if (data.success) {
                allCategories = data.categories || [];
                renderCategorySelect();
            }
        } catch (err) {
            console.error("Failed to load categories:", err);
        }
    }

    function renderCategorySelect() {
        const sel = document.getElementById("pp-categorySelect");
        if (!sel) return;

        let html = "";
        allCategories.forEach(cat => {
            html += `<option value="${cat.code}">${cat.code} - ${cat.name}</option>`;
        });
        sel.innerHTML = html;
    }

    function onPlatformChange() {
        loadCategories();
    }

    function onCategoryChange() {
        selectedCategories = getSelectedCategories();
    }

    async function search() {
        const query = document.getElementById("pp-searchInput")?.value.trim();
        if (!query) return;

        const prePrintPlatforms = getPreprintPlatforms();
        const paperSources = getPaperSources();
        const maxResults = parseInt(document.getElementById("pp-maxResults")?.value || "20");
        const categories = getSelectedCategories();
        const strictMode = document.getElementById("pp-strictMode")?.checked || false;
        const aiRefine = document.getElementById("pp-aiRefine")?.checked || false;

        showSearchStatus(true, getT("preprint_fetching"));
        hideResults();
        selectedItems.clear();
        updateBatchBar();

        let allResults = [];
        let refinedQuery = query;

        // Search preprint sources
        if (prePrintPlatforms.length > 0) {
            try {
                const resp = await fetch("/api/preprint/search", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        query,
                        platforms: prePrintPlatforms,
                        max_results: maxResults,
                        categories,
                        strict_mode: strictMode,
                        ai_refine: aiRefine,
                    }),
                });
                const data = await resp.json();
                if (data.success) {
                    allResults = data.preprints || [];
                    if (data.query_refined && data.refined_query) {
                        refinedQuery = data.refined_query;
                        showRefinedQueryBanner(data.query, data.refined_query);
                    }
                }
            } catch (err) {
                console.error("Preprint search failed:", err);
            }
        }

        // Search paper sources (use refined query if available)
        if (paperSources.length > 0) {
            const paperQuery = (aiRefine && refinedQuery !== query) ? refinedQuery : query;
            try {
                const resp = await fetch("/api/research/search", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        query: paperQuery,
                        sources: paperSources,
                        max_results: maxResults,
                    }),
                });
                const data = await resp.json();
                if (data.results) {
                    const paperResults = data.results.map(r => {
                        const p = r.paper || {};
                        const id = p.doi || p.arxiv_id || `paper-${idx || Math.random().toString(36).substr(2, 8)}`;
                        return {
                            preprint_id: id,
                            title: p.title || "Untitled",
                            authors: p.authors || [],
                            abstract: p.abstract || "",
                            source_platform: p.source || "paper",
                            published_date: p.year || "",
                            category: p.venue || p.journal || "",
                            has_html: false,
                            has_tex: false,
                            html_url: "",
                            tex_source_url: "",
                            pdf_url: p.pdf_url || "",
                            raw_data: { categories: [p.journal || "", p.venue || ""].filter(Boolean) },
                            from_paper_search: true,
                            paper: p,
                        };
                    });
                    allResults = allResults.concat(paperResults);
                }
            } catch (err) {
                console.error("Paper search failed:", err);
            }
        }

        if (allResults.length === 0) {
            showError("No results found");
        } else {
            currentResults = allResults;
            renderResults(currentResults);
        }
        showSearchStatus(false);
    }

    function showRefinedQueryBanner(original, refined) {
        let banner = document.getElementById("pp-refinedBanner");
        if (!banner) {
            banner = document.createElement("div");
            banner.id = "pp-refinedBanner";
            banner.style.cssText = "padding:8px 12px; background:var(--bg-tertiary); border-radius:6px; margin-bottom:12px; font-size:0.85em; border-left:3px solid var(--accent);";
            const container = document.getElementById("pp-resultsContainer");
            container.insertBefore(banner, container.firstChild);
        }
        banner.style.display = "block";
        banner.innerHTML = `<strong>✨ ${getT("preprint_ai_refined")}:</strong><br>
            <span style="color:var(--text-muted);">${escHtml(original)}</span> → <span style="color:var(--accent); font-weight:600;">${escHtml(refined)}</span>`;
    }

    function hideRefinedQueryBanner() {
        const banner = document.getElementById("pp-refinedBanner");
        if (banner) banner.style.display = "none";
    }

    async function fetchRecent() {
        showSearchStatus(true, getT("preprint_fetching"));
        hideResults();
        hideRefinedQueryBanner();
        selectedItems.clear();

        try {
            const resp = await fetch("/api/preprint/recent?days=7");
            const data = await resp.json();

            if (data.success) {
                currentResults = data.preprints || [];
                renderResults(currentResults);
            } else {
                showError(data.error || "Fetch failed");
            }
        } catch (err) {
            showError(err.message);
        } finally {
            showSearchStatus(false);
            updateBatchBar();
        }
    }

    function sortResults() {
        currentSort = document.getElementById("pp-sortOrder")?.value || "relevance";
        if (!currentResults.length) return;
        renderResults(currentResults);
    }

    function applySort(results) {
        const sorted = [...results];
        switch (currentSort) {
            case "date_desc":
                sorted.sort((a, b) => (b.published_date || "").localeCompare(a.published_date || ""));
                break;
            case "date_asc":
                sorted.sort((a, b) => (a.published_date || "").localeCompare(b.published_date || ""));
                break;
            case "title_asc":
                sorted.sort((a, b) => (a.title || "").localeCompare(b.title || ""));
                break;
            case "title_desc":
                sorted.sort((a, b) => (b.title || "").localeCompare(a.title || ""));
                break;
            default:
                break;
        }
        return sorted;
    }

    function renderResults(papers) {
        const container = document.getElementById("pp-resultsList");
        const emptyState = document.getElementById("pp-emptyState");
        const sorted = applySort(papers);

        if (!sorted.length) {
            emptyState.style.display = "block";
            emptyState.textContent = getT("preprint_no_results");
            container.style.display = "none";
            return;
        }

        emptyState.style.display = "none";
        container.style.display = "block";

        let html = `<div style="margin-bottom:12px; font-size:0.85em; color:var(--text-muted);">
            ${getT("total")}: ${sorted.length}</div>`;

        html += `<div style="display:flex; flex-direction:column; gap:10px;">`;

        sorted.forEach((p, idx) => {
            const originalIdx = papers.indexOf(p);
            const formatBadge = getFormatBadge(p);
            const platformBadge = getPlatformBadge(p.source_platform);
            const catBadges = getCategoryBadges(p);
            const checked = selectedItems.has(originalIdx) ? "checked" : "";
            const id = p.preprint_id || p.paper?.doi || p.paper?.arxiv_id || "";
            const status = itemStatus.get(id) || "";
            const statusBadge = status ? getStatusBadge(status) : "";

            html += `<div class="paper-card" style="padding:12px; background:var(--bg-secondary); border-radius:6px; border:1px solid var(--border); ${selectedItems.has(originalIdx) ? 'border:2px solid var(--accent); background:var(--accent-soft);' : ''}">
                <div style="display:flex; align-items:start; gap:8px;">
                    <input type="checkbox" ${checked} onchange="event.stopPropagation(); PreprintUI.toggleSelect(${originalIdx})" style="margin-top:3px; accent-color:var(--accent);">
                    <div style="flex:1; cursor:pointer;" onclick="PreprintUI.showDetail(${originalIdx})">
                        <div style="font-size:0.9em; font-weight:600; margin-bottom:4px; line-height:1.4;">${escHtml(p.title)}</div>
                        <div style="font-size:0.8em; color:var(--text-muted); margin-bottom:4px;">${escHtml(p.authors?.slice(0, 3).join(", ") || "Unknown")} ${p.authors?.length > 3 ? "et al." : ""}</div>
                        <div style="font-size:0.75em; color:var(--text-muted);">${escHtml(p.abstract?.substring(0, 150) || "")}${(p.abstract?.length || 0) > 150 ? "..." : ""}</div>
                        ${catBadges}
                    </div>
                    <div style="display:flex; gap:4px; flex-shrink:0; align-items:center;">
                        ${statusBadge}
                        ${platformBadge}
                        ${formatBadge}
                    </div>
                </div>
                <div style="margin-top:6px; font-size:0.75em; color:var(--text-muted);">
                    ${p.published_date || ""} | ${p.source_platform}
                </div>
            </div>`;
        });

        html += `</div>`;
        container.innerHTML = html;
        updateBatchBar();
    }

    function getCategoryBadges(paper) {
        const raw = paper.raw_data || {};
        const cats = raw.categories || [];
        if (!cats.length) return "";

        const topCats = cats.slice(0, 3).map(c => {
            const parts = c.split(".");
            const label = parts.length > 1 ? parts[1] : parts[0];
            return `<span style="background:var(--accent); color:white; padding:1px 5px; border-radius:3px; font-size:0.65em; margin-right:3px;">${label}</span>`;
        }).join("");

        return `<div style="margin-top:4px;">${topCats}</div>`;
    }

    function getFormatBadge(paper) {
        if (paper.has_html) return `<span class="badge badge-green" style="background:#4caf50; color:white; padding:2px 6px; border-radius:3px; font-size:0.7em;">HTML</span>`;
        if (paper.has_tex) return `<span class="badge badge-blue" style="background:#2196f3; color:white; padding:2px 6px; border-radius:3px; font-size:0.7em;">TeX</span>`;
        return `<span class="badge badge-gray" style="background:#9e9e9e; color:white; padding:2px 6px; border-radius:3px; font-size:0.7em;">PDF</span>`;
    }

    function getPlatformBadge(platform) {
        const colors = { arxiv: "#b71c1c", biorxiv: "#1b5e20", medrxiv: "#0d47a1", semantic_scholar: "#f57c00", crossref: "#7b1fa2", openalex: "#00838f", dblp: "#2e7d32", pubmed: "#1565c0", github: "#37474f", paper: "#6a1b9a" };
        const color = colors[platform] || "#666";
        return `<span class="badge" style="background:${color}; color:white; padding:2px 6px; border-radius:3px; font-size:0.7em;">${platform}</span>`;
    }

    function getStatusBadge(status) {
        const badges = {
            converting: { bg: "#f9a825", text: "⏳ Converting", color: "#fff" },
            converted: { bg: "#2e7d32", text: "✓ Converted", color: "#fff" },
            convert_failed: { bg: "#c62828", text: "✗ Conv Failed", color: "#fff" },
            in_kb: { bg: "#1565c0", text: "📥 In KB", color: "#fff" },
            download_failed: { bg: "#bf360c", text: "⇓ DL Failed", color: "#fff" },
        };
        const b = badges[status] || { bg: "#666", text: status, color: "#fff" };
        return `<span class="badge" style="background:${b.bg}; color:${b.color}; padding:2px 6px; border-radius:3px; font-size:0.7em; white-space:nowrap;" title="${status}">${b.text}</span>`;
    }

    function showDetail(idx) {
        const paper = currentResults[idx];
        if (!paper) return;
        currentModalPaper = paper;

        document.getElementById("pp-modalTitle").textContent = paper.title;
        document.getElementById("pp-modalAuthors").textContent = paper.authors?.join(", ") || "Unknown";

        let meta = `${paper.source_platform} | ${paper.published_date || "Unknown date"}`;
        if (paper.category) meta += ` | ${paper.category}`;
        document.getElementById("pp-modalMeta").textContent = meta;
        document.getElementById("pp-modalAbstract").textContent = paper.abstract || "";

        const raw = paper.raw_data || {};
        const cats = raw.categories || [];
        let formatInfo = `<strong>${getT("preprint_source_format")}:</strong> `;
        if (paper.has_html) formatInfo += `<span style="color:#4caf50;">HTML ✓</span> | `;
        if (paper.has_tex) formatInfo += `<span style="color:#2196f3;">TeX ✓</span> | `;
        formatInfo += `PDF`;
        if (cats.length) {
            formatInfo += `<br><strong>${getT("preprint_categories")}:</strong> ${cats.join(", ")}`;
        }
        document.getElementById("pp-modalFormat").innerHTML = formatInfo;

        const convertBtn = document.getElementById("pp-modalConvertBtn");
        convertBtn.style.display = "inline-block";

        document.getElementById("pp-paperModal").style.display = "flex";
    }

    async function convertFromModal() {
        if (!currentModalPaper) return;
        const paper = currentModalPaper;

        let url = "";
        let contentType = "html";

        if (paper.has_html && paper.html_url) {
            url = paper.html_url;
            contentType = "html";
        } else if (paper.has_tex && paper.tex_source_url) {
            url = paper.tex_source_url;
            contentType = "tex";
        } else if (paper.pdf_url) {
            url = paper.pdf_url;
            contentType = "pdf";
        } else {
            alert("No convertible source available");
            return;
        }

        showSearchStatus(true, getT("preprint_converting"));

        try {
            const resp = await fetch("/api/preprint/convert", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url, content_type: contentType, preprint_id: paper.preprint_id }),
            });
            const data = await resp.json();

            if (data.success) {
                document.getElementById("pp-modalIndexBtn").style.display = "inline-block";
                document.getElementById("pp-modalIndexBtn").dataset.mdPath = data.markdown_path;
                alert((getT("conversion_success") || "Conversion successful") + "! " + (getT("engine") || "Engine") + ": " + (data.engine || "auto"));
            } else {
                alert((getT("conversion_failed") || "Conversion failed") + ": " + (data.error || ""));
            }
        } catch (err) {
            alert((getT("conversion_error") || "Error") + ": " + err.message);
        } finally {
            showSearchStatus(false);
        }
    }

    async function indexFromModal() {
        if (!currentModalPaper) return;
        const btn = document.getElementById("pp-modalIndexBtn");
        const mdPath = btn.dataset.mdPath;

        if (!mdPath) {
            alert("No converted Markdown available");
            return;
        }

        try {
            const resp = await fetch("/api/preprint/kb/index", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ preprint_id: currentModalPaper.preprint_id, markdown_path: mdPath }),
            });
            const data = await resp.json();

            if (data.success) {
                alert((getT("indexed_to_kb") || "Indexed to knowledge base successfully") + "!");
            } else {
                alert((getT("indexing_failed") || "Indexing failed") + ": " + (data.error || ""));
            }
        } catch (err) {
            alert((getT("indexing_error") || "Error") + ": " + err.message);
        }
    }

    function closeModal() {
        document.getElementById("pp-paperModal").style.display = "none";
        currentModalPaper = null;
    }

    function toggleSelect(idx) {
        if (selectedItems.has(idx)) {
            selectedItems.delete(idx);
        } else {
            selectedItems.add(idx);
        }
        updateBatchBar();
    }

    function selectAll(checked) {
        selectedItems.clear();
        if (checked) {
            for (let i = 0; i < currentResults.length; i++) {
                selectedItems.add(i);
            }
        }
        updateBatchBar();
        renderResults(currentResults);
    }

    function updateBatchBar() {
        const batchBar = document.getElementById("pp-batchBar");
        const convertBtn = document.getElementById("pp-batchConvertBtn");
        const kbBtn = document.getElementById("pp-batchKbBtn");
        const countEl = document.getElementById("pp-selectedCount");
        const selectAllCb = document.getElementById("pp-selectAll");

        if (!currentResults.length) {
            batchBar.style.display = "none";
            return;
        }
        batchBar.style.display = "flex";

        const count = selectedItems.size;
        countEl.textContent = count + " selected";
        if (selectAllCb) selectAllCb.checked = count === currentResults.length;

        convertBtn.style.display = count > 0 ? "inline-block" : "none";
        kbBtn.style.display = count > 0 ? "inline-block" : "none";
    }

    async function batchConvert() {
        if (selectedItems.size === 0) return;

        const selected = Array.from(selectedItems).map(idx => currentResults[idx]);
        const total = selected.length;

        selected.forEach(p => { const id = p.preprint_id || p.paper?.doi || p.paper?.arxiv_id || ""; itemStatus.set(id, "converting"); });
        renderResults(currentResults);
        showSearchStatus(true, "Converting 0/" + total + "...");

        const items = selected.map((p, idx) => {
            const pidx = Array.from(selectedItems)[idx];
            let url = "", contentType = "html";
            if (p.has_html && p.html_url) { url = p.html_url; contentType = "html"; }
            else if (p.has_tex && p.tex_source_url) { url = p.tex_source_url; contentType = "tex"; }
            else if (p.pdf_url) { url = p.pdf_url; contentType = "pdf"; }
            return { item_id: p.preprint_id || p.paper?.doi || p.paper?.arxiv_id || String(pidx),
                     title: p.title, url, content_type: contentType, preprint_id: p.preprint_id,
                     authors: p.authors || [], year: p.published_date || "", published_date: p.published_date || "" };
        }).filter(item => item.url);

        if (items.length === 0) {
            selected.forEach(p => { const id = p.preprint_id || p.paper?.doi || p.paper?.arxiv_id || ""; itemStatus.set(id, "download_failed"); });
            renderResults(currentResults);
            alert(getT("no_convertible") || "No convertible URLs found for selected items");
            showSearchStatus(false);
            return;
        }

        try {
            const resp = await fetch("/api/preprint/batch-convert", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ items, create_zip: false }),
            });
            const data = await resp.json();

            // Update statuses from results
            if (data.results) {
                data.results.forEach(r => {
                    const id = r.item_id;
                    if (r.success) itemStatus.set(id, "converted");
                    else itemStatus.set(id, "convert_failed");
                });
                // Show progress
                const converted = data.results.filter(r => r.success).length;
                const failed = data.results.filter(r => !r.success).length;
                showSearchStatus(true, "Converting " + (converted + failed) + "/" + total + "...");
            }
            renderResults(currentResults);

            if (data.success_count !== undefined) {
                const engineInfo = data.results && data.results[0] ? " Engine: " + (data.results[0].engine || "auto") : "";
                alert("Converted " + (data.success_count || 0) + "/" + (data.total || 0) + " items. Failed: " + (data.fail_count || 0) + engineInfo);
            } else if (data.error) {
                alert("Batch convert failed: " + data.error);
            }
        } catch (err) {
            selected.forEach(p => { const id = p.preprint_id || p.paper?.doi || p.paper?.arxiv_id || ""; itemStatus.set(id, "convert_failed"); });
            renderResults(currentResults);
            alert("Error: " + err.message);
        } finally {
            showSearchStatus(false);
        }
    }

    function showAddToKbDialog() {
        if (selectedItems.size === 0) return;
        const dialog = document.getElementById("pp-addKbDialog");
        const select = document.getElementById("pp-existingKbSelect");
        const input = document.getElementById("pp-newKbName");

        // Load KB list into dropdown
        select.innerHTML = '<option value="">' + (getT("create_new_kb") || "Create New KB") + '</option>';
        fetch("/api/kb/list")
            .then(r => r.json())
            .then(data => {
                (data.kbs || []).forEach(kb => {
                    const opt = document.createElement("option");
                    opt.value = kb.name;
                    opt.textContent = (kb.display_name || kb.name) + " (" + (kb.doc_count || 0) + " docs)";
                    select.appendChild(opt);
                });
            }).catch(() => {});

        dialog.style.display = "block";
        input.value = "";
        input.style.display = "block";
    }

    function batchAddToKb() {
        if (selectedItems.size === 0) return;
        const select = document.getElementById("pp-existingKbSelect");
        const input = document.getElementById("pp-newKbName");
        const dialog = document.getElementById("pp-addKbDialog");

        // Get KB name from dialog - either from dropdown or new name input
        let kbName = "";
        if (select.value && select.value !== "") {
            kbName = select.options[select.selectedIndex].text.split(" (")[0]; // display name
        }
        if (!kbName) {
            kbName = input.value.trim();
        }

        if (!kbName) {
            alert(getT("enter_kb_name") || "Please enter or select a knowledge base name");
            return;
        }

        dialog.style.display = "none";
        showSearchStatus(true, getT("preprint_fetching") || "Adding to KB...");

        const preprints = Array.from(selectedItems).map(idx => {
            const p = currentResults[idx];
            const id = p.preprint_id || p.paper?.doi || p.paper?.arxiv_id || "";
            return {
                preprint_id: id, doc_id: id, title: p.title,
                authors: p.authors || [], abstract: p.abstract || "",
                published_date: p.published_date || "",
                source_platform: p.source_platform || "arxiv",
                url: p.pdf_url || "", source_type: "preprint",
            };
        });

        fetch("/api/preprint/add-to-kb", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ kb_name: kbName, preprints, index_to_chroma: true }),
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                selectedItems.forEach(idx => {
                    const p = currentResults[idx];
                    const id = p.preprint_id || p.paper?.doi || p.paper?.arxiv_id || "";
                    itemStatus.set(id, "in_kb");
                });
                renderResults(currentResults);
                alert((getT("added_to_kb") || "Added") + " " + (data.added || 0) + " " + (getT("items") || "items") + (data.skipped ? ", " + data.skipped + " " + (getT("skipped") || "skipped") : ""));
            } else {
                alert((getT("failed") || "Failed") + ": " + (data.error || "Unknown error"));
            }
        })
        .catch(err => alert("Error: " + err.message))
        .finally(() => showSearchStatus(false));
    }

    async function toggleScheduler() {
        const btn = document.getElementById("pp-startScheduler");
        const statusText = document.getElementById("pp-statusText");

        if (schedulerRunning) {
            try {
                const resp = await fetch("/api/preprint/scheduler/stop", { method: "POST" });
                const data = await resp.json();
                if (data.success) {
                    schedulerRunning = false;
                    btn.innerHTML = `▶️ <span data-i18n="preprint_start_scheduler">${getT("preprint_start_scheduler")}</span>`;
                    statusText.textContent = getT("preprint_stopped");
                }
            } catch (err) {
                alert(`Stop failed: ${err.message}`);
            }
        } else {
            const hours = parseInt(document.getElementById("pp-interval")?.value || "24");

            try {
                await fetch("/api/preprint/scheduler/interval", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ hours }),
                });

                const resp = await fetch("/api/preprint/scheduler/start", { method: "POST" });
                const data = await resp.json();
                if (data.success) {
                    schedulerRunning = true;
                    btn.innerHTML = `⏹️ <span data-i18n="preprint_stop_scheduler">${getT("preprint_stop_scheduler")}</span>`;
                    statusText.textContent = getT("preprint_running");
                }
            } catch (err) {
                alert(`Start failed: ${err.message}`);
            }
        }
    }

    async function loadSchedulerStatus() {
        try {
            const resp = await fetch("/api/preprint/scheduler/status");
            const data = await resp.json();
            if (data.success) {
                const status = data.status;
                schedulerRunning = status.running;

                const btn = document.getElementById("pp-startScheduler");
                const statusText = document.getElementById("pp-statusText");

                if (schedulerRunning) {
                    btn.innerHTML = `⏹️ <span data-i18n="preprint_stop_scheduler">${getT("preprint_stop_scheduler")}</span>`;
                    statusText.textContent = getT("preprint_running");
                } else {
                    btn.innerHTML = `▶️ <span data-i18n="preprint_start_scheduler">${getT("preprint_start_scheduler")}</span>`;
                    statusText.textContent = getT("preprint_stopped");
                }

                if (status.interval_hours) {
                    document.getElementById("pp-interval").value = status.interval_hours;
                }
            }
        } catch (err) {
            console.error("Failed to load scheduler status:", err);
        }
    }

    async function loadSubscriptions() {
        try {
            const resp = await fetch("/api/preprint/subscriptions");
            const data = await resp.json();
            if (data.success) {
                subscriptions = data.subscriptions || [];
                renderSubscriptions();
            }
        } catch (err) {
            console.error("Failed to load subscriptions:", err);
        }
    }

    function renderSubscriptions() {
        const container = document.getElementById("pp-subscriptionList");
        if (!subscriptions.length) {
            container.innerHTML = `<div style="color:var(--text-muted); font-size:0.8em;">No subscriptions</div>`;
            return;
        }

        let html = "";
        subscriptions.forEach((sub) => {
            html += `<div style="padding:6px; background:var(--bg-tertiary); border-radius:4px; margin-bottom:4px; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <div style="font-weight:600;">${escHtml(sub.name)}</div>
                    <div style="font-size:0.75em; color:var(--text-muted);">${sub.keywords.join(", ")} | ${sub.total_fetched} fetched</div>
                </div>
                <button onclick="PreprintUI.removeSubscription('${escHtml(sub.name)}')" style="background:none; border:none; color:var(--danger); cursor:pointer; font-size:1.1em;">&times;</button>
            </div>`;
        });
        container.innerHTML = html;
    }

    async function addSubscription() {
        const name = document.getElementById("pp-subName")?.value.trim();
        const keywordsStr = document.getElementById("pp-subKeywords")?.value.trim();

        if (!name || !keywordsStr) {
            alert("Name and keywords are required");
            return;
        }

        const keywords = keywordsStr.split(",").map(k => k.trim()).filter(Boolean);
        const platforms = getPlatforms();

        try {
            const resp = await fetch("/api/preprint/subscriptions", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name, keywords, platforms }),
            });
            const data = await resp.json();

            if (data.success) {
                document.getElementById("pp-subName").value = "";
                document.getElementById("pp-subKeywords").value = "";
                await loadSubscriptions();
            } else {
                alert(`Failed: ${data.error}`);
            }
        } catch (err) {
            alert(`Error: ${err.message}`);
        }
    }

    async function removeSubscription(name) {
        if (!confirm(`Remove subscription "${name}"?`)) return;

        try {
            const resp = await fetch(`/api/preprint/subscriptions/${encodeURIComponent(name)}`, { method: "DELETE" });
            const data = await resp.json();

            if (data.success) {
                await loadSubscriptions();
            } else {
                alert(`Failed: ${data.error}`);
            }
        } catch (err) {
            alert(`Error: ${err.message}`);
        }
    }

    function showSearchStatus(show, text = "") {
        const el = document.getElementById("pp-searchStatus");
        const textEl = document.getElementById("pp-statusSearch");
        if (show) {
            el.style.display = "block";
            textEl.textContent = text || getT("preprint_fetching");
        } else {
            el.style.display = "none";
        }
    }

    function hideResults() {
        document.getElementById("pp-emptyState").style.display = "none";
        document.getElementById("pp-resultsList").style.display = "none";
    }

    function showError(msg) {
        const container = document.getElementById("pp-resultsList");
        const emptyState = document.getElementById("pp-emptyState");
        emptyState.style.display = "block";
        emptyState.textContent = `Error: ${msg}`;
        container.style.display = "none";
    }

    function escHtml(str) {
        if (!str) return "";
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    function handleSearchKey(e) {
        if (e.key === "Enter") search();
    }

    function init() {
        const searchInput = document.getElementById("pp-searchInput");
        if (searchInput) {
            searchInput.addEventListener("keydown", handleSearchKey);
        }

        loadCategories();
        loadSchedulerStatus();
        loadSubscriptions();
    }

    return {
        init,
        search,
        fetchRecent,
        showDetail,
        convertFromModal,
        indexFromModal,
        closeModal,
        toggleScheduler,
        addSubscription,
        removeSubscription,
        onPlatformChange,
        onCategoryChange,
        toggleSelect,
        selectAll,
        sortResults,
        batchConvert,
        batchAddToKb,
        showAddToKbDialog,
    };
})();

document.addEventListener("DOMContentLoaded", () => {
    if (typeof PreprintUI !== "undefined") {
        PreprintUI.init();
    }
});
