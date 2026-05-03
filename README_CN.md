# GangDan (纲担)

基于大语言模型的知识管理与教学辅助工具，支持离线使用。

> **纲担** — 有纲领有担当。

![Chat Panel](images/chat.png)

## 概述

GangDan 是一个**本地优先、离线运行的编程助手**，由 [Ollama](https://ollama.ai/) 和 [ChromaDB](https://www.trychroma.com/) 驱动。它将基于 RAG 的知识管理与教学辅助工具相结合，全部在本地运行——无需任何云端 API。

![系统架构](diagrams/architecture.svg)

## 功能特性

### 知识管理

- **统一文献检索** — 一站式搜索 arXiv、bioRxiv、medRxiv、Semantic Scholar、CrossRef、OpenAlex、DBLP、PubMed、GitHub。AI 智能查询精炼，自动翻译和同义词扩展。
- **批量操作** — 多选、全选、批量转换（PDF/HTML/TeX → Markdown，保留图片和公式）、批量加入知识库。支持按相关性、日期、标题排序。
- **智能重命名** — 下载论文自动按引用格式命名：`作者姓 et al. (年份) - 标题.pdf`
- **LLM 生成 Wiki** — 从知识库内容自动构建结构化 Wiki 页面，支持跨知识库概念关联。像维基百科一样浏览你的文档。
- **图集浏览** — 浏览和搜索知识库中的图片，支持上下文和来源标注。
- **文档管理** — 一键下载和索引 30+ 常用库文档（Python、Rust、Go、JS、CUDA、Docker 等）。上传自定义文档、批量操作、GitHub 仓库搜索、网页搜索添加到知识库。
- **自定义知识库上传** — 上传你自己的 Markdown (.md) 和纯文本 (.txt) 文档，创建命名知识库并自动索引。

### 教学辅助

- **出题器** — 从知识库内容生成选择题、简答题、填空题、判断题。
- **引导学习** — 自动提取知识点，生成互动课程和问答。
- **深度研究** — 多阶段研究管线：主题分解 → RAG 检索研究 → 综合报告。
- **课件制作** — 从知识库材料生成结构化课件。
- **试卷生成** — 从知识库内容生成完整试卷及答案解析。
- **文献综述与论文撰写** — 从知识库内容生成学术综述和论文。

### 核心功能

- **RAG 对话** — 流式聊天，支持知识库检索和网络搜索。严格 KB 模式确保回答有据可查。
- **跨语言搜索** — 自动检测查询和文档语言，支持跨语言 RAG 检索（例如用中文查询英文文档）。
- **引用参考** — 每个回答自动附带来源文档引用列表，方便验证和追溯。
- **AI 命令助手** — 自然语言描述 → 生成 Shell 命令，可拖拽到终端执行。
- **内置终端** — 浏览器内直接运行命令，显示 stdout/stderr。
- **对话保存/加载** — JSON 格式导出/导入，保持会话连续。
- **10 语言界面** — 中文、English、日本語、Français、Русский、Deutsch、Italiano、Español、Português、한국어。
- **暗色/亮色主题** — 完整主题支持，CSS 变量驱动。
- **离线优先** — 完全在本地运行，无需云 API。

![功能地图](diagrams/feature_map.svg)

### 多提供商 LLM 支持

GangDan 支持**分离模式**：本地 Ollama 用于聊天/嵌入/重排序，可选外部 LLM 提供商用于深度研究和论文撰写。

![提供商系统](diagrams/provider_system.svg)

| 提供商 | API 类型 | 用途 |
|--------|---------|------|
| **Ollama**（本地） | ollama | 聊天、嵌入、重排序 |
| **DashScope** | OpenAI 兼容 | 深度研究、论文撰写 |
| **MiniMax** | OpenAI 兼容 | 深度研究 |
| **百炼 Coding** | Anthropic 兼容 | 深度研究 |
| **OpenAI / DeepSeek / 月之暗面** | OpenAI 兼容 | 深度研究 |
| **自定义** | OpenAI 兼容 | 任意兼容 API |

### 命令行

- 流式聊天（`gangdan chat "问题"`）、交互式 REPL（`gangdan cli`）
- 知识库操作、文档管理、配置修改、对话持久化
- AI 命令生成、安全检查 Shell 执行
- 丰富的终端输出，支持格式化表格和语法高亮

## 界面截图

| 对话界面 | 内置终端 |
|:--------:|:--------:|
| ![对话](images/chat.png) | ![终端](images/terminal.png) |

| 文档管理 | 设置面板 |
|:--------:|:--------:|
| ![文档](images/documents.png) | ![设置](images/setting.png) |

| 上传文档 | 知识库范围选择 |
|:--------:|:--------------:|
| ![上传](images/upload.png) | ![知识库](images/knowledge.png) |

| 严格知识库模式（带引用） |
|:------------------------:|
| ![严格模式](images/specificated_knowledge_chat.png) |

上图展示了严格知识库模式的实际效果：选择特定知识库后，系统仅从该知识库检索内容，并在每个回答末尾自动附加引用列表，标注来源文档。

| 加载对话 | 对话已加载 |
|:--------:|:----------:|
| ![加载](images/load_history.png) | ![已加载](images/history_loaded.png) |

将聊天保存为 JSON 文件，随时加载以继续对话。

## RAG 管线

![RAG 管线](diagrams/rag_pipeline.svg)

从文档摄取到检索的完整管线：

1. **文档摄取** — 从 GitHub 仓库下载或上传自定义文件（.rst、.py、.html、.cpp、.md）
2. **格式转换** — 自动转换为统一的 Markdown 格式
3. **滑动窗口分块** — 固定大小分段，可配置重叠（默认：800 字符，150 重叠）
4. **向量嵌入** — 通过 Ollama API 使用 nomic-embed-text 模型（768 维向量，500 字符截断）
5. **向量存储** — ChromaDB 配合 HNSW 索引和余弦相似度
6. **查询检索** — Top-K 搜索配合距离过滤（阈值 1.5）、去重和上下文构建

### 分块策略

![分块策略](diagrams/chunking_strategy.svg)

滑动窗口方法确保跨分块边界的上下文连续性。关键参数：

| 参数 | 默认值 | 范围 | 描述 |
|-----|-------|------|------|
| CHUNK_SIZE | 800 字符 | 100-2000 | 每个分块的字符数 |
| CHUNK_OVERLAP | 150 字符 | N/A | 连续分块间的重叠 |
| MIN_CHUNK | 50 字符 | N/A | 最小分块长度阈值 |

## 环境要求

- Python 3.10+
- [Ollama](https://ollama.ai/) 本地运行（默认 `http://localhost:11434`）
- 聊天模型（如 `ollama pull qwen2.5`）
- 嵌入模型（如 `ollama pull nomic-embed-text`）

## 安装

### 方式一：从 PyPI 安装（推荐）

```bash
pip install gangdan
gangdan                    # Web 界面
gangdan cli                # 交互式 CLI
gangdan --port 8080        # 自定义端口
```

### 方式二：从源码安装

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
├── diagrams/                        # 架构图（SVG）
└── removed/                         # 已废弃文件
```

## 配置

所有设置通过**设置**标签页管理：Ollama URL、聊天/嵌入/重排序模型、代理、上下文长度、输出语言、向量数据库类型、LLM 提供商选择和 API 密钥。

## 测试

```bash
pip install pytest pytest-cov
pytest tests/ -v
pytest tests/ --cov=gangdan
```

## 学术论文

关于 RAG 管线和分块策略的详细实证研究，请参阅 [Article.md](Article.md) / [Article_CN.md](Article_CN.md)。

## 许可证

GPL-3.0-or-later。详见 [LICENSE](LICENSE)。
