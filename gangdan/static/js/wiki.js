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
            select.innerHTML = '<option value="">选择知识库</option>';
            
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
                const wikiBadge = kb.has_wiki ? ` (${kb.page_count}页)` : '';
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
                ? `🌐 生成跨库 Wiki (${this.crossKbNames.length}库)` 
                : '🌐 生成跨库 Wiki';
        }
    },

    async loadPages() {
        const select = document.getElementById('wikiKbSelect');
        const kbName = select?.value || '';
        if (!kbName) {
            document.getElementById('wikiPageList').innerHTML = '<div class="wiki-empty">选择知识库</div>';
            return;
        }

        this.currentKb = kbName;
        const listEl = document.getElementById('wikiPageList');
        listEl.innerHTML = '<div class="wiki-empty">加载中...</div>';

        try {
            const res = await fetch(`/api/wiki/pages?kb=${encodeURIComponent(kbName)}`);
            const data = await res.json();
            this.pages = data.pages || [];

            if (this.pages.length === 0) {
                listEl.innerHTML = '<div class="wiki-empty">暂无 Wiki 页面，点击"生成 Wiki"创建</div>';
                return;
            }

            // Group by category
            const groups = {};
            for (const page of this.pages) {
                const cat = page.category || 'other';
                if (!groups[cat]) groups[cat] = [];
                groups[cat].push(page);
            }

            let html = '';
            const catNames = { index: '📋 索引', concept: '📝 概念', entity: '👤 实体', other: '📄 其他' };
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
            listEl.innerHTML = `<div class="wiki-empty">加载失败: ${e.message}</div>`;
        }
    },

    async openPage(pagePath) {
        this.currentPage = pagePath;
        const contentEl = document.getElementById('wikiContent');
        contentEl.innerHTML = '<div class="wiki-empty">加载中...</div>';

        // Highlight active page
        document.querySelectorAll('.wiki-page-item').forEach(el => el.classList.remove('active'));
        event?.target?.closest?.('.wiki-page-item')?.classList.add('active');

        // Strip 'wiki/' prefix from path for API call
        const apiPath = pagePath.replace(/^wiki\//, '');

        try {
            const res = await fetch(`/api/wiki/page?kb=${encodeURIComponent(this.currentKb)}&path=${encodeURIComponent(apiPath)}`);
            const data = await res.json();

            if (!data.content) {
                contentEl.innerHTML = '<div class="wiki-empty">页面不存在</div>';
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
            contentEl.innerHTML = `<div class="wiki-empty">加载失败: ${e.message}</div>`;
        }
    },

    async openCrossPage(pagePath) {
        this.currentPage = pagePath;
        const contentEl = document.getElementById('wikiContent');
        contentEl.innerHTML = '<div class="wiki-empty">加载中...</div>';

        const kbsParam = this.crossKbNames.join(',');

        try {
            const res = await fetch(`/api/wiki/cross-page?kbs=${encodeURIComponent(kbsParam)}&path=${encodeURIComponent(pagePath)}`);
            const data = await res.json();

            if (!data.content) {
                contentEl.innerHTML = '<div class="wiki-empty">页面不存在</div>';
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
            contentEl.innerHTML = `<div class="wiki-empty">加载失败: ${e.message}</div>`;
        }
    },

    async loadCrossPages() {
        if (this.crossKbNames.length < 2) return;

        const listEl = document.getElementById('wikiPageList');
        listEl.innerHTML = '<div class="wiki-empty">加载中...</div>';

        try {
            const kbsParam = this.crossKbNames.join(',');
            const res = await fetch(`/api/wiki/cross-pages?kbs=${encodeURIComponent(kbsParam)}`);
            const data = await res.json();
            this.pages = data.pages || [];

            if (this.pages.length === 0) {
                listEl.innerHTML = '<div class="wiki-empty">暂无跨库 Wiki 页面，点击"生成跨库 Wiki"创建</div>';
                return;
            }

            const groups = {};
            for (const page of this.pages) {
                const cat = page.category || 'other';
                if (!groups[cat]) groups[cat] = [];
                groups[cat].push(page);
            }

            let html = `<div style="font-size:0.78em;color:var(--accent);margin-bottom:10px;padding:5px;background:var(--accent-soft);border-radius:4px;">🌐 跨库 Wiki (${this.crossKbNames.length} 库)</div>`;
            const catNames = { index: '📋 索引', concept: '📝 概念', other: '📄 其他' };
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
            listEl.innerHTML = `<div class="wiki-empty">加载失败: ${e.message}</div>`;
        }
    },

    async buildWiki() {
        const select = document.getElementById('wikiKbSelect');
        const kbName = select?.value || '';
        if (!kbName) {
            showToast('请先选择知识库', 'warning');
            return;
        }

        const btn = document.getElementById('wikiBuildBtn');
        const listEl = document.getElementById('wikiPageList');
        btn.disabled = true;
        btn.textContent = '⏳ 生成中...';
        listEl.innerHTML = '<div class="wiki-empty">🔨 正在生成 Wiki，这可能需要几分钟...</div>';

        try {
            const res = await fetch('/api/wiki/build', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ kb_name: kbName, force: true })
            });
            const data = await res.json();

            if (data.success) {
                listEl.innerHTML = `<div class="wiki-build-status success">✓ 生成完成！${data.stats.pages} 个页面，${data.stats.keywords} 个关键词，${data.stats.links} 个内部链接</div>`;
                this.loadPages();
                this.loadKbList(); // Refresh to show page count
            } else {
                listEl.innerHTML = `<div class="wiki-build-status error">✗ 生成失败: ${data.error}</div>`;
            }
        } catch (e) {
            listEl.innerHTML = `<div class="wiki-build-status error">✗ 生成失败: ${e.message}</div>`;
        }

        btn.disabled = false;
        btn.textContent = '🔨 生成 Wiki';
    },

    async buildCrossWiki() {
        if (this.crossKbNames.length < 2) {
            showToast('请至少选择 2 个知识库', 'warning');
            return;
        }

        const btn = document.getElementById('wikiCrossBuildBtn');
        const listEl = document.getElementById('wikiPageList');
        btn.disabled = true;
        btn.textContent = '⏳ 生成中...';
        listEl.innerHTML = '<div class="wiki-empty">🌐 正在生成跨库 Wiki...</div>';

        try {
            const res = await fetch('/api/wiki/build-cross', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ kb_names: this.crossKbNames, force: true })
            });
            const data = await res.json();

            if (data.success) {
                listEl.innerHTML = `<div class="wiki-build-status success">✓ 跨库 Wiki 生成完成！<br>${data.stats.pages} 个页面，${data.stats.keywords} 个关键词<br>${data.stats.links} 个内部链接，${data.stats.kbs} 个知识库</div>`;
                this.loadCrossPages();
            } else {
                listEl.innerHTML = `<div class="wiki-build-status error">✗ 生成失败: ${data.error}</div>`;
            }
        } catch (e) {
            listEl.innerHTML = `<div class="wiki-build-status error">✗ 生成失败: ${e.message}</div>`;
        }

        btn.disabled = false;
        btn.textContent = `🌐 生成跨库 Wiki (${this.crossKbNames.length}库)`;
    }
};

// Initialize wiki module when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    WikiModule.init();
});
