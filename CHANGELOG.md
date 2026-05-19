# Changelog

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