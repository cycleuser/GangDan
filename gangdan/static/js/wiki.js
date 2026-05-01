// ============================================
// Wiki Module - Knowledge Base Wiki Browser
// ============================================

var WikiModule = {
    currentKb: '',
    currentPage: '',
    pages: [],
    allKbs: [],
    crossKbNames: [],

    init: function() {
        this.loadKbList();
    },

    async loadKbList() {
        try {
            const res = await fetch('/api/wiki/list');
            const data = await res.json();
            const select = document.getElementById('wikiKbSelect');
            if (!select) return;

            this.allKbs = data.kbs;
            select.innerHTML = '<option value="">' + getT('wiki_select_kb') + '</option>';
            
            // Build cross-KB checkbox list
            const crossList = document.getElementById('wikiCrossKbList');
            if (crossList) {
                crossList.innerHTML = data.kbs.map(kb => 
                    `<label style="display:block;padding:3px 0;cursor:pointer;">
                        <input type="checkbox" class="wiki-cross-kb" value="${kb.name}" onchange="WikiModule.updateCrossSelection()"> 
                        ${kb.display_name}
                    </label>`
                ).join('');
            }
            
            for (const kb of data.kbs) {
                const wikiBadge = kb.has_wiki ? ` (${kb.page_count}${getT('wiki_page_suffix')})` : '';
                select.innerHTML += `<option value="${kb.name}">${kb.display_name}${wikiBadge}</option>`;
            }
        } catch (e) {
            console.error('Failed to load wiki KB list:', e);
        }
    },

    updateCrossSelection() {
        const checkboxes = document.querySelectorAll('.wiki-cross-kb:checked');
        this.crossKbNames = Array.from(checkboxes).map(cb => cb.value);
        const btn = document.getElementById('wikiCrossBuildBtn');
        if (btn) {
            btn.disabled = this.crossKbNames.length < 2;
            btn.textContent = this.crossKbNames.length >= 2 
                ? `🌐 ${getT('wiki_generate_cross')} (${this.crossKbNames.length}${getT('wiki_cross_kb_unit')})` 
                : `🌐 ${getT('wiki_generate_cross')}`;
        }
    },

    async loadPages() {
        const select = document.getElementById('wikiKbSelect');
        const kbName = select?.value || '';
        if (!kbName) {
            document.getElementById('wikiPageList').innerHTML = '<div class="wiki-empty">' + getT('wiki_select_kb') + '</div>';
            return;
        }

        this.currentKb = kbName;
        const listEl = document.getElementById('wikiPageList');
        listEl.innerHTML = '<div class="wiki-empty">' + getT('wiki_loading') + '</div>';

        try {
            const res = await fetch(`/api/wiki/pages?kb=${encodeURIComponent(kbName)}`);
            const data = await res.json();
            this.pages = data.pages || [];

            if (this.pages.length === 0) {
                listEl.innerHTML = '<div class="wiki-empty">' + getT('wiki_no_pages') + '</div>';
                return;
            }

            // Check wiki status for dirty pages
            let statusHtml = '';
            try {
                const statusRes = await fetch(`/api/wiki/status?kb=${encodeURIComponent(kbName)}`);
                const statusData = await statusRes.json();
                if (statusData.success && statusData.status.exists) {
                    const status = statusData.status;
                    if (status.dirty > 0) {
                        statusHtml = `<div class="wiki-status-bar warning">
                            ⚠️ ${status.dirty} ${getT('wiki_pages_need_update')}
                            <button class="wiki-small-btn" onclick="WikiModule.updateDirtyPages()">${getT('wiki_incremental_update')}</button>
                        </div>`;
                    } else {
                        statusHtml = `<div class="wiki-status-bar ok">✓ ${getT('wiki_up_to_date')}</div>`;
                    }
                }
            } catch (e) {
                console.warn('Failed to load wiki status:', e);
            }

            // Group by category
            const groups = {};
            for (const page of this.pages) {
                const cat = page.category || 'other';
                if (!groups[cat]) groups[cat] = [];
                groups[cat].push(page);
            }

            let html = statusHtml;
            const catNames = { 
                index: '📋 ' + getT('wiki_cat_index'), 
                concept: '📝 ' + getT('wiki_cat_concept'), 
                entity: '👤 ' + getT('wiki_cat_entity'), 
                other: '📄 ' + getT('wiki_cat_other') 
            };
            for (const [cat, pages] of Object.entries(groups)) {
                html += `<div style="font-size:0.78em;color:var(--text-muted);margin:10px 0 5px;padding-left:5px;">${catNames[cat] || cat}</div>`;
                for (const page of pages) {
                    const activeClass = page.path === this.currentPage ? 'active' : '';
                    html += `<div class="wiki-page-item ${activeClass}" onclick="WikiModule.openPage('${page.path}')">
                        ${escapeHtml(page.title)}
                    </div>`;
                }
            }
            listEl.innerHTML = html;
        } catch (e) {
            listEl.innerHTML = `<div class="wiki-empty">${getT('wiki_load_failed')}${e.message}</div>`;
        }
    },

    async openPage(pagePath) {
        this.currentPage = pagePath;
        const contentEl = document.getElementById('wikiContent');
        contentEl.innerHTML = '<div class="wiki-empty">' + getT('wiki_loading') + '</div>';

        // Highlight active page
        document.querySelectorAll('.wiki-page-item').forEach(el => el.classList.remove('active'));
        event?.target?.closest?.('.wiki-page-item')?.classList.add('active');

        // Strip 'wiki/' prefix from path for API call
        const apiPath = pagePath.replace(/^wiki\//, '');

        try {
            const res = await fetch(`/api/wiki/page?kb=${encodeURIComponent(this.currentKb)}&path=${encodeURIComponent(apiPath)}`);
            const data = await res.json();

            if (!data.content) {
                contentEl.innerHTML = '<div class="wiki-empty">' + getT('wiki_page_not_found') + '</div>';
                return;
            }

            // Render markdown
            contentEl.innerHTML = renderMarkdown(data.content);
            renderLatex(contentEl);

            // Make internal wiki links clickable
            contentEl.querySelectorAll('a[href^="concepts/"], a[href^="entities/"]').forEach(link => {
                link.addEventListener('click', (e) => {
                    e.preventDefault();
                    const href = link.getAttribute('href');
                    this.openPage('wiki/' + href);
                });
            });
        } catch (e) {
            contentEl.innerHTML = `<div class="wiki-empty">${getT('wiki_load_failed')}${e.message}</div>`;
        }
    },

    async openCrossPage(pagePath) {
        this.currentPage = pagePath;
        const contentEl = document.getElementById('wikiContent');
        contentEl.innerHTML = '<div class="wiki-empty">' + getT('wiki_loading') + '</div>';

        const kbsParam = this.crossKbNames.join(',');

        try {
            const res = await fetch(`/api/wiki/cross-page?kbs=${encodeURIComponent(kbsParam)}&path=${encodeURIComponent(pagePath)}`);
            const data = await res.json();

            if (!data.content) {
                contentEl.innerHTML = '<div class="wiki-empty">' + getT('wiki_page_not_found') + '</div>';
                return;
            }

            contentEl.innerHTML = renderMarkdown(data.content);
            renderLatex(contentEl);

            // Make internal wiki links clickable
            contentEl.querySelectorAll('a[href^="concepts/"]').forEach(link => {
                link.addEventListener('click', (e) => {
                    e.preventDefault();
                    const href = link.getAttribute('href');
                    this.openCrossPage(href);
                });
            });
        } catch (e) {
            contentEl.innerHTML = `<div class="wiki-empty">${getT('wiki_load_failed')}${e.message}</div>`;
        }
    },

    async loadCrossPages() {
        if (this.crossKbNames.length < 2) return;

        const listEl = document.getElementById('wikiPageList');
        listEl.innerHTML = '<div class="wiki-empty">' + getT('wiki_loading') + '</div>';

        try {
            const kbsParam = this.crossKbNames.join(',');
            const res = await fetch(`/api/wiki/cross-pages?kbs=${encodeURIComponent(kbsParam)}`);
            const data = await res.json();
            this.pages = data.pages || [];

            if (this.pages.length === 0) {
                listEl.innerHTML = '<div class="wiki-empty">' + getT('wiki_no_cross_pages') + '</div>';
                return;
            }

            const groups = {};
            for (const page of this.pages) {
                const cat = page.category || 'other';
                if (!groups[cat]) groups[cat] = [];
                groups[cat].push(page);
            }

            let html = `<div style="font-size:0.78em;color:var(--accent);margin-bottom:10px;padding:5px;background:var(--accent-soft);border-radius:4px;">🌐 ${getT('wiki_cross_header')} (${this.crossKbNames.length} ${getT('wiki_cross_kb_unit')})</div>`;
            const catNames = { 
                index: '📋 ' + getT('wiki_cat_index'), 
                concept: '📝 ' + getT('wiki_cat_concept'), 
                other: '📄 ' + getT('wiki_cat_other') 
            };
            for (const [cat, pages] of Object.entries(groups)) {
                html += `<div style="font-size:0.78em;color:var(--text-muted);margin:10px 0 5px;padding-left:5px;">${catNames[cat] || cat}</div>`;
                for (const page of pages) {
                    const activeClass = page.path === this.currentPage ? 'active' : '';
                    html += `<div class="wiki-page-item ${activeClass}" onclick="WikiModule.openCrossPage('${page.path}')">
                        ${escapeHtml(page.title)}
                    </div>`;
                }
            }
            listEl.innerHTML = html;
        } catch (e) {
            listEl.innerHTML = `<div class="wiki-empty">${getT('wiki_load_failed')}${e.message}</div>`;
        }
    },

    async buildWiki() {
        const select = document.getElementById('wikiKbSelect');
        const kbName = select?.value || '';
        if (!kbName) {
            showToast(getT('wiki_please_select_kb'), 'warning');
            return;
        }

        const useLlCheckbox = document.getElementById('wikiLlMode');
        const useLl = useLlCheckbox?.checked || false;
        const btn = document.getElementById('wikiBuildBtn');
        const listEl = document.getElementById('wikiPageList');
        btn.disabled = true;
        btn.textContent = '⏳ ' + getT('wiki_generating');
        listEl.innerHTML = `<div class="wiki-empty">🔨 ${getT('wiki_building_status')}${useLl ? ' ' + getT('wiki_llm_enhanced') : ''}${getT('wiki_may_take_minutes')}</div>`;

        try {
            const res = await fetch('/api/wiki/build', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ kb_name: kbName, force: true, use_llm: useLl })
            });
            const data = await res.json();

            if (data.success) {
                const stats = data.stats;
                const updateInfo = stats.updated !== undefined
                    ? `${getT('wiki_updated_count')}${stats.updated}${getT('wiki_skipped_count')}${stats.skipped}${getT('wiki_page_suffix')}`
                    : '';
                listEl.innerHTML = `<div class="wiki-build-status success">✓ ${getT('wiki_generation_complete')}${stats.pages}${getT('wiki_pages_count')}，${stats.keywords}${getT('wiki_keywords_count')}，${stats.links}${getT('wiki_links_count')}${updateInfo}</div>`;
                this.loadPages();
                this.loadKbList();
            } else {
                listEl.innerHTML = `<div class="wiki-build-status error">✗ ${getT('wiki_generation_failed')}${data.error}</div>`;
            }
        } catch (e) {
            listEl.innerHTML = `<div class="wiki-build-status error">✗ ${getT('wiki_generation_failed')}${e.message}</div>`;
        }

        btn.disabled = false;
        btn.textContent = '🔨 ' + getT('wiki_generate');
    },

    async buildCrossWiki() {
        if (this.crossKbNames.length < 2) {
            showToast(getT('wiki_select_at_least_2'), 'warning');
            return;
        }

        const btn = document.getElementById('wikiCrossBuildBtn');
        const listEl = document.getElementById('wikiPageList');
        btn.disabled = true;
        btn.textContent = '⏳ ' + getT('wiki_generating');
        listEl.innerHTML = '<div class="wiki-empty">🌐 ' + getT('wiki_building_cross') + '</div>';

        try {
            const res = await fetch('/api/wiki/build-cross', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ kb_names: this.crossKbNames, force: true })
            });
            const data = await res.json();

            if (data.success) {
                listEl.innerHTML = `<div class="wiki-build-status success">✓ ${getT('wiki_cross_complete')}<br>${data.stats.pages}${getT('wiki_pages_count')}，${data.stats.keywords}${getT('wiki_keywords_count')}<br>${data.stats.links}${getT('wiki_links_count')}，${data.stats.kbs}${getT('wiki_kbs_count')}</div>`;
                this.loadCrossPages();
            } else {
                listEl.innerHTML = `<div class="wiki-build-status error">✗ ${getT('wiki_generation_failed')}${data.error}</div>`;
            }
        } catch (e) {
            listEl.innerHTML = `<div class="wiki-build-status error">✗ ${getT('wiki_generation_failed')}${e.message}</div>`;
        }

        btn.disabled = false;
        btn.textContent = `🌐 ${getT('wiki_generate_cross')} (${this.crossKbNames.length}${getT('wiki_cross_kb_unit')})`;
    },

    async updateDirtyPages() {
        if (!this.currentKb) return;

        const listEl = document.getElementById('wikiPageList');
        const useLlCheckbox = document.getElementById('wikiLlMode');
        const useLl = useLlCheckbox?.checked || false;

        listEl.innerHTML = '<div class="wiki-empty">🔄 ' + getT('wiki_updating_affected') + '</div>';

        try {
            const res = await fetch('/api/wiki/update-dirty', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ kb_name: this.currentKb, use_llm: useLl })
            });
            const data = await res.json();

            if (data.success) {
                const result = data.result;
                if (result.message) {
                    listEl.innerHTML = `<div class="wiki-build-status success">✓ ${result.message}</div>`;
                } else {
                    listEl.innerHTML = `<div class="wiki-build-status success">✓ ${getT('wiki_incremental_complete')} ${result.updated} ${getT('wiki_skipped_count')}${result.skipped}${getT('wiki_page_suffix')}</div>`;
                }
                this.loadPages();
            } else {
                listEl.innerHTML = `<div class="wiki-build-status error">✗ ${getT('wiki_update_failed')}${data.error}</div>`;
            }
        } catch (e) {
            listEl.innerHTML = `<div class="wiki-build-status error">✗ ${getT('wiki_update_failed')}${e.message}</div>`;
        }
    },

    async regenerateSelectedPages(pageSlugs) {
        if (!this.currentKb || pageSlugs.length === 0) return;

        const listEl = document.getElementById('wikiPageList');
        const useLlCheckbox = document.getElementById('wikiLlMode');
        const useLl = useLlCheckbox?.checked || false;

        listEl.innerHTML = `<div class="wiki-empty">🔄 ${getT('wiki_regenerating')} ${pageSlugs.length}${getT('wiki_pages_count')}...</div>`;

        try {
            const res = await fetch('/api/wiki/regenerate-pages', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ kb_name: this.currentKb, page_slugs: pageSlugs, use_llm: useLl })
            });
            const data = await res.json();

            if (data.success) {
                const result = data.result;
                let msg = `✓ ${getT('wiki_regeneration_complete')} ${result.updated} ${getT('wiki_pages_count')}`;
                if (result.not_found && result.not_found.length > 0) {
                    msg += `${getT('wiki_not_found_count')}${result.not_found.length}${getT('wiki_pages_count')}`;
                }
                listEl.innerHTML = `<div class="wiki-build-status success">${msg}</div>`;
                this.loadPages();
            } else {
                listEl.innerHTML = `<div class="wiki-build-status error">✗ ${getT('wiki_regeneration_failed')}${data.error}</div>`;
            }
        } catch (e) {
            listEl.innerHTML = `<div class="wiki-build-status error">✗ ${getT('wiki_regeneration_failed')}${e.message}</div>`;
        }
    }
};

// Initialize wiki module when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    WikiModule.init();
});
