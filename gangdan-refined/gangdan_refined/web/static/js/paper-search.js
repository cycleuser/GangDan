/**
 * Paper Search & Library - Frontend Module
 *
 * Provides UI for:
 * - Paper search with autocomplete
 * - Search results display
 * - Paper details modal with citations/references
 * - PDF download management
 * - Downloaded papers library
 * - Research settings
 *
 * All UI strings use getT() for i18n support.
 */

const PaperSearch = {
    searchResults: [],
    selectedPapers: new Set(),
    currentPaper: null,
    downloadedPapers: [],
    isSearching: false,

    init() {
        this.loadDownloadedPapers();
        this.loadSettings();
    },

    // ==================== Search ====================

    handleSearchKey(event) {
        if (event.key === 'Enter') {
            this.search();
        } else {
            this.handleAutocomplete(event.target.value);
        }
    },

    async handleAutocomplete(query) {
        const dropdown = document.getElementById('p-autocomplete');
        if (query.length < 3) {
            dropdown.style.display = 'none';
            return;
        }

        try {
            const resp = await fetch(`/api/research/autocomplete?q=${encodeURIComponent(query)}&limit=5`);
            const data = await resp.json();
            const suggestions = data.suggestions || [];

            if (suggestions.length === 0) {
                dropdown.style.display = 'none';
                return;
            }

            dropdown.innerHTML = suggestions.map((s, i) =>
                `<div class="autocomplete-item ${i === 0 ? 'active' : ''}" onclick="PaperSearch.selectAutocomplete('${s.replace(/'/g, "\\'")}')">${s}</div>`
            ).join('');
            dropdown.style.display = 'block';
        } catch (e) {
            dropdown.style.display = 'none';
        }
    },

    selectAutocomplete(value) {
        document.getElementById('p-searchInput').value = value;
        document.getElementById('p-autocomplete').style.display = 'none';
        this.search();
    },

    async search() {
        const query = document.getElementById('p-searchInput').value.trim();
        if (!query || this.isSearching) return;

        this.isSearching = true;
        this.selectedPapers.clear();
        this.updateDownloadBtn();

        const sources = this.getSelectedSources();
        const maxResults = parseInt(document.getElementById('p-maxResults').value) || 10;
        const expandQuery = document.getElementById('p-expandQuery').checked;

        document.getElementById('p-searchStatus').style.display = 'block';
        document.getElementById('p-statusText').textContent = getT('searching');
        document.getElementById('p-emptyState').style.display = 'none';
        document.getElementById('p-resultsList').style.display = 'none';

        try {
            const resp = await fetch('/api/research/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query,
                    sources,
                    max_results: maxResults,
                    expand_query: expandQuery,
                }),
            });

            const data = await resp.json();
            this.searchResults = data.results || [];

            document.getElementById('p-searchStatus').style.display = 'none';
            this.renderResults();
        } catch (e) {
            document.getElementById('p-statusText').textContent = `${getT('download_failed')}: ${e.message}`;
            setTimeout(() => {
                document.getElementById('p-searchStatus').style.display = 'none';
            }, 3000);
        } finally {
            this.isSearching = false;
        }
    },

    getSelectedSources() {
        const checkboxes = document.querySelectorAll('#p-sourceFilters input[type="checkbox"]:checked');
        return Array.from(checkboxes).map(cb => cb.value);
    },

    renderResults() {
        const container = document.getElementById('p-resultsList');

        if (this.searchResults.length === 0) {
            container.innerHTML = `<div class="empty-state">${getT('no_papers_found')}</div>`;
            container.style.display = 'block';
            return;
        }

        container.innerHTML = this.searchResults.map((r, i) => {
            const p = r.paper;
            const badges = [];
            if (p.pdf_url) badges.push('<span class="paper-badge oa">OA</span>');
            if (p.citations > 0) badges.push(`<span class="paper-badge">${p.citations} ${getT('citations')}</span>`);
            badges.push(`<span class="paper-badge">${p.source}</span>`);

            return `
                <div class="paper-result-item" onclick="PaperSearch.showPaperDetails(${i})">
                    <div class="paper-result-header">
                        <div class="paper-result-title">${this.escapeHtml(p.title || getT('untitled'))}</div>
                        <div class="paper-result-checkbox">
                            <input type="checkbox" onclick="event.stopPropagation(); PaperSearch.toggleSelect(${i})" ${this.selectedPapers.has(i) ? 'checked' : ''}>
                        </div>
                    </div>
                    <div class="paper-result-meta">
                        <span>${this.escapeHtml(this.formatAuthors(p.authors))}</span>
                        <span>${p.year || getT('na')}</span>
                        ${p.journal ? `<span>${this.escapeHtml(p.journal)}</span>` : ''}
                    </div>
                    ${p.abstract ? `<div class="paper-result-abstract">${this.escapeHtml(p.abstract.substring(0, 200))}...</div>` : ''}
                    <div class="paper-result-badges">${badges.join('')}</div>
                </div>
            `;
        }).join('');

        container.style.display = 'block';
    },

    // ==================== Selection & Download ====================

    toggleSelect(index) {
        if (this.selectedPapers.has(index)) {
            this.selectedPapers.delete(index);
        } else {
            this.selectedPapers.add(index);
        }
        this.updateDownloadBtn();
    },

    updateDownloadBtn() {
        const btn = document.getElementById('p-downloadBtn');
        const count = this.selectedPapers.size;
        btn.style.display = count > 0 ? 'block' : 'none';
        document.getElementById('p-selectedCount').textContent = `(${count})`;
    },

    async downloadSelected() {
        const papers = Array.from(this.selectedPapers).map(i => this.searchResults[i].paper);
        if (papers.length === 0) return;

        const btn = document.getElementById('p-downloadBtn');
        btn.disabled = true;
        btn.innerHTML = `⬇️ ${getT('downloading')}`;

        for (const paper of papers) {
            try {
                await fetch('/api/research/download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        paper: paper,
                        rename: document.getElementById('p-autoRename').checked,
                        convert: document.getElementById('p-autoConvert').checked,
                    }),
                });
            } catch (e) {
                console.error(`Failed to download ${paper.title}:`, e);
            }
        }

        btn.disabled = false;
        btn.innerHTML = `⬇️ <span data-i18n="download_selected">${getT('download_selected')}</span> <span id="p-selectedCount">(0)</span>`;
        this.selectedPapers.clear();
        this.updateDownloadBtn();
        this.loadDownloadedPapers();
        showToast(getT('download_complete'));
    },

    async downloadFromModal() {
        if (!this.currentPaper) return;

        const btn = document.getElementById('p-modalDownloadBtn');
        btn.disabled = true;
        btn.textContent = getT('downloading');

        try {
            const resp = await fetch('/api/research/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    paper: this.currentPaper,
                    rename: document.getElementById('p-autoRename').checked,
                    convert: document.getElementById('p-autoConvert').checked,
                }),
            });

            const data = await resp.json();
            if (data.record && data.record.local_pdf) {
                showToast(getT('download_complete'));
                this.loadDownloadedPapers();
            } else {
                showToast(`${getT('download_failed')}: ${data.error || getT('unknown')}`);
            }
        } catch (e) {
            showToast(`${getT('download_failed')}: ${e.message}`);
        } finally {
            btn.disabled = false;
            btn.innerHTML = `⬇️ ${getT('download_pdf')}`;
        }
    },

    // ==================== Paper Details ====================

    showPaperDetails(index) {
        const result = this.searchResults[index];
        if (!result) return;

        this.currentPaper = result.paper;
        const p = this.currentPaper;

        document.getElementById('p-modalTitle').textContent = p.title || getT('untitled');
        document.getElementById('p-modalAuthors').textContent = this.formatAuthors(p.authors);

        const metaParts = [];
        if (p.year) metaParts.push(`${getT('year')}: ${p.year}`);
        if (p.journal) metaParts.push(`${getT('journal')}: ${p.journal}`);
        if (p.venue) metaParts.push(`${getT('venue')}: ${p.venue}`);
        if (p.doi) metaParts.push(`DOI: ${p.doi}`);
        if (p.citations) metaParts.push(`${getT('citations')}: ${p.citations}`);
        document.getElementById('p-modalMeta').textContent = metaParts.join(' | ');

        document.getElementById('p-modalAbstract').textContent = p.abstract || 'No abstract available';
        document.getElementById('p-relatedPapers').innerHTML = `<div class="empty-state">${getT('click_tab_load_related')}</div>`;

        document.getElementById('p-paperModal').style.display = 'flex';

        // Reset tabs with translated labels
        const tabs = document.querySelectorAll('.paper-tab');
        if (tabs.length >= 3) {
            tabs[0].textContent = getT('citations');
            tabs[1].textContent = getT('references');
            tabs[2].textContent = getT('similar_papers');
        }
        tabs.forEach(t => t.classList.remove('active'));
        if (tabs.length > 0) tabs[0].classList.add('active');
    },

    closeModal() {
        document.getElementById('p-paperModal').style.display = 'none';
        this.currentPaper = null;
    },

    async loadRelated(relation) {
        if (!this.currentPaper) return;

        // Update tabs
        const tabs = document.querySelectorAll('.paper-tab');
        const relationLabels = { citations: getT('citations'), references: getT('references'), recommendations: getT('similar_papers') };
        tabs.forEach(t => {
            t.classList.toggle('active', t.textContent === relationLabels[relation]);
        });

        const container = document.getElementById('p-relatedPapers');
        container.innerHTML = `<div class="learning-loading"></div> ${getT('loading')}`;

        // Get paper ID
        const paperId = this.currentPaper.doi || this.currentPaper.arxiv_id || '';
        if (!paperId) {
            container.innerHTML = `<div class="empty-state">${getT('no_paper_id')}</div>`;
            return;
        }

        try {
            const resp = await fetch(`/api/research/paper/${encodeURIComponent(paperId)}/${relation}?limit=10`);
            const data = await resp.json();
            const papers = data.papers || [];

            if (papers.length === 0) {
                container.innerHTML = `<div class="empty-state">${getT('no_related_papers')}</div>`;
                return;
            }

            container.innerHTML = papers.map(p => `
                <div class="related-paper-item">
                    <div class="related-paper-title">${this.escapeHtml(p.title || getT('untitled'))}</div>
                    <div class="related-paper-meta">
                        ${this.escapeHtml(this.formatAuthors(p.authors))} (${p.year || getT('na')})
                        ${p.citations ? ` - ${p.citations} ${getT('citations')}` : ''}
                    </div>
                </div>
            `).join('');
        } catch (e) {
            container.innerHTML = `<div class="empty-state">${getT('download_failed')}: ${e.message}</div>`;
        }
    },

    // ==================== Downloaded Papers Library ====================

    async loadDownloadedPapers() {
        try {
            const resp = await fetch('/api/research/papers');
            const data = await resp.json();
            this.downloadedPapers = data.papers || [];
            this.renderDownloadedPapers();
        } catch (e) {
            console.error('Failed to load downloaded papers:', e);
        }
    },

    renderDownloadedPapers() {
        const container = document.getElementById('p-downloadedList');

        if (this.downloadedPapers.length === 0) {
            container.innerHTML = `<div class="empty-state" style="font-size:0.8em; color:var(--text-muted);">${getT('no_downloaded_papers')}</div>`;
            return;
        }

        container.innerHTML = this.downloadedPapers.map((p, i) => `
            <div class="downloaded-paper-item">
                <div class="downloaded-paper-title" title="${this.escapeHtml(p.metadata?.title || '')}">${this.escapeHtml((p.metadata?.title || getT('untitled')).substring(0, 50))}</div>
                <div class="downloaded-paper-meta">${p.metadata?.year || getT('na')} - ${p.citation_filename || ''}</div>
                <div class="downloaded-paper-actions">
                    ${p.markdown_path ? `<button onclick="PaperSearch.viewMarkdown(${i})">${getT('view_markdown')}</button>` : ''}
                    <button onclick="PaperSearch.deletePaper(${i})">${getT('delete')}</button>
                </div>
            </div>
        `).join('');
    },

    async deletePaper(index) {
        const paper = this.downloadedPapers[index];
        if (!paper) return;

        const paperId = paper.paper_id || (paper.metadata?.doi) || (paper.metadata?.arxiv_id);
        if (!paperId) return;

        if (!confirm(getT('delete_paper_confirm'))) return;

        try {
            await fetch(`/api/research/papers/${encodeURIComponent(paperId)}`, { method: 'DELETE' });
            this.loadDownloadedPapers();
            showToast(getT('paper_deleted'));
        } catch (e) {
            showToast(`${getT('save_failed')}: ${e.message}`);
        }
    },

    viewMarkdown(index) {
        const paper = this.downloadedPapers[index];
        if (!paper || !paper.markdown_path) return;

        window.open(`/api/research/papers/${encodeURIComponent(paper.paper_id)}/markdown`, '_blank');
    },

    // ==================== Settings ====================

    toggleSettings() {
        const panel = document.getElementById('p-settingsPanel');
        panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
    },

    async loadSettings() {
        try {
            const resp = await fetch('/api/research/config');
            const config = await resp.json();

            document.getElementById('p-unpaywallEmail').value = config.unpaywall_email || '';
            document.getElementById('p-crossrefEmail').value = config.crossref_email || '';
            document.getElementById('p-convertEngine').value = config.pdf_convert_engine || 'auto';
            document.getElementById('p-autoRename').checked = config.research_pipeline_rename !== false;
            document.getElementById('p-autoConvert').checked = config.research_pipeline_convert !== false;
        } catch (e) {
            console.error('Failed to load settings:', e);
        }
    },

    async saveSettings() {
        const settings = {
            unpaywall_email: document.getElementById('p-unpaywallEmail').value,
            crossref_email: document.getElementById('p-crossrefEmail').value,
            pdf_convert_engine: document.getElementById('p-convertEngine').value,
            research_pipeline_rename: document.getElementById('p-autoRename').checked,
            research_pipeline_convert: document.getElementById('p-autoConvert').checked,
        };

        try {
            await fetch('/api/research/config', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings),
            });
            showToast(getT('settings_saved'));
        } catch (e) {
            showToast(`${getT('save_failed')}: ${e.message}`);
        }
    },

    // ==================== Utilities ====================

    formatAuthors(authors) {
        if (!authors || authors.length === 0) return getT('unknown');
        if (authors.length === 1) return authors[0];
        if (authors.length === 2) return authors.join(' & ');
        return `${authors[0]} et al.`;
    },

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    PaperSearch.init();
});
