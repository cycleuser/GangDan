# GangDan-Refined

模块化、Agent 管线架构的大语言模型知识管理工具。每个功能都是独立的可组合 Agent，通过 JSON 协议通信。

> **纲担** — 有纲领有担当。

## 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                     CLI 工具 (gd-*)                             │
│  gd-config  gd-models  gd-chat  gd-search  gd-summarize      │
│  gd-translate  gd-embed  gd-ask  gd-kb  gd-docs             │
│  gd-convert  gd-research  gd-learn  gd-preprint               │
└──────────────────────────┬──────────────────────────────────────┘
                           │ --json / --stdin 管道
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Agent 管线系统                                   │
│  AgentInput ──► Agent ──► AgentOutput ──► Agent ──► ...         │
│  Pipeline(A) | B | C  ──►  PipelineResult                       │
│  协议 v2.0：元数据、管线 ID、时间戳                                │
└──────────────────────────┬──────────────────────────────────────┘
                           │
              ┌────────────┼────────────────┐
              ▼            ▼                ▼
┌──────────────────┐ ┌──────────┐ ┌─────────────────┐
│    核心模块      │ │   LLM    │ │     存储层        │
│  config  i18n   │ │ ollama   │ │  chroma_manager  │
│  errors constants│ │ factory  │ │  kb_manager      │
│  port_utils     │ │ openai_  │ │  vector_db       │
│                 │ │ compat   │ │  conversation    │
│                 │ │ models   │ │  doc_manager     │
└──────────────────┘ └──────────┘ └─────────────────┘
              │            │                │
              ▼            ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Web 界面 (Flask)                             │
│  8 个蓝图，156+ 路由：                                            │
│  kb(28) learning(25) docs(10) preprint(14) research(16)         │
│  export(7) chat(2) settings(6) api(48)                         │
└─────────────────────────────────────────────────────────────────┘
```

## 核心设计决策

### Agent 管线架构

每个功能是一个独立的 **Agent**，遵循标准化 JSON 协议：

```python
# Agent 协议 v2.0
AgentInput  →  {query, text, file_path, data, options, metadata}
AgentOutput →  {success, data, error, metadata, protocol_version}
```

Agent 可通过 Unix 管道或 Python API 组合：

```bash
# CLI 管线 — 搜索 → 摘要 → 翻译
gd-search "量子计算" --json | gd-summarize --stdin --json | gd-translate --stdin --to en --json
```

```python
# Python API 管线
from gangdan_refined.agents import SearchAgent, SummarizeAgent, TranslateAgent
from gangdan_refined.agents.pipeline import Pipeline

pipeline = Pipeline(SearchAgent(), SummarizeAgent(), TranslateAgent())
result = pipeline.run(AgentInput(query="量子计算"))
print(result.data["translation"])
```

### 分组配置

配置按 9 个 dataclass 分组，替代原先 50+ 字段的扁平结构：

| 分组 | 字段 | 示例 |
|------|------|------|
| `proxy` | mode, http, https | `proxy.mode = "none"` |
| `llm` | chat_model, embedding_model, ollama_url, ... | `llm.chat_model = "qwen2.5:7b"` |
| `storage` | top_k, chunk_size, chunk_overlap, ... | `storage.top_k = 5` |
| `search` | web_search_engine, research_sources, ... | `search.web_search_engine = "duckduckgo"` |
| `learning` | default_question_type, num_questions, ... | `learning.default_question_type = "mcq"` |
| `adaptive` | auto_chunk_size, auto_context_length, ... | `adaptive.auto_chunk_size = True` |
| `document` | pdf_converter, download_retries, ... | `document.pdf_converter = "marker"` |
| `ui` | language, theme, ... | `ui.language = "zh"` |
| `logging` | level, file, ... | `logging.level = "INFO"` |

### 国际化 (i18n)

437 个翻译键，支持 10 种语言，存储在外部 JSON 文件中：

```python
from gangdan_refined.core.i18n import t
text = t("chat.send")  # → "Send" / "发送" / "送信" 等
```

## 14 个 Agent

| Agent | CLI 命令 | 描述 |
|-------|---------|------|
| ConfigAgent | `gd-config` | 查看/修改配置 |
| ModelsAgent | `gd-models` | 列出/管理 LLM 模型 |
| ChatAgent | `gd-chat` | 交互式 LLM 对话 |
| SearchAgent | `gd-search` | 网络和学术搜索 |
| SummarizeAgent | `gd-summarize` | 文本摘要（段落/要点/大纲） |
| TranslateAgent | `gd-translate` | 文本翻译 |
| EmbedAgent | `gd-embed` | 生成文本嵌入向量 |
| AskAgent | `gd-ask` | 基于知识库的 RAG 问答 |
| KBAgent | `gd-kb` | 知识库增删改查与搜索 |
| DocsAgent | `gd-docs` | 下载/索引文档 |
| ConvertAgent | `gd-convert` | PDF/HTML/TeX → Markdown |
| ResearchAgent | `gd-research` | 多阶段深度研究 |
| LearnAgent | `gd-learn` | 出题、引导学习、考试 |
| PreprintAgent | `gd-preprint` | 搜索/转换学术预印本 |

## 安装

```bash
# 从 PyPI 安装（发布后）
pip install gangdan-refined

