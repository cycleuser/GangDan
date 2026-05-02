# GangDan (纲担)

基于大语言模型的知识管理与教学辅助工具，支持离线使用。

> **纲担** — 有纲领有担当。

## 功能特性

### 知识管理
- **统一文献检索** — 一站式搜索 arXiv、bioRxiv、medRxiv、Semantic Scholar、CrossRef、OpenAlex、DBLP、PubMed、GitHub。AI 智能查询精炼，自动翻译和同义词扩展。
- **批量操作** — 多选、全选、批量转换（PDF/HTML/TeX → Markdown，保留图片和公式）、批量加入知识库。支持按相关性、日期、标题排序。
- **智能重命名** — 下载论文自动按引用格式命名：`作者姓 et al. (年份) - 标题.pdf`
- **LLM 生成 Wiki** — 从知识库内容自动构建结构化 Wiki 页面，支持跨知识库概念关联。
- **图集浏览** — 浏览和搜索知识库中的图片，支持上下文和来源标注。
- **文档管理** — 一键下载和索引 30+ 常用库文档（Python、Rust、Go、JS、CUDA、Docker 等）。上传自定义文档、批量操作、GitHub 仓库搜索、网页搜索添加到知识库。

### 教学辅助
- **出题器** — 从知识库内容生成选择题、简答题、填空题、判断题。
- **引导学习** — 自动提取知识点，生成互动课程和问答。
- **深度研究** — 多阶段研究管线：主题分解 → RAG 检索研究 → 综合报告。
- **课件制作** — 从知识库材料生成结构化课件。
- **试卷生成** — 从知识库内容生成完整试卷及答案解析。

### 核心功能
- **RAG 对话** — 流式聊天，支持知识库检索和网络搜索。严格 KB 模式确保回答有据可查。
- **AI 命令助手** — 自然语言描述 → 生成 Shell 命令，可拖拽到终端执行。
- **内置终端** — 浏览器内直接运行命令，显示 stdout/stderr。
- **文献综述与论文撰写** — 从知识库内容生成学术综述和论文。
- **对话保存/加载** — JSON 格式导出/导入，保持会话连续。
- **10 语言界面** — 中文、English、日本語、Français、Русский、Deutsch、Italiano、Español、Português、한국어。
- **暗色/亮色主题** — 完整主题支持，CSS 变量驱动。
- **离线优先** — 完全在本地运行，无需云 API。

### 命令行
- 流式聊天（`gangdan chat "问题"`）、交互式 REPL（`gangdan cli`）
- 知识库操作、文档管理、配置修改、对话持久化
- AI 命令生成、安全检查 Shell 执行

## 环境要求

- Python 3.10+
- [Ollama](https://ollama.ai/) 本地运行（默认 `http://localhost:11434`）
- 聊天模型（如 `ollama pull qwen2.5`）
- 嵌入模型（如 `ollama pull nomic-embed-text`）

## 安装

```bash
pip install gangdan
gangdan                    # Web 界面
gangdan cli                # 交互式 CLI
gangdan --port 8080        # 自定义端口
```

源码安装：

```bash
git clone https://github.com/cycleuser/GangDan.git
cd GangDan
pip install -e .
gangdan
```

浏览器打开 [http://127.0.0.1:5000](http://127.0.0.1:5000)。

## Ollama 设置

```bash
ollama serve
ollama pull qwen2.5
ollama pull nomic-embed-text
```

## 项目结构

```
GangDan/
├── pyproject.toml
├── README.md / README_CN.md
├── gangdan/
│   ├── __init__.py / __main__.py
│   ├── cli.py / cli_app.py          # CLI 入口 + REPL
│   ├── app.py                       # Flask 后端
│   ├── learning_routes.py           # 学习模块蓝图
│   ├── preprint_routes.py           # 预印本搜索 + 转换
│   ├── research_routes.py           # 论文搜索
│   ├── kb_routes.py                 # 自定义知识库管理
│   ├── export_routes.py             # 导出 API
│   ├── core/                        # 共享核心模块
│   │   ├── config.py                # 配置、国际化、翻译
│   │   ├── ollama_client.py         # Ollama API 客户端
│   │   ├── chroma_manager.py        # ChromaDB 管理
│   │   ├── vector_db.py             # 多后端向量数据库
│   │   ├── kb_manager.py            # 自定义知识库 CRUD
│   │   ├── conversation.py          # 对话历史
│   │   ├── doc_manager.py           # 文档下载/索引
│   │   ├── wiki_builder.py          # LLM Wiki 生成
│   │   ├── preprint_fetcher.py      # 预印本搜索
│   │   ├── preprint_converter.py    # HTML/TeX/PDF → MD
│   │   ├── pdf_converter.py         # PDF → MD (marker/mineru/docling)
│   │   ├── export_manager.py        # 批量转换/导出
│   │   ├── web_searcher.py          # 网络搜索
│   │   └── ...
│   ├── templates/index.html         # 主 SPA 模板
│   └── static/{css,js}/             # 前端资源
├── tests/                           # 测试套件
├── images/                          # 截图
└── removed/                         # 已废弃文件
```

## 架构

```
┌──────────────┐    ┌──────────────┐
│   Flask GUI  │    │  CLI / REPL  │
│   (app.py)   │    │ (cli_app.py) │
└──────┬───────┘    └──────┬───────┘
       │                   │
┌──────┴───────────────────┴──────┐
│          gangdan/core/          │
└─────────────────────────────────┘
       │                   │
┌──────┴───────┐    ┌──────┴───────┐
│    Ollama    │    │   ChromaDB   │
└──────────────┘    └──────────────┘
```

## 配置

所有设置通过**设置**标签页管理：Ollama URL、聊天/嵌入/重排序模型、代理、上下文长度、输出语言、向量数据库类型。

## 测试

```bash
pip install pytest pytest-cov
pytest tests/ -v
pytest tests/ --cov=gangdan
```

## 许可证

GPL-3.0-or-later。详见 [LICENSE](LICENSE)。
