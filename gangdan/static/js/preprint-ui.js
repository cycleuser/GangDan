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

    function getT(key) {
        if (window.i18n && window.i18n.t) return window.i18n.t(key);
        return key;
    }

    function getPlatforms() {
        const platforms = [];
        if (document.getElementById("pp-arxiv")?.checked) platforms.push("arxiv");
        if (document.getElementById("pp-biorxiv")?.checked) platforms.push("biorxiv");
        if (document.getElementById("pp-medrxiv")?.checked) platforms.push("medrxiv");
        return platforms.length ? platforms : ["arxiv"];
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

        const platforms = getPlatforms();
        const maxResults = parseInt(document.getElementById("pp-maxResults")?.value || "20");
        const categories = getSelectedCategories();
        const strictMode = document.getElementById("pp-strictMode")?.checked || false;
        const aiRefine = document.getElementById("pp-aiRefine")?.checked || false;

        showSearchStatus(true, aiRefine ? getT("preprint_ai_refining") : getT("preprint_fetching"));
        hideResults();

        try {
            const resp = await fetch("/api/preprint/search", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    query,
                    platforms,
                    max_results: maxResults,
                    categories,
                    strict_mode: strictMode,
                    ai_refine: aiRefine,
                }),
            });
            const data = await resp.json();

            if (data.success) {
                currentResults = data.preprints || [];

                if (data.query_refined) {
                    showRefinedQueryBanner(data.query, data.refined_query);
                } else {
                    hideRefinedQueryBanner();
                }

                renderResults(currentResults, data.html_available, data.tex_available, data.category_counts);
            } else {
                showError(data.error || "Search failed");
            }
        } catch (err) {
            showError(err.message);
        } finally {
            showSearchStatus(false);
        }
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

        try {
            const resp = await fetch("/api/preprint/recent?days=7");
            const data = await resp.json();

            if (data.success) {
                currentResults = data.preprints || [];
                renderResults(currentResults, 0, 0, true);
            } else {
                showError(data.error || "Fetch failed");
            }
        } catch (err) {
            showError(err.message);
        } finally {
            showSearchStatus(false);
        }
    }

    function renderResults(papers, htmlCount, texCount, isRecent = false, categoryCounts = {}) {
        const container = document.getElementById("pp-resultsList");
        const emptyState = document.getElementById("pp-emptyState");

        if (!papers.length) {
            emptyState.style.display = "block";
            emptyState.textContent = getT("preprint_no_results");
            container.style.display = "none";
            return;
        }

        emptyState.style.display = "none";
        container.style.display = "block";

        let html = `<div style="margin-bottom:12px; font-size:0.85em; color:var(--text-muted);">
            ${getT("total")}: ${papers.length}`;
        if (htmlCount > 0) html += ` | <span style="color:#4caf50;">HTML: ${htmlCount}</span>`;
        if (texCount > 0) html += ` | <span style="color:#2196f3;">TeX: ${texCount}</span>`;

        if (Object.keys(categoryCounts).length > 0) {
            html += `<br><span style="font-size:0.9em;">${getT("preprint_category_distribution")}:</span> `;
            const topCats = Object.entries(categoryCounts).sort((a, b) => b[1] - a[1]).slice(0, 5);
            html += topCats.map(([cat, count]) => `<span style="background:var(--bg-secondary); padding:1px 5px; border-radius:3px; margin-right:4px;">${cat}: ${count}</span>`).join("");
        }
        html += `</div>`;

        html += `<div style="display:flex; flex-direction:column; gap:10px;">`;

        papers.forEach((p, idx) => {
            const formatBadge = getFormatBadge(p);
            const platformBadge = getPlatformBadge(p.source_platform);
            const catBadges = getCategoryBadges(p);

            html += `<div class="paper-card" style="padding:12px; background:var(--bg-secondary); border-radius:6px; border:1px solid var(--border); cursor:pointer;" onclick="PreprintUI.showDetail(${idx})">
                <div style="display:flex; justify-content:space-between; align-items:start; gap:8px;">
                    <div style="flex:1;">
                        <div style="font-size:0.9em; font-weight:600; margin-bottom:4px; line-height:1.4;">${escHtml(p.title)}</div>
                        <div style="font-size:0.8em; color:var(--text-muted); margin-bottom:4px;">${escHtml(p.authors?.slice(0, 3).join(", ") || "Unknown")} ${p.authors?.length > 3 ? "et al." : ""}</div>
                        <div style="font-size:0.75em; color:var(--text-muted);">${escHtml(p.abstract?.substring(0, 150) || "")}${(p.abstract?.length || 0) > 150 ? "..." : ""}</div>
                        ${catBadges}
                    </div>
                    <div style="display:flex; gap:4px; flex-shrink:0;">
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
        const colors = { arxiv: "#b71c1c", biorxiv: "#1b5e20", medrxiv: "#0d47a1" };
        const color = colors[platform] || "#666";
        return `<span class="badge" style="background:${color}; color:white; padding:2px 6px; border-radius:3px; font-size:0.7em;">${platform}</span>`;
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
                alert(`Conversion successful! Engine: ${data.engine}`);
            } else {
                alert(`Conversion failed: ${data.error}`);
            }
        } catch (err) {
            alert(`Conversion error: ${err.message}`);
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
                alert("Indexed to knowledge base successfully!");
            } else {
                alert(`Indexing failed: ${data.error}`);
            }
        } catch (err) {
            alert(`Indexing error: ${err.message}`);
        }
    }

    function closeModal() {
        document.getElementById("pp-paperModal").style.display = "none";
        currentModalPaper = null;
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
    };
})();

document.addEventListener("DOMContentLoaded", () => {
    if (typeof PreprintUI !== "undefined") {
        PreprintUI.init();
    }
});