# 从源码安装
git clone https://github.com/cycleuser/GangDan.git
cd GangDan/gangdan-refined
pip install -e .

# 安装可选依赖
pip install -e ".[search]"   # 网络搜索（duckduckgo、searxng）
pip install -e ".[pdf]"      # PDF 转换（marker、docling）
pip install -e ".[analytics]" # 分析工具
pip install -e ".[all]"      # 全部
```

## 快速开始

### 命令行

```bash
# 查看配置
gd-config --json show

# 列出可用模型
gd-models --json

# 网络搜索
gd-search "transformer 架构" --json

# 文本摘要
gd-summarize "长文本内容..." --style bullet --json

# 翻译
gd-translate "Hello world" --to zh --json

# 管线组合
gd-search "量子计算" --json | gd-summarize --stdin --json

# 知识库操作
gd-kb --action list --json
gd-kb --action create --name my-kb --json

# 基于知识库提问
gd-ask "什么是 RAG？" --kb-names my-kb --json

# Web 界面
gd-web --port 8080
```

### Python API

```python
from gangdan_refined.agents import SearchAgent, SummarizeAgent, TranslateAgent
from gangdan_refined.agents.protocol import AgentInput
from gangdan_refined.agents.pipeline import Pipeline

# 单个 Agent
agent = SearchAgent()
result = agent.run(AgentInput(query="transformer 架构"))
print(result.data["results"])

# 管线组合
pipeline = Pipeline(SearchAgent(), SummarizeAgent())
result = pipeline.run(AgentInput(query="量子计算"))
print(result.data["summary"])

