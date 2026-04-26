// ============================================
// Wiki Module - Knowledge Base Wiki Browser
// ============================================

var WikiModule = {
    currentKb: '',
    currentPage: '',
    pages: [],

    init: function() {
        this.loadKbList();
    },

    async loadKbList() {
        try {
            const res = await fetch('/api/wiki/list');
            const data = await res.json();
            const select = document.getElementById('wikiKbSelect');
            if (!select) return;

            select.innerHTML = '<option value="">选择知识库</option>';
            for (const kb of data.kbs) {
                const wikiBadge = kb.has_wiki ? ` (${kb.page_count}页)` : '';
                select.innerHTML += `<option value="${kb.name}">${kb.display_name}${wikiBadge}</option>`;
            }
        } catch (e) {
            console.error('Failed to load wiki KB list:', e);
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
            } else {
                listEl.innerHTML = `<div class="wiki-build-status error">✗ 生成失败: ${data.error}</div>`;
            }
        } catch (e) {
            listEl.innerHTML = `<div class="wiki-build-status error">✗ 生成失败: ${e.message}</div>`;
        }

        btn.disabled = false;
        btn.textContent = '🔨 生成 Wiki';
    }
};

// Initialize wiki module when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    WikiModule.init();
});
