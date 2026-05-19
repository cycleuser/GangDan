# Changelog

## [2026-05-19] CAJ 上传支持 + PDF 上传改进 + 语言选择器扩展

### CAJ 文件上传与转换

- 新增 CAJ（知网专有格式）文件上传支持：上传 `.caj` 文件后自动转换为 Markdown
- 实现 `CAJConverter` 类（`pdf_converter.py`）：CAJ → PDF（caj2pdf）→ Markdown（docling/pymupdf 优先链）
- CAJ 转换中间态 PDF 自动保存到 KB 目录（与 .caj 原件和 .md 并列），导出时一并打包
- 依赖 `caj2pdf-restructured`（pip 安装），未安装时优雅降级跳过
- 支持 CAJ、KDH、HN 三种格式（caj2pdf 库能力范围），CAJ-wrapped-PDF 最可靠

### PDF 上传改进

- 上传 PDF 后自动用 `PDFConverter` 转换为同名 `.md`（如 `paper.pdf` → `paper.md`）
- PDF 原件保留在 KB 目录，导出时一并打包
- 支持 `upload_docs()`、`import_directory()`、`check_duplicates()` 三个端点的 PDF 处理
- `import_directory()` 的 SSE 流推送包含 PDF 转换进度（50%-70% 区间）

### 语言选择器扩展

- KB 语言选择从硬编码 3 个（中/英/日）扩展为 10 个（中/英/日/韩/法/德/西/葡/俄/意），与系统 `LANGUAGES` 字典同步
- 新增「🔍 Auto」选项（默认勾选），选择 Auto 时自动从文档内容检测语言
- Auto 与具体语言互斥：选 Auto 清除其他选择，选具体语言取消 Auto
- 前端 JS 过滤 `auto` 值，不传语言参数 → 后端自动检测
- `detect_language()` 基于 Unicode 字符范围检测：CJK → zh, 平假名/片假名 → ja, 韩文 → ko, 西里尔 → ru 等

### ChromaDB 文档去重修复

- `_get_chroma_docs()` 中 metadata 无 `doc_id` 时 fallback 到 `file` 字段作为去重 key
- 上传类 KB 的 chunk metadata 只有 `file` 没有 `doc_id`，修复后 41 个 chunk 正确合并为 1 个文档

### 导出改进

- `SOURCE_EXTENSIONS` 新增 `.caj`，导出时 CAJ 原件一同打包
- CAJ 中间态 PDF（同名 `.pdf`）也被 SOURCE_EXTENSIONS 的 `.pdf` 通配捕获导出

### 涉及文件

| 文件 | 改动 |
|------|------|
| `gangdan/core/pdf_converter.py` | 新增 `CAJConverter` 类，CAJ→PDF→MD 管线，中间 PDF 保存 |
| `gangdan/app.py` | CAJ/PDF 上传支持、语言自动检测、SOURCE_EXTENSIONS 增加 .caj |
| `gangdan/templates/index.html` | 语言选择器 10 语言 + Auto 选项，accept 增加 .caj |
| `gangdan/kb_routes.py` | ChromaDB 文档去重 fallback |
| `gangdan/static/js/docs.js` | 语言收集过滤 auto 值（3 处） |
| `gangdan-go/web/templates/index.html` | 同步：语言选择器、accept 属性、Auto 互斥 JS |
| `gangdan-go/web/static/js/docs.js` | 同步：语言收集过滤 auto 值（3 处） |

---

## [2026-05-19] 知识库全文下载与导出修复

### 重大改进：arXiv 论文从"只存摘要"到"全文+源文件"

此前，将 arXiv 论文添加到知识库时仅保存 500 字符的摘要，导出的知识库也是残缺的。本次修复实现了完整的论文下载→全文转换→知识库写入→导出全链路。

#### 全文 Markdown 写入（不再截断摘要）

- `_add_preprints_to_kb_direct()` 在前端只传摘要时，自动从 `preprint_exports` 目录查找已下载的全文 MD 文件覆盖写入
- `content_preview` 字段不再截断到 500 字符，保留全文用于 ChromaDB 索引
- 修复了知识库 MD 文件全是摘要、ChromaDB 索引也只得摘要碎片的问题

#### 源文件持久化与统一命名

- 所有源格式（HTML/PDF/TeX）均复制到知识库目录，不再依赖临时目录
- 文件命名统一为 `{作者} ({年}) - {标题} [{arXiv ID}].md` 和对应的 `_source.html`/`_source.pdf`/`_source.tar.gz`
- 命名中包含 arXiv ID（方括号内），确保同篇文章的所有文件排序时相邻，便于识别和检索

#### 导出 ZIP 修复

- 导出知识库时，`_source.*` 文件随 MD 一起打包，不再遗漏
- 移除了 `sources/` 子目录中重复导出 KB 目录内已有文件的问题
- 移除了从 `papers_dir` 和 `preprint_exports` 额外搜索并重复打包的逻辑

#### 下载与转换流程改进

- arXiv HTML 全文页使用 `arxiv.org/html/{id}`（官方源，中国网络更稳定），`ar5iv` 作为 fallback
- 两阶段下载：先下载所有格式源文件（best-effort），再按 HTML→TeX→PDF 优先链转换 Markdown
- `PreprintConverter.download_source()` 新方法只下载保存源文件不转换
- `_detect_source_formats()` 网络超时时乐观对待（`has_html=True`），404 时才判否
- docling 模型缓存检查 `_is_docling_model_cached()`，无缓存时跳过避免下载超时
- SemanticScholar API 429 重试 bug 修复

#### KBDocEntry 扩展

- 新增 `source_format` 字段：记录转换成功时使用的源格式（html/tex/pdf）
- 新增 `source_formats_saved` 字段：记录所有已保存的源格式列表
- `documents.json` 中完整记录源格式信息，便于导出时识别

### 涉及文件

| 文件 | 改动 |
|------|------|
| `gangdan/preprint_routes.py` | 全文 MD 查找、源文件复制、统一命名、content_preview 不截断 |
| `gangdan/core/kb_manager.py` | KBDocEntry 新增 source_format / source_formats_saved 字段 |
| `gangdan/app.py` | 导出 ZIP 精简、_source.* 文件打包、HF 镜像配置 |
| `gangdan/core/preprint_converter.py` | download_source() 新方法、_safe_filename() |
| `gangdan/core/preprint_fetcher.py` | HTML_BASE 改为 arxiv.org/html、ar5iv fallback、乐观超时 |
| `gangdan/core/research_searcher.py` | 429 重试 bug 修复 |