# 使用 | 运算符
pipeline = Pipeline(SearchAgent()) | SummarizeAgent() | TranslateAgent()
result = pipeline.run(AgentInput(query="神经网络", options={"target_language": "zh"}))
```

## 项目结构

```
gangdan-refined/
├── pyproject.toml                     # 包配置，13 个 CLI 入口
├── gangdan_refined/
│   ├── __init__.py / __main__.py      # 包入口
│   ├── cli.py                          # CLI 路由
│   ├── cli_app/                        # 交互式 REPL
│   ├── api.py                          # 顶层 API 导出
│   ├── agents/                         # 14 个 Agent + 协议 + 管线
│   │   ├── base.py                     # BaseAgent 抽象基类
│   │   ├── protocol.py                 # AgentInput/Output/Metadata，v2.0
│   │   ├── pipeline.py                 # 管线组合引擎
│   │   ├── __init__.py                 # 注册表：get_agent()、list_agents()
│   │   ├── config_agent.py             # gd-config
│   │   ├── models_agent.py             # gd-models
│   │   ├── chat_agent.py              # gd-chat
│   │   ├── search_agent.py            # gd-search
│   │   ├── summarize_agent.py         # gd-summarize
│   │   ├── translate_agent.py         # gd-translate
│   │   ├── embed_agent.py             # gd-embed
│   │   ├── ask_agent.py               # gd-ask
│   │   ├── kb_agent.py                # gd-kb
│   │   ├── docs_agent.py              # gd-docs
│   │   ├── convert_agent.py           # gd-convert
│   │   ├── research_agent.py          # gd-research
│   │   ├── learn_agent.py             # gd-learn
│   │   └── preprint_agent.py          # gd-preprint
│   ├── commands/                       # CLI 命令实现
│   │   ├── common.py                  # 共享参数解析、输出格式化
│   │   ├── config.py / models.py / chat.py / search.py
│   │   ├── summarize.py / translate.py / embed.py / ask.py
│   │   ├── kb.py / docs.py / convert.py / research.py / web.py
│   ├── core/                           # 共享模块
│   │   ├── config.py                  # 9 个分组 dataclass 配置
│   │   ├── i18n.py                    # 外部翻译加载器
│   │   ├── constants.py               # 路径常量
│   │   ├── errors.py                  # 错误层次结构
│   │   ├── port_utils.py             # 端口检测
│   │   └── locales/translations.json # 437 键 × 10 语言
│   ├── llm/                            # LLM 抽象层
│   │   ├── ollama.py                 # Ollama 客户端
│   │   ├── openai_compat.py          # OpenAI 兼容提供商
│   │   ├── factory.py                # 提供商工厂
│   │   └── models.py                 # 提供商配置
│   ├── storage/                        # 持久化层
│   │   ├── chroma_manager.py         # ChromaDB 自恢复
│   │   ├── kb_manager.py             # 知识库增删改查
│   │   ├── vector_db.py              # 多后端向量数据库
│   │   ├── conversation.py           # 对话历史自动保存
│   │   ├── doc_manager.py           # 文档下载/索引
│   │   └── image_handler.py         # 图片提取/存储
│   ├── search/                         # 搜索后端
│   │   ├── web_searcher.py           # DuckDuckGo/SearXNG/Brave
│   │   ├── research_searcher.py       # 学术搜索（arXiv、S2 等）
│   │   ├── adaptive_search.py        # 查询精炼
│   │   └── query_expander.py        # 翻译 + 同义词扩展
│   ├── learning/                       # 教学模块
│   │   ├── question_gen.py           # 选择题/简答题/判断题生成
│   │   ├── guided.py                 # 引导学习会话
│   │   ├── exam.py                   # 试卷生成
│   │   ├── lecture.py                # 课件内容
│   │   ├── research.py              # 多阶段研究报告
│   │   └── prompts.py               # 提示词模板
│   ├── document/                       # 文档处理
│   │   ├── pdf_converter.py         # PDF → Markdown
│   │   ├── pdf_downloader.py        # 论文下载
│   │   ├── pdf_renamer.py          # 引用格式命名
│   │   └── preprint/                # 预印本搜索/转换/批量
│   ├── research/                       # 深度研究管线
│   │   ├── pipeline.py              # 多阶段研究
│   │   ├── models.py                # 数据模型
│   │   └── export.py                # 报告导出
│   └── web/                            # Flask Web 界面
│       ├── app.py                    # Flask 工厂（8 个蓝图）
│       └── routes/                   # 156+ 路由处理
│           ├── kb.py / learning.py / docs.py / preprint.py
│           ├── research.py / export.py / chat.py / settings.py
│           └── api.py                # REST API 路由
└── tests/                              # 352 个测试
    ├── test_agent_protocol.py         # 协议层测试
    ├── test_agent_base_pipeline.py    # BaseAgent + Pipeline 测试
    ├── test_agent_whitebox.py        # 14 个 Agent 模拟依赖测试
    ├── test_pipeline_e2e.py          # 管线组合端到端测试
    ├── test_cli_commands.py           # CLI 命令测试
    ├── test_edge_cases.py             # 错误处理 + 边界情况
    ├── test_config.py                 # 配置测试
    ├── test_llm.py                    # LLM 客户端测试
    ├── test_errors.py                 # 错误层次测试
    ├── test_web_routes.py             # Web 路由测试
    └── test_architecture.py           # 架构验证
```

## 测试

```bash
pip install pytest pytest-cov

# 运行全部测试
pytest tests/ -v

# 运行并查看覆盖率
pytest tests/ --cov=gangdan_refined

# 运行指定测试文件
pytest tests/test_agent_whitebox.py -v

# 遇到第一个失败即停止
pytest tests/ -x
```

### 测试覆盖

| 模块 | 测试数 | 重点 |
|------|--------|------|
| 协议 | 60 | AgentInput/Output/Metadata、编解码、验证 |
| BaseAgent | 19 | Agent 抽象基类、CLI 参数、JSON/文本输出 |
| Pipeline | 17 | 组合、__or__、错误传播、数据流 |
| 白盒 | 35+ | 全部 14 个 Agent（模拟依赖） |
| 端到端 | 21 | 管线组合（真实和测试 Agent） |
| CLI | 16 | 全部 12 个 CLI 命令 |
| 边界情况 | 15 | 错误处理、空白输入、None 值 |
| 配置 | 13 | 配置分组、验证、保存/加载 |
| LLM | 12 | Ollama 客户端、工厂、错误 |
| Web 路由 | 44 | 页面路由和 API 端点 |
| 架构 | 15 | 模块结构、导入、规范 |

## Agent 协议 v2.0

### 输入格式

```json
{
  "query": "量子计算",
  "text": "可选的待处理文本内容",
  "file_path": "/path/to/document.pdf",
  "data": {"key": "value"},
  "options": {"model": "qwen2.5:7b", "language": "zh"},
  "metadata": {
    "agent": "gd-search",
    "version": "2.0.0",
    "timestamp": "2026-05-22T10:30:00+00:00",
    "pipeline_id": "pipe_12345678"
  }
}
```

### 输出格式

```json
{
  "success": true,
  "data": {
    "results": [...],
    "count": 10,
    "source": "web"
  },
  "error": null,
  "metadata": {
    "agent": "gd-search",
    "version": "2.0.0",
    "timestamp": "2026-05-22T10:30:01+00:00",
    "pipeline_id": "pipe_12345678"
  },
  "protocol_version": "2.0"
}
```

### 管线组合

```python
# Python：使用 | 运算符的管线
pipeline = Pipeline(SearchAgent()) | SummarizeAgent() | TranslateAgent()
result = pipeline.run(AgentInput(query="神经网络"))

# CLI：Unix 管道链
gd-search "主题" --json | gd-summarize --stdin --json | gd-translate --stdin --to zh --json
```

管线结果跟踪每个步骤：

```json
{
  "success": true,
  "data": {...},
  "steps": [
    {"name": "gd-search", "duration_ms": 450.2, "success": true},
    {"name": "gd-summarize", "duration_ms": 1200.5, "success": true}
  ],
  "pipeline_id": "pipe_1779336607901",
  "total_duration_ms": 1650.7,
  "protocol_version": "2.0"
}
```

## Ollama 设置

```bash
ollama serve
ollama pull qwen2.5
ollama pull nomic-embed-text
```

## 配置

所有设置通过 `gd-config` CLI 或 Web 界面设置标签页管理：

```bash
# 显示所有配置
gd-config --json show

# 获取指定值
gd-config --json get llm.chat_model

# 设置值
gd-config --json set llm.chat_model=qwen2.5:7b

# 列出 LLM 提供商
gd-config --json providers
```

## 环境要求

- Python 3.10+
- [Ollama](https://ollama.ai/) 本地运行（默认 `http://localhost:11434`）
- 聊天模型（如 `ollama pull qwen2.5`）
- 嵌入模型（如 `ollama pull nomic-embed-text`）

## 许可证

GPL-3.0-or-later。详见 [LICENSE](LICENSE)。