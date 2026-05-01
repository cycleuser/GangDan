"""Configuration management for GangDan.

This module handles global configuration, internationalization (i18n),
and utility functions for the GangDan application.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .constants import (
    CHUNK_OVERLAP_DEFAULT,
    CHUNK_SIZE_DEFAULT,
    DEFAULT_CHAT_MODEL,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LANGUAGE,
    DEFAULT_TOP_K,
    MAX_CONTEXT_TOKENS_DEFAULT,
    OLLAMA_DEFAULT_URL,
)


def _get_data_dir() -> Path:
    """Determine the data directory based on environment or install context."""
    env = os.environ.get("GANGDAN_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()

    pkg_dir = Path(__file__).resolve().parent.parent
    if "site-packages" in str(pkg_dir) or "dist-packages" in str(pkg_dir):
        return Path.home() / ".gangdan"
    return Path("./data")


DATA_DIR = _get_data_dir()
DOCS_DIR = DATA_DIR / "docs"
CHROMA_DIR = DATA_DIR / "chroma"
CONFIG_FILE = DATA_DIR / "gangdan_config.json"
USER_KBS_FILE = DATA_DIR / "user_kbs.json"


@dataclass
class Config:
    """GangDan configuration with sensible defaults."""

    ollama_url: str = OLLAMA_DEFAULT_URL
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    chat_model: str = DEFAULT_CHAT_MODEL
    reranker_model: str = ""
    chunk_size: int = CHUNK_SIZE_DEFAULT
    chunk_overlap: int = CHUNK_OVERLAP_DEFAULT
    top_k: int = DEFAULT_TOP_K
    max_context_tokens: int = MAX_CONTEXT_TOKENS_DEFAULT
    language: str = DEFAULT_LANGUAGE
    output_language: str = DEFAULT_LANGUAGE
    context_length: int = 4096

    proxy_mode: str = "none"
    proxy_http: str = ""
    proxy_https: str = ""

    strict_kb_mode: bool = False
    vector_db_type: str = "chroma"

    research_provider: str = "ollama"
    research_api_key: str = ""
    research_api_base_url: str = ""
    research_model: str = ""

    chat_provider: str = "ollama"
    chat_api_key: str = ""
    chat_api_base_url: str = ""
    chat_model_name: str = ""

    rag_distance_threshold: float = 0.5
    chat_temperature: float = 0.7
    chat_max_tokens: int = 4096

    # Research search configuration
    query_expansion_enabled: bool = False
    query_expansion_model: str = ""
    research_search_sources: str = "arxiv,semantic_scholar,crossref,openalex,dblp"
    research_max_results: int = 10
    research_search_timeout: int = 15
    semantic_scholar_api_key: str = ""
    crossref_email: str = ""
    pubmed_api_key: str = ""
    github_token: str = ""
    openalex_email: str = ""

    # PDF processing configuration
    pdf_rename_enabled: bool = True
    pdf_convert_enabled: bool = True
    pdf_convert_engine: str = "auto"
    unpaywall_email: str = "gangdan@localhost"

    # Web search engine configuration
    web_search_engine: str = "duckduckgo"
    serper_api_key: str = ""
    brave_api_key: str = ""

    # Semantic Scholar cache TTL (seconds)
    s2_cache_ttl: int = 86400

    # Research pipeline configuration
    research_pipeline_convert: bool = True
    research_pipeline_index: bool = False
    research_pipeline_rename: bool = True


CONFIG = Config()


def get_proxies() -> Optional[Dict[str, str]]:
    """Get proxy configuration based on proxy_mode setting."""
    if CONFIG.proxy_mode == "none":
        return None

    if CONFIG.proxy_mode == "system":
        http_proxy = os.environ.get("HTTP_PROXY", os.environ.get("http_proxy", ""))
        https_proxy = os.environ.get("HTTPS_PROXY", os.environ.get("https_proxy", ""))
        if http_proxy or https_proxy:
            return {"http": http_proxy, "https": https_proxy or http_proxy}
        return None

    if CONFIG.proxy_mode == "manual":
        if CONFIG.proxy_http or CONFIG.proxy_https:
            return {
                "http": CONFIG.proxy_http,
                "https": CONFIG.proxy_https or CONFIG.proxy_http,
            }
        return None

    return None


def load_config() -> None:
    """Load configuration from disk."""
    global CONFIG

    if not CONFIG_FILE.exists():
        return

    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        CONFIG.ollama_url = data.get("ollama_url", CONFIG.ollama_url)
        CONFIG.embedding_model = data.get("embedding_model", CONFIG.embedding_model)
        CONFIG.chat_model = data.get("chat_model", CONFIG.chat_model)
        CONFIG.reranker_model = data.get("reranker_model", CONFIG.reranker_model)
        CONFIG.top_k = data.get("top_k", CONFIG.top_k)
        CONFIG.language = data.get("language", CONFIG.language)
        CONFIG.proxy_mode = data.get("proxy_mode", CONFIG.proxy_mode)
        CONFIG.proxy_http = data.get("proxy_http", CONFIG.proxy_http)
        CONFIG.proxy_https = data.get("proxy_https", CONFIG.proxy_https)
        CONFIG.strict_kb_mode = data.get("strict_kb_mode", CONFIG.strict_kb_mode)
        CONFIG.vector_db_type = data.get("vector_db_type", CONFIG.vector_db_type)
        CONFIG.context_length = data.get("context_length", CONFIG.context_length)
        CONFIG.max_context_tokens = data.get(
            "max_context_tokens", CONFIG.max_context_tokens
        )
        CONFIG.output_language = data.get("output_language", CONFIG.output_language)
        CONFIG.research_provider = data.get(
            "research_provider", CONFIG.research_provider
        )
        CONFIG.research_api_key = data.get("research_api_key", CONFIG.research_api_key)
        CONFIG.research_api_base_url = data.get(
            "research_api_base_url", CONFIG.research_api_base_url
        )
        CONFIG.research_model = data.get("research_model", CONFIG.research_model)
        CONFIG.chat_provider = data.get("chat_provider", CONFIG.chat_provider)
        CONFIG.chat_api_key = data.get("chat_api_key", CONFIG.chat_api_key)
        CONFIG.chat_api_base_url = data.get("chat_api_base_url", CONFIG.chat_api_base_url)
        CONFIG.chat_model_name = data.get("chat_model_name", CONFIG.chat_model_name)
        CONFIG.rag_distance_threshold = data.get("rag_distance_threshold", CONFIG.rag_distance_threshold)
        CONFIG.chat_temperature = data.get("chat_temperature", CONFIG.chat_temperature)
        CONFIG.chat_max_tokens = data.get("chat_max_tokens", CONFIG.chat_max_tokens)
        CONFIG.query_expansion_enabled = data.get("query_expansion_enabled", CONFIG.query_expansion_enabled)
        CONFIG.query_expansion_model = data.get("query_expansion_model", CONFIG.query_expansion_model)
        CONFIG.research_search_sources = data.get("research_search_sources", CONFIG.research_search_sources)
        CONFIG.research_max_results = data.get("research_max_results", CONFIG.research_max_results)
        CONFIG.research_search_timeout = data.get("research_search_timeout", CONFIG.research_search_timeout)
        CONFIG.semantic_scholar_api_key = data.get("semantic_scholar_api_key", CONFIG.semantic_scholar_api_key)
        CONFIG.crossref_email = data.get("crossref_email", CONFIG.crossref_email)
        CONFIG.pubmed_api_key = data.get("pubmed_api_key", CONFIG.pubmed_api_key)
        CONFIG.github_token = data.get("github_token", CONFIG.github_token)
        CONFIG.openalex_email = data.get("openalex_email", CONFIG.openalex_email)
        CONFIG.pdf_rename_enabled = data.get("pdf_rename_enabled", CONFIG.pdf_rename_enabled)
        CONFIG.pdf_convert_enabled = data.get("pdf_convert_enabled", CONFIG.pdf_convert_enabled)
        CONFIG.pdf_convert_engine = data.get("pdf_convert_engine", CONFIG.pdf_convert_engine)
        CONFIG.unpaywall_email = data.get("unpaywall_email", CONFIG.unpaywall_email)
        CONFIG.web_search_engine = data.get("web_search_engine", CONFIG.web_search_engine)
        CONFIG.serper_api_key = data.get("serper_api_key", CONFIG.serper_api_key)
        CONFIG.brave_api_key = data.get("brave_api_key", CONFIG.brave_api_key)
        CONFIG.s2_cache_ttl = data.get("s2_cache_ttl", CONFIG.s2_cache_ttl)
        CONFIG.research_pipeline_convert = data.get("research_pipeline_convert", CONFIG.research_pipeline_convert)
        CONFIG.research_pipeline_index = data.get("research_pipeline_index", CONFIG.research_pipeline_index)
        CONFIG.research_pipeline_rename = data.get("research_pipeline_rename", CONFIG.research_pipeline_rename)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[Config] Error loading config, using defaults: {e}", file=sys.stderr)
        pass


def save_config() -> None:
    """Save configuration to disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    config_data = {
        "ollama_url": CONFIG.ollama_url,
        "embedding_model": CONFIG.embedding_model,
        "chat_model": CONFIG.chat_model,
        "reranker_model": CONFIG.reranker_model,
        "top_k": CONFIG.top_k,
        "language": CONFIG.language,
        "output_language": CONFIG.output_language,
        "context_length": CONFIG.context_length,
        "max_context_tokens": CONFIG.max_context_tokens,
        "proxy_mode": CONFIG.proxy_mode,
        "proxy_http": CONFIG.proxy_http,
        "proxy_https": CONFIG.proxy_https,
        "strict_kb_mode": CONFIG.strict_kb_mode,
        "vector_db_type": CONFIG.vector_db_type,
        "research_provider": CONFIG.research_provider,
        "research_api_key": CONFIG.research_api_key,
        "research_api_base_url": CONFIG.research_api_base_url,
        "research_model": CONFIG.research_model,
        "chat_provider": CONFIG.chat_provider,
        "chat_api_key": CONFIG.chat_api_key,
        "chat_api_base_url": CONFIG.chat_api_base_url,
        "chat_model_name": CONFIG.chat_model_name,
        "rag_distance_threshold": CONFIG.rag_distance_threshold,
        "chat_temperature": CONFIG.chat_temperature,
        "chat_max_tokens": CONFIG.chat_max_tokens,
        "query_expansion_enabled": CONFIG.query_expansion_enabled,
        "query_expansion_model": CONFIG.query_expansion_model,
        "research_search_sources": CONFIG.research_search_sources,
        "research_max_results": CONFIG.research_max_results,
        "research_search_timeout": CONFIG.research_search_timeout,
        "semantic_scholar_api_key": CONFIG.semantic_scholar_api_key,
        "crossref_email": CONFIG.crossref_email,
        "pubmed_api_key": CONFIG.pubmed_api_key,
        "github_token": CONFIG.github_token,
        "openalex_email": CONFIG.openalex_email,
        "pdf_rename_enabled": CONFIG.pdf_rename_enabled,
        "pdf_convert_enabled": CONFIG.pdf_convert_enabled,
        "pdf_convert_engine": CONFIG.pdf_convert_engine,
        "unpaywall_email": CONFIG.unpaywall_email,
        "web_search_engine": CONFIG.web_search_engine,
        "serper_api_key": CONFIG.serper_api_key,
        "brave_api_key": CONFIG.brave_api_key,
        "s2_cache_ttl": CONFIG.s2_cache_ttl,
        "research_pipeline_convert": CONFIG.research_pipeline_convert,
        "research_pipeline_index": CONFIG.research_pipeline_index,
        "research_pipeline_rename": CONFIG.research_pipeline_rename,
    }

    CONFIG_FILE.write_text(
        json.dumps(config_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_user_kbs() -> Dict:
    """Load user-created knowledge base manifest."""
    if USER_KBS_FILE.exists():
        try:
            return json.loads(USER_KBS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_user_kb(
    internal_name: str,
    display_name: str,
    file_count: int,
    languages: Optional[List[str]] = None,
    output_word_limit: Optional[int] = None,
) -> None:
    """Add or update a user KB entry in the manifest."""
    kbs = load_user_kbs()

    entry: Dict = {
        "display_name": display_name,
        "created": datetime.now().isoformat(),
        "file_count": file_count,
        "languages": languages or [],
    }

    if output_word_limit is not None:
        entry["output_word_limit"] = output_word_limit

    kbs[internal_name] = entry

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    USER_KBS_FILE.write_text(
        json.dumps(kbs, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def delete_user_kb(internal_name: str) -> None:
    """Remove a user KB entry from the manifest."""
    kbs = load_user_kbs()
    kbs.pop(internal_name, None)
    USER_KBS_FILE.write_text(
        json.dumps(kbs, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def sanitize_kb_name(name: str) -> str:
    """Sanitize user-provided KB name to a safe internal name with user_ prefix.

    Parameters
    ----------
    name : str
        User-provided knowledge base name.

    Returns
    -------
    str
        Sanitized internal name with 'user_' prefix.

    Notes
    -----
    - Removes special characters, keeping only alphanumeric, spaces, and hyphens
    - Converts spaces and hyphens to underscores
    - Uses MD5 hash if resulting name is too short
    - Always prefixes with 'user_'
    """
    from .constants import KB_NAME_HASH_LENGTH, KB_NAME_MIN_LENGTH

    safe = re.sub(r"[^a-zA-Z0-9\s-]", "", name.strip()).strip()
    safe = re.sub(r"[\s-]+", "_", safe).lower()

    if not safe or len(safe) < KB_NAME_MIN_LENGTH:
        name_hash = hashlib.md5(name.encode("utf-8")).hexdigest()[:KB_NAME_HASH_LENGTH]
        safe = f"kb_{name_hash}"

    return f"user_{safe}"


LANGUAGES = {
    "zh": "中文",
    "en": "English",
    "ja": "日本語",
    "fr": "Français",
    "ru": "Русский",
    "de": "Deutsch",
    "it": "Italiano",
    "es": "Español",
    "pt": "Português",
    "ko": "한국어",
}

# Language detection thresholds
LANGUAGE_THRESHOLD = 0.1
SAMPLE_SIZE = 500

# Unicode ranges for language detection
CJK_RANGE = ("\u4e00", "\u9fff")
HIRAGANA_RANGE = ("\u3040", "\u309f")
KATAKANA_RANGE = ("\u30a0", "\u30ff")
HANGUL_RANGE = ("\uac00", "\ud7af")
CYRILLIC_RANGE = ("\u0400", "\u04ff")


def detect_language(text: str) -> str:
    """Detect language using Unicode character ranges.

    Parameters
    ----------
    text : str
        Text sample for language detection.

    Returns
    -------
    str
        ISO 639-1 language code (zh, en, ja, ko, ru, fr, de, es, pt, it).
        Returns 'unknown' if unclear.

    Notes
    -----
    Analyzes first 500 characters using Unicode block detection.
    """
    if not text:
        return "unknown"

    sample = text[:SAMPLE_SIZE]
    total = len(sample)

    cjk = sum(1 for c in sample if CJK_RANGE[0] <= c <= CJK_RANGE[1])
    hiragana = sum(1 for c in sample if HIRAGANA_RANGE[0] <= c <= HIRAGANA_RANGE[1])
    katakana = sum(1 for c in sample if KATAKANA_RANGE[0] <= c <= KATAKANA_RANGE[1])
    hangul = sum(1 for c in sample if HANGUL_RANGE[0] <= c <= HANGUL_RANGE[1])
    cyrillic = sum(1 for c in sample if CYRILLIC_RANGE[0] <= c <= CYRILLIC_RANGE[1])

    if (hiragana + katakana) / total > LANGUAGE_THRESHOLD:
        return "ja"
    if hangul / total > LANGUAGE_THRESHOLD:
        return "ko"
    if cjk / total > LANGUAGE_THRESHOLD:
        return "zh"
    if cyrillic / total > LANGUAGE_THRESHOLD:
        return "ru"

    return "en"


TRANSLATIONS = {
    "app_title": {
        "zh": "纲担",
        "en": "GangDan",
        "ja": "GangDan",
        "fr": "GangDan",
        "ru": "GangDan",
        "de": "GangDan",
        "it": "GangDan",
        "es": "GangDan",
        "pt": "GangDan",
        "ko": "GangDan",
    },
    "app_subtitle": {
        "zh": "有纲领有担当，基于 Ollama 和 ChromaDB 的离线开发助手",
        "en": "Local offline programming assistant powered by Ollama and ChromaDB",
        "ja": "Ollama と ChromaDB を使用した\nローカルオフラインプログラミングアシスタント",
        "fr": "Assistant de programmation hors-ligne\nbasé sur Ollama et ChromaDB",
        "ru": "Локальный офлайн-помощник на базе Ollama и ChromaDB",
        "de": "Lokaler Offline-Programmierassistent\nmit Ollama und ChromaDB",
        "it": "Assistente di programmazione offline\nbasato su Ollama e ChromaDB",
        "es": "Asistente de programación offline\nbasado en Ollama e ChromaDB",
        "pt": "Assistente de programação offline\nbaseado em Ollama e ChromaDB",
        "ko": "Ollama 와 ChromaDB 기반\n로컬 오프라인 프로그래밍 어시스턴트",
    },
    "chat": {
        "zh": "对话",
        "en": "Chat",
        "ja": "チャット",
        "fr": "Chat",
        "ru": "Чат",
        "de": "Chat",
        "it": "Chat",
        "es": "Chat",
        "pt": "Chat",
        "ko": "채팅",
    },
    "docs": {
        "zh": "文档",
        "en": "Docs",
        "ja": "ドキュメント",
        "fr": "Docs",
        "ru": "Документы",
        "de": "Dokumente",
        "it": "Documenti",
        "es": "Docs",
        "pt": "Docs",
        "ko": "문서",
    },
    "settings": {
        "zh": "设置",
        "en": "Settings",
        "ja": "設定",
        "fr": "Paramètres",
        "ru": "Настройки",
        "de": "Einstellungen",
        "it": "Impostazioni",
        "es": "Configuración",
        "pt": "Configurações",
        "ko": "설정",
    },
    "chat_provider": {
        "zh": "聊天模型提供商",
        "en": "Chat Model Provider",
        "ja": "チャットモデルプロバイダー",
        "fr": "Fournisseur de modèle de chat",
        "ru": "Провайдер чат-модели",
        "de": "Chat-Modell-Anbieter",
        "it": "Provider del modello chat",
        "es": "Proveedor de modelo de chat",
        "pt": "Provedor de modelo de chat",
        "ko": "챗 모델 제공자",
    },
    "send": {
        "zh": "发送",
        "en": "Send",
        "ja": "送信",
        "fr": "Envoyer",
        "ru": "Отправить",
        "de": "Senden",
        "it": "Invia",
        "es": "Enviar",
        "pt": "Enviar",
        "ko": "보내기",
    },
    "stop": {
        "zh": "停止",
        "en": "Stop",
        "ja": "停止",
        "fr": "Arrêter",
        "ru": "Стоп",
        "de": "Stopp",
        "it": "Ferma",
        "es": "Parar",
        "pt": "Parar",
        "ko": "중지",
    },
    "clear": {
        "zh": "清除",
        "en": "Clear",
        "ja": "クリア",
        "fr": "Effacer",
        "ru": "Очистить",
        "de": "Löschen",
        "it": "Cancella",
        "es": "Borrar",
        "pt": "Limpar",
        "ko": "지우기",
    },
    "export": {
        "zh": "导出",
        "en": "Export",
        "ja": "エクスポート",
        "fr": "Exporter",
        "ru": "Экспорт",
        "de": "Exportieren",
        "it": "Esporta",
        "es": "Exportar",
        "pt": "Exportar",
        "ko": "내보내기",
    },
    "save_conversation": {
        "zh": "保存对话",
        "en": "Save Chat",
        "ja": "会話を保存",
        "fr": "Enregistrer le chat",
        "ru": "Сохранить чат",
        "de": "Chat speichern",
        "it": "Salva chat",
        "es": "Guardar chat",
        "pt": "Salvar chat",
        "ko": "대화 저장",
    },
    "load_conversation": {
        "zh": "加载对话",
        "en": "Load Chat",
        "ja": "会話を読み込む",
        "fr": "Charger le chat",
        "ru": "Загрузить чат",
        "de": "Chat laden",
        "it": "Carica chat",
        "es": "Cargar chat",
        "pt": "Carregar chat",
        "ko": "대화 불러오기",
    },
    "conversation_loaded": {
        "zh": "已加载 {0} 条消息",
        "en": "Loaded {0} messages",
        "ja": "{0} 件のメッセージを読み込みました",
        "fr": "{0} messages chargés",
        "ru": "Загружено {0} сообщений",
        "de": "{0} Nachrichten geladen",
        "it": "{0} messaggi caricati",
        "es": "{0} mensajes cargados",
        "pt": "{0} mensagens carregadas",
        "ko": "{0} 개 메시지 로드됨",
    },
    "invalid_conversation_file": {
        "zh": "无效的对话文件",
        "en": "Invalid conversation file",
        "ja": "無効な会話ファイル",
        "fr": "Fichier de conversation invalide",
        "ru": "Неверный файл разговора",
        "de": "Ungültige Konversationsdatei",
        "it": "File conversazione non valido",
        "es": "Archivo de conversación inválido",
        "pt": "Arquivo de conversa inválido",
        "ko": "잘못된 대화 파일",
    },
    "use_kb": {
        "zh": "使用知识库",
        "en": "Use Knowledge Base",
        "ja": "知識ベースを使用",
        "fr": "Utiliser la base de connaissances",
        "ru": "Использовать базу знаний",
        "de": "Wissensdatenbank verwenden",
        "it": "Usa base di conoscenza",
        "es": "Usar base de conocimiento",
        "pt": "Usar base de conhecimento",
        "ko": "지식 베이스 사용",
    },
    "use_web": {
        "zh": "搜索网络",
        "en": "Search Web",
        "ja": "ウェブ検索",
        "fr": "Rechercher sur le Web",
        "ru": "Поиск в интернете",
        "de": "Web durchsuchen",
        "it": "Cerca sul Web",
        "es": "Buscar en la Web",
        "pt": "Pesquisar na Web",
        "ko": "웹 검색",
    },
    "download": {
        "zh": "下载",
        "en": "Download",
        "ja": "ダウンロード",
        "fr": "Télécharger",
        "ru": "Скачать",
        "de": "Herunterladen",
        "it": "Scarica",
        "es": "Descargar",
        "pt": "Baixar",
        "ko": "다운로드",
    },
    "index": {
        "zh": "索引",
        "en": "Index",
        "ja": "インデックス",
        "fr": "Indexer",
        "ru": "Индексировать",
        "de": "Indexieren",
        "it": "Indicizza",
        "es": "Indexar",
        "pt": "Indexar",
        "ko": "인덱스",
    },
    "refresh": {
        "zh": "刷新",
        "en": "Refresh",
        "ja": "更新",
        "fr": "Actualiser",
        "ru": "Обновить",
        "de": "Aktualisieren",
        "it": "Aggiorna",
        "es": "Actualizar",
        "pt": "Atualizar",
        "ko": "새로고침",
    },
    "save": {
        "zh": "保存",
        "en": "Save",
        "ja": "保存",
        "fr": "Enregistrer",
        "ru": "Сохранить",
        "de": "Speichern",
        "it": "Salva",
        "es": "Guardar",
        "pt": "Salvar",
        "ko": "저장",
    },
    "embedding_model": {
        "zh": "嵌入模型",
        "en": "Embedding Model",
        "ja": "埋め込みモデル",
        "fr": "Modèle d'embedding",
        "ru": "Модель эмбеддинга",
        "de": "Embedding-Modell",
        "it": "Modello di embedding",
        "es": "Modelo de embedding",
        "pt": "Modelo de embedding",
        "ko": "임베딩 모델",
    },
    "chat_model": {
        "zh": "聊天模型",
        "en": "Chat Model",
        "ja": "チャットモデル",
        "fr": "Modèle de chat",
        "ru": "Модель чата",
        "de": "Chat-Modell",
        "it": "Modello di chat",
        "es": "Modelo de chat",
        "pt": "Modelo de chat",
        "ko": "채팅 모델",
    },
    "language": {
        "zh": "界面语言",
        "en": "UI Language",
        "ja": "UI 言語",
        "fr": "Langue de l'interface",
        "ru": "Язык интерфейса",
        "de": "Oberflächensprache",
        "it": "Lingua dell'interfaccia",
        "es": "Idioma de interfaz",
        "pt": "Idioma da interface",
        "ko": "인터페이스 언어",
    },
    "select_source": {
        "zh": "选择源",
        "en": "Select Source",
        "ja": "ソースを選択",
        "fr": "Sélectionner la source",
        "ru": "Выбрать источник",
        "de": "Quelle auswählen",
        "it": "Seleziona fonte",
        "es": "Seleccionar fuente",
        "pt": "Selecionar fonte",
        "ko": "소스 선택",
    },
    "downloaded": {
        "zh": "已下载",
        "en": "Downloaded",
        "ja": "ダウンロード済み",
        "fr": "Téléchargé",
        "ru": "Загружено",
        "de": "Heruntergeladen",
        "it": "Scaricato",
        "es": "Descargado",
        "pt": "Baixado",
        "ko": "다운로드됨",
    },
    "indexed": {
        "zh": "已索引",
        "en": "Indexed",
        "ja": "インデックス済み",
        "fr": "Indexé",
        "ru": "Проиндексировано",
        "de": "Indexiert",
        "it": "Indicizzato",
        "es": "Indexado",
        "pt": "Indexado",
        "ko": "인덱스됨",
    },
    "status": {
        "zh": "状态",
        "en": "Status",
        "ja": "状態",
        "fr": "État",
        "ru": "Статус",
        "de": "Status",
        "it": "Stato",
        "es": "Estado",
        "pt": "Estado",
        "ko": "상태",
    },
    "ollama_url": {
        "zh": "Ollama 地址",
        "en": "Ollama URL",
        "ja": "Ollama URL",
        "fr": "URL Ollama",
        "ru": "URL Ollama",
        "de": "Ollama-URL",
        "it": "URL Ollama",
        "es": "URL de Ollama",
        "pt": "URL do Ollama",
        "ko": "Ollama URL",
    },
    "test_connection": {
        "zh": "测试连接",
        "en": "Test Connection",
        "ja": "接続テスト",
        "fr": "Tester la connexion",
        "ru": "Тест соединения",
        "de": "Verbindung testen",
        "it": "Test connessione",
        "es": "Probar conexión",
        "pt": "Testar conexão",
        "ko": "연결 테스트",
    },
    "type_message": {
        "zh": "输入消息...",
        "en": "Type a message...",
        "ja": "メッセージを入力...",
        "fr": "Tapez un message...",
        "ru": "Введите сообщение...",
        "de": "Nachricht eingeben...",
        "it": "Digita un messaggio...",
        "es": "Escribe un mensaje...",
        "pt": "Digite uma mensagem...",
        "ko": "메시지를 입력하세요...",
    },
    "no_models": {
        "zh": "未检测到模型，请先拉取模型",
        "en": "No models detected, please pull models first",
        "ja": "モデルが検出されません。最初にモデルをプルしてください",
        "fr": "Aucun modèle détecté, veuillez d'abord télécharger des modèles",
        "ru": "Модели не обнаружены, сначала загрузите модели",
        "de": "Keine Modelle erkannt, bitte zuerst Modelle laden",
        "it": "Nessun modello rilevato, prima scarica i modelli",
        "es": "No se detectaron modelos, primero descargue modelos",
        "pt": "Nenhum modelo detectado, primeiro baixe modelos",
        "ko": "모델이 감지되지 않았습니다. 먼저 모델을 다운로드하세요",
    },
    "generation_stopped": {
        "zh": "生成已停止",
        "en": "Generation stopped",
        "ja": "生成が停止しました",
        "fr": "Génération arrêtée",
        "ru": "Генерация остановлена",
        "de": "Generierung gestoppt",
        "it": "Generazione interrotta",
        "es": "Generación detenida",
        "pt": "Geração interrompida",
        "ko": "생성이 중지되었습니다",
    },
    "proxy_settings": {
        "zh": "代理设置",
        "en": "Proxy Settings",
        "ja": "プロキシ設定",
        "fr": "Paramètres proxy",
        "ru": "Настройки прокси",
        "de": "Proxy-Einstellungen",
        "it": "Impostazioni proxy",
        "es": "Configuración de proxy",
        "pt": "Configurações de proxy",
        "ko": "프록시 설정",
    },
    "no_proxy": {
        "zh": "不使用代理",
        "en": "No Proxy",
        "ja": "プロキシなし",
        "fr": "Pas de proxy",
        "ru": "Без прокси",
        "de": "Kein Proxy",
        "it": "Nessun proxy",
        "es": "Sin proxy",
        "pt": "Sem proxy",
        "ko": "프록시 없음",
    },
    "system_proxy": {
        "zh": "系统代理",
        "en": "System Proxy",
        "ja": "システムプロキシ",
        "fr": "Proxy système",
        "ru": "Системный прокси",
        "de": "System-Proxy",
        "it": "Proxy di sistema",
        "es": "Proxy del sistema",
        "pt": "Proxy do sistema",
        "ko": "시스템 프록시",
    },
    "manual_proxy": {
        "zh": "手动设置",
        "en": "Manual Proxy",
        "ja": "手動プロキシ",
        "fr": "Proxy manuel",
        "ru": "Ручной прокси",
        "de": "Manueller Proxy",
        "it": "Proxy manuale",
        "es": "Proxy manual",
        "pt": "Proxy manual",
        "ko": "수동 프록시",
    },
    "ai_assistant": {
        "zh": "AI 命令助手",
        "en": "AI Command Assistant",
        "ja": "AI コマンドアシスタント",
        "fr": "Assistant de commandes IA",
        "ru": "AI Командный помощник",
        "de": "KI-Befehlsassistent",
        "it": "Assistente comandi IA",
        "es": "Asistente de comandos IA",
        "pt": "Assistente de comandos IA",
        "ko": "AI 명령 어시스턴트",
    },
    "command_line": {
        "zh": "命令行",
        "en": "Command Line",
        "ja": "コマンドライン",
        "fr": "Ligne de commande",
        "ru": "Командная строка",
        "de": "Befehlszeile",
        "it": "Riga di comando",
        "es": "Línea de comandos",
        "pt": "Linha de comando",
        "ko": "명령줄",
    },
    "ai_ask_desc": {
        "zh": "输入问题或描述任务...",
        "en": "Describe what you want to do...",
        "ja": "やりたいことを入力...",
        "fr": "Décrivez ce que vous voulez faire...",
        "ru": "Опишите, что вы хотите сделать...",
        "de": "Beschreiben Sie, was Sie tun möchten...",
        "it": "Descrivi cosa vuoi fare...",
        "es": "Describa lo que quiere hacer...",
        "pt": "Descreva o que deseja fazer...",
        "ko": "원하는 작업을 설명하세요...",
    },
    "enter_command": {
        "zh": "输入命令...",
        "en": "Enter command...",
        "ja": "コマンドを入力...",
        "fr": "Entrer une commande...",
        "ru": "Введите команду...",
        "de": "Befehl eingeben...",
        "it": "Inserisci comando...",
        "es": "Ingrese comando...",
        "pt": "Digite o comando...",
        "ko": "명령어 입력...",
    },
    "ai_cleared": {
        "zh": "AI 助手已清空",
        "en": "AI assistant cleared",
        "ja": "AI アシスタントがクリアされました",
        "fr": "Assistant IA effacé",
        "ru": "AI помощник очищен",
        "de": "KI-Assistent gelöscht",
        "it": "Assistente IA cancellato",
        "es": "Asistente IA borrado",
        "pt": "Assistente IA limpo",
        "ko": "AI 어시스턴트 초기화됨",
    },
    "ai_intro": {
        "zh": "输入问题让我帮你生成命令、分析结果或解释错误。",
        "en": "Ask me to generate commands, analyze results, or explain errors.",
        "ja": "コマンドの生成、結果の分析、\nエラーの説明をお手伝いします。",
        "fr": "Demandez-moi de générer des commandes,\nd'analyser des résultats\nou d'expliquer des erreurs.",
        "ru": "Попросите меня сгенерировать команды,\nпроанализировать результаты\nили объяснить ошибки.",
        "de": "Bitten Sie mich, Befehle zu generieren,\nErgebnisse zu analysieren\noder Fehler zu erklären.",
        "it": "Chiedimi di generare comandi,\nanalizzare risultati o spiegare errori.",
        "es": "Pídale generar comandos,\nanalizar resultados o explicar errores.",
        "pt": "Peça para gerar comandos,\nanalisar resultados ou explicar erros.",
        "ko": "명령 생성, 결과 분석,\n오류 설명을 요청하세요.",
    },
    "terminal_ready": {
        "zh": "终端就绪",
        "en": "Terminal Ready",
        "ja": "ターミナル準備完了",
        "fr": "Terminal prêt",
        "ru": "Терминал готов",
        "de": "Terminal bereit",
        "it": "Terminale pronto",
        "es": "Terminal listo",
        "pt": "Terminal pronto",
        "ko": "터미널 준비됨",
    },
    "terminal_hint": {
        "zh": "输入命令或从 AI 助手拖拽。",
        "en": "Type commands or drag from AI assistant.",
        "ja": "コマンドを入力するか AI アシスタントからドラッグ。",
        "fr": "Tapez des commandes ou glissez depuis l'assistant IA.",
        "ru": "Введите команды или перетащите из AI-помощника.",
        "de": "Befehle eingeben oder vom KI-Assistenten ziehen.",
        "it": "Digita comandi o trascina dall'assistente IA.",
        "es": "Escriba comandos o arrastre desde el asistente IA.",
        "pt": "Digite comandos ou arraste do assistente IA.",
        "ko": "명령어를 입력하거나 AI 어시스턴트에서 드래그하세요.",
    },
    "kb_no_results_strict": {
        "zh": "严格模式下，知识库中未找到相关内容。请尝试其他问题或关闭严格模式。",
        "en": "No relevant information found in the knowledge base. Try a different question or disable strict mode.",
        "ja": "知識ベースに関連する情報が見つかりませんでした。別の質問を試すか、厳密モードを無効にしてください。",
        "fr": "Aucune information pertinente trouvée dans la base de connaissances. Essayez une autre question ou désactivez le mode strict.",
        "ru": "В базе знаний не найдено релевантной информации. Попробуйте другой вопрос или отключите строгий режим.",
        "de": "Keine relevanten Informationen in der Wissensdatenbank gefunden. Versuchen Sie eine andere Frage oder deaktivieren Sie den strengen Modus.",
        "it": "Nessuna informazione pertinente trovata nella base di conoscenza. Prova un'altra domanda o disabilita la modalità rigorosa.",
        "es": "No se encontró información relevante en la base de conocimiento. Intente otra pregunta o desactive el modo estricto.",
        "pt": "Nenhuma informação relevante encontrada na base de conhecimento. Tente outra pergunta ou desative o modo rigoroso.",
        "ko": "지식 베이스에서 관련 정보를 찾을 수 없습니다. 다른 질문을 시도하거나 엄격 모드를 비활성화하세요.",
    },
    "advanced_params": {
        "zh": "高级参数",
        "en": "Advanced Params",
        "ja": "詳細パラメータ",
        "fr": "Paramètres avancés",
        "ru": "Расширенные параметры",
        "de": "Erweiterte Parameter",
        "it": "Parametri avanzati",
        "es": "Parámetros avanzados",
        "pt": "Parâmetros avançados",
        "ko": "고급 매개변수",
    },
    "model_params": {
        "zh": "模型参数",
        "en": "Model Parameters",
        "ja": "モデルパラメータ",
        "fr": "Paramètres du modèle",
        "ru": "Параметры модели",
        "de": "Modellparameter",
        "it": "Parametri del modello",
        "es": "Parámetros del modelo",
        "pt": "Parâmetros do modelo",
        "ko": "모델 매개변수",
    },
    "temperature": {
        "zh": "温度",
        "en": "Temperature",
        "ja": "温度",
        "fr": "Température",
        "ru": "Температура",
        "de": "Temperatur",
        "it": "Temperatura",
        "es": "Temperatura",
        "pt": "Temperatura",
        "ko": "온도",
    },
    "max_tokens": {
        "zh": "最大输出 Tokens",
        "en": "Max Output Tokens",
        "ja": "最大出力トークン",
        "fr": "Tokens de sortie max",
        "ru": "Макс. токенов вывода",
        "de": "Max. Ausgabe-Token",
        "it": "Token di output massimi",
        "es": "Tokens de salida máx.",
        "pt": "Tokens de saída máx.",
        "ko": "최대 출력 토큰",
    },
    "rag_threshold": {
        "zh": "RAG 距离阈值",
        "en": "RAG Distance Threshold",
        "ja": "RAG 距離閾値",
        "fr": "Seuil de distance RAG",
        "ru": "Порог расстояния RAG",
        "de": "RAG-Distanzschwellenwert",
        "it": "Soglia distanza RAG",
        "es": "Umbral de distancia RAG",
        "pt": "Limiar de distância RAG",
        "ko": "RAG 거리 임계값",
    },
    "gallery": {
        "zh": "图集",
        "en": "Gallery",
        "ja": "ギャラリー",
        "fr": "Galerie",
        "ru": "Галерея",
        "de": "Galerie",
        "it": "Galleria",
        "es": "Galería",
        "pt": "Galeria",
        "ko": "갤러리",
    },
    "wiki": {
        "zh": "Wiki",
        "en": "Wiki",
        "ja": "Wiki",
        "fr": "Wiki",
        "ru": "Wiki",
        "de": "Wiki",
        "it": "Wiki",
        "es": "Wiki",
        "pt": "Wiki",
        "ko": "Wiki",
    },
    "image_gallery": {
        "zh": "图集",
        "en": "Gallery",
        "ja": "ギャラリー",
        "fr": "Galerie",
        "ru": "Галерея",
        "de": "Galerie",
        "it": "Galleria",
        "es": "Galería",
        "pt": "Galeria",
        "ko": "갤러리",
    },
    "select_kb_gallery": {
        "zh": "选择知识库",
        "en": "Select Knowledge Base",
        "ja": "知識ベースを選択",
        "fr": "Sélectionner la base de connaissances",
        "ru": "Выберите базу знаний",
        "de": "Wissensdatenbank auswählen",
        "it": "Seleziona base di conoscenza",
        "es": "Seleccionar base de conocimiento",
        "pt": "Selecionar base de conhecimento",
        "ko": "지식 베이스 선택",
    },
    "gallery_search_placeholder": {
        "zh": "搜索图片、上下文...",
        "en": "Search images, context...",
        "ja": "画像、コンテキストを検索...",
        "fr": "Rechercher des images, du contexte...",
        "ru": "Поиск изображений, контекста...",
        "de": "Bilder, Kontext suchen...",
        "it": "Cerca immagini, contesto...",
        "es": "Buscar imágenes, contexto...",
        "pt": "Pesquisar imagens, contexto...",
        "ko": "이미지, 컨텍스트 검색...",
    },
    "gallery_search_all": {
        "zh": "全文搜索",
        "en": "Full Text Search",
        "ja": "全文検索",
        "fr": "Recherche plein texte",
        "ru": "Полнотекстовый поиск",
        "de": "Volltextsuche",
        "it": "Ricerca testo completo",
        "es": "Búsqueda de texto completo",
        "pt": "Pesquisa de texto completo",
        "ko": "전체 텍스트 검색",
    },
    "gallery_search_context": {
        "zh": "上下文匹配",
        "en": "Context Match",
        "ja": "コンテキスト一致",
        "fr": "Correspondance de contexte",
        "ru": "Соответствие контексту",
        "de": "Kontextübereinstimmung",
        "it": "Corrispondenza contesto",
        "es": "Coincidencia de contexto",
        "pt": "Correspondência de contexto",
        "ko": "컨텍스트 일치",
    },
    "gallery_search_alt": {
        "zh": "Alt 文本",
        "en": "Alt Text",
        "ja": "代替テキスト",
        "fr": "Texte alternatif",
        "ru": "Альтернативный текст",
        "de": "Alternativtext",
        "it": "Testo alternativo",
        "es": "Texto alternativo",
        "pt": "Texto alternativo",
        "ko": "대체 텍스트",
    },
    "gallery_select_kb": {
        "zh": "请先选择一个知识库",
        "en": "Please select a knowledge base first",
        "ja": "最初に知識ベースを選択してください",
        "fr": "Veuillez d'abord sélectionner une base de connaissances",
        "ru": "Сначала выберите базу знаний",
        "de": "Bitte zuerst eine Wissensdatenbank auswählen",
        "it": "Seleziona prima una base di conoscenza",
        "es": "Seleccione primero una base de conocimiento",
        "pt": "Selecione primeiro uma base de conhecimento",
        "ko": "먼저 지식 베이스를 선택하세요",
    },
    "gallery_source_file": {
        "zh": "源文件：",
        "en": "Source File: ",
        "ja": "ソースファイル：",
        "fr": "Fichier source : ",
        "ru": "Исходный файл: ",
        "de": "Quelldatei: ",
        "it": "File sorgente: ",
        "es": "Archivo fuente: ",
        "pt": "Arquivo fonte: ",
        "ko": "소스 파일: ",
    },
    "gallery_filename": {
        "zh": "文件名：",
        "en": "Filename: ",
        "ja": "ファイル名：",
        "fr": "Nom du fichier : ",
        "ru": "Имя файла: ",
        "de": "Dateiname: ",
        "it": "Nome file: ",
        "es": "Nombre de archivo: ",
        "pt": "Nome do arquivo: ",
        "ko": "파일명: ",
    },
    "gallery_kb": {
        "zh": "知识库：",
        "en": "Knowledge Base: ",
        "ja": "知識ベース：",
        "fr": "Base de connaissances : ",
        "ru": "База знаний: ",
        "de": "Wissensdatenbank: ",
        "it": "Base di conoscenza: ",
        "es": "Base de conocimiento: ",
        "pt": "Base de conhecimento: ",
        "ko": "지식 베이스: ",
    },
    "search": {
        "zh": "搜索",
        "en": "Search",
        "ja": "検索",
        "fr": "Rechercher",
        "ru": "Поиск",
        "de": "Suche",
        "it": "Cerca",
        "es": "Buscar",
        "pt": "Pesquisar",
        "ko": "검색",
    },
    "browse": {
        "zh": "浏览",
        "en": "Browse",
        "ja": "閲覧",
        "fr": "Parcourir",
        "ru": "Просмотр",
        "de": "Durchsuchen",
        "it": "Sfoglia",
        "es": "Examinar",
        "pt": "Navegar",
        "ko": "찾아보기",
    },
    "question_generator": {
        "zh": "出题器",
        "en": "Question Generator",
        "ja": "問題作成",
        "fr": "Générateur de questions",
        "ru": "Генератор вопросов",
        "de": "Fragengenerator",
        "it": "Generatore di domande",
        "es": "Generador de preguntas",
        "pt": "Gerador de perguntas",
        "ko": "문제 생성기",
    },
    "guided_learning": {
        "zh": "引导学习",
        "en": "Guided Learning",
        "ja": "ガイド付き学習",
        "fr": "Apprentissage guidé",
        "ru": "Управляемое обучение",
        "de": "Geführtes Lernen",
        "it": "Apprendimento guidato",
        "es": "Aprendizaje guiado",
        "pt": "Aprendizado guiado",
        "ko": "가이드 학습",
    },
    "deep_research": {
        "zh": "深度研究",
        "en": "Deep Research",
        "ja": "詳細調査",
        "fr": "Recherche approfondie",
        "ru": "Глубокое исследование",
        "de": "Tiefenrecherche",
        "it": "Ricerca approfondita",
        "es": "Investigación profunda",
        "pt": "Pesquisa profunda",
        "ko": "심층 연구",
    },
    "lecture_maker": {
        "zh": "课件制作",
        "en": "Lecture Maker",
        "ja": "講義作成",
        "fr": "Créateur de cours",
        "ru": "Создатель лекций",
        "de": "Vortragsersteller",
        "it": "Creatore di lezioni",
        "es": "Creador de conferencias",
        "pt": "Criador de aulas",
        "ko": "강의 제작",
    },
    "exam_generator": {
        "zh": "试卷生成",
        "en": "Exam Generator",
        "ja": "試験作成",
        "fr": "Générateur d'examens",
        "ru": "Генератор экзаменов",
        "de": "Prüfungsgenerator",
        "it": "Generatore di esami",
        "es": "Generador de exámenes",
        "pt": "Gerador de exames",
        "ko": "시험 생성기",
    },
    "llm_assisted": {
        "zh": "LLM 增强生成",
        "en": "LLM Assisted",
        "ja": "LLM支援生成",
        "fr": "Génération assistée par LLM",
        "ru": "LLM-усиленная генерация",
        "de": "LLM-unterstützte Generierung",
        "it": "Generazione assistita da LLM",
        "es": "Generación asistida por LLM",
        "pt": "Geração assistida por LLM",
        "ko": "LLM 지원 생성",
    },
    "strict_kb_mode": {
        "zh": "严格知识库模式",
        "en": "Strict KB Mode",
        "ja": "厳密なKBモード",
        "fr": "Mode KB strict",
        "ru": "Строгий режим БЗ",
        "de": "Strenger WB-Modus",
        "it": "Modalità KB rigorosa",
        "es": "Modo BC estricto",
        "pt": "Modo BC rigoroso",
        "ko": "엄격 KB 모드",
    },
    "strict_kb_mode_desc": {
        "zh": "仅允许从知识库中回答，找不到相关内容时拒绝回答",
        "en": "Only answer from knowledge base, refuse if no relevant content found",
        "ja": "ナレッジベースからのみ回答、関連コンテンツが見つからない場合は拒否",
        "fr": "Répondre uniquement depuis la base de connaissances, refuser si aucun contenu pertinent trouvé",
        "ru": "Отвечать только из базы знаний, отказать если не найдено релевантного содержимого",
        "de": "Nur aus Wissensdatenbank antworten, ablehnen wenn keine relevanten Inhalte gefunden",
        "it": "Rispondi solo dalla base di conoscenza, rifiuta se non viene trovato contenuto pertinente",
        "es": "Responder solo desde la base de conocimiento, rechazar si no se encuentra contenido relevante",
        "pt": "Responder apenas da base de conhecimento, recusar se nenhum conteúdo relevante for encontrado",
        "ko": "지식 베이스에서만 답변, 관련 내용을 찾을 수 없으면 거부",
    },
    "lit_review": {
        "zh": "文献综述",
        "en": "Literature Review",
        "ja": "文献レビュー",
        "fr": "Revue de littérature",
        "ru": "Обзор литературы",
        "de": "Literaturübersicht",
        "it": "Revisione della letteratura",
        "es": "Revisión de literatura",
        "pt": "Revisão de literatura",
        "ko": "문헌 검토",
    },
    "lit_review_desc": {
        "zh": "基于知识库生成文献综述",
        "en": "Generate a literature review from the knowledge base",
        "ja": "ナレッジベースから文献レビューを生成",
        "fr": "Générer une revue de littérature depuis la base de connaissances",
        "ru": "Создать обзор литературы из базы знаний",
        "de": "Literaturübersicht aus der Wissensdatenbank generieren",
        "it": "Genera una revisione della letteratura dalla base di conoscenza",
        "es": "Generar una revisión de literatura desde la base de conocimiento",
        "pt": "Gerar uma revisão de literatura da base de conhecimento",
        "ko": "지식 베이스에서 문헌 검토 생성",
    },
    "use_images": {
        "zh": "包含图片",
        "en": "Include Images",
        "ja": "画像を含む",
        "fr": "Inclure des images",
        "ru": "Включить изображения",
        "de": "Bilder einbeziehen",
        "it": "Includi immagini",
        "es": "Incluir imágenes",
        "pt": "Incluir imagens",
        "ko": "이미지 포함",
    },
    "generating_lit_review": {
        "zh": "正在生成文献综述...",
        "en": "Generating literature review...",
        "ja": "文献レビューを生成中...",
        "fr": "Génération de la revue de littérature...",
        "ru": "Генерация обзора литературы...",
        "de": "Literaturübersicht wird generiert...",
        "it": "Generazione revisione della letteratura...",
        "es": "Generando revisión de literatura...",
        "pt": "Gerando revisão de literatura...",
        "ko": "문헌 검토 생성 중...",
    },
    "generate_lit_review": {
        "zh": "生成文献综述",
        "en": "Generate Literature Review",
        "ja": "文献レビューを生成",
        "fr": "Générer une revue de littérature",
        "ru": "Создать обзор литературы",
        "de": "Literaturübersicht generieren",
        "it": "Genera revisione della letteratura",
        "es": "Generar revisión de literatura",
        "pt": "Gerar revisão de literatura",
        "ko": "문헌 검토 생성",
    },
    "paper_writer": {
        "zh": "撰写论文",
        "en": "Write Paper",
        "ja": "論文執筆",
        "fr": "Rédiger un article",
        "ru": "Написать статью",
        "de": "Papier schreiben",
        "it": "Scrivi articolo",
        "es": "Escribir artículo",
        "pt": "Escrever artigo",
        "ko": "논문 작성",
    },
    "paper_writer_desc": {
        "zh": "基于选定知识库撰写完整学术论文",
        "en": "Write a complete academic paper from selected knowledge bases",
        "ja": "選択した知識ベースから完全な学術論文を執筆",
        "fr": "Rédiger un article académique complet à partir des bases de connaissances sélectionnées",
        "ru": "Написать полную академическую статью на основе выбранных баз знаний",
        "de": "Vollständigen wissenschaftlichen Artikel aus ausgewählten Wissensdatenbanken schreiben",
        "it": "Scrivi un articolo accademico completo dalle basi di conoscenza selezionate",
        "es": "Escribir un artículo académico completo desde las bases de conocimiento seleccionadas",
        "pt": "Escrever um artigo acadêmico completo das bases de conhecimento selecionadas",
        "ko": "선택한 지식 베이스에서 완전한 학술 논문 작성",
    },
    "generating_paper": {
        "zh": "正在撰写论文...",
        "en": "Writing paper...",
        "ja": "論文を執筆中...",
        "fr": "Rédaction de l'article...",
        "ru": "Написание статьи...",
        "de": "Papier wird geschrieben...",
        "it": "Scrittura dell'articolo...",
        "es": "Escribiendo artículo...",
        "pt": "Escrevendo artigo...",
        "ko": "논문 작성 중...",
    },
    "paper_title": {
        "zh": "论文题目",
        "en": "Paper Title",
        "ja": "論文題目",
        "fr": "Titre de l'article",
        "ru": "Название статьи",
        "de": "Papiertitel",
        "it": "Titolo dell'articolo",
        "es": "Título del artículo",
        "pt": "Título do artigo",
        "ko": "논문 제목",
    },
    "paper_abstract": {
        "zh": "摘要",
        "en": "Abstract",
        "ja": "要約",
        "fr": "Résumé",
        "ru": "Аннотация",
        "de": "Zusammenfassung",
        "it": "Sommario",
        "es": "Resumen",
        "pt": "Resumo",
        "ko": "초록",
    },
    "paper_introduction": {
        "zh": "引言",
        "en": "Introduction",
        "ja": "序論",
        "fr": "Introduction",
        "ru": "Введение",
        "de": "Einleitung",
        "it": "Introduzione",
        "es": "Introducción",
        "pt": "Introdução",
        "ko": "서론",
    },
    "paper_related_work": {
        "zh": "相关工作",
        "en": "Related Work",
        "ja": "関連研究",
        "fr": "Travaux connexes",
        "ru": "Связанная работа",
        "de": "Verwandte Arbeit",
        "it": "Lavori correlati",
        "es": "Trabajo relacionado",
        "pt": "Trabalho relacionado",
        "ko": "관련 연구",
    },
    "paper_method": {
        "zh": "方法",
        "en": "Method",
        "ja": "手法",
        "fr": "Méthode",
        "ru": "Метод",
        "de": "Methode",
        "it": "Metodo",
        "es": "Método",
        "pt": "Método",
        "ko": "방법",
    },
    "paper_experiments": {
        "zh": "实验",
        "en": "Experiments",
        "ja": "実験",
        "fr": "Expériences",
        "ru": "Эксперименты",
        "de": "Experimente",
        "it": "Esperimenti",
        "es": "Experimentos",
        "pt": "Experimentos",
        "ko": "실험",
    },
    "paper_discussion": {
        "zh": "讨论",
        "en": "Discussion",
        "ja": "考察",
        "fr": "Discussion",
        "ru": "Обсуждение",
        "de": "Diskussion",
        "it": "Discussione",
        "es": "Discusión",
        "pt": "Discussão",
        "ko": "토론",
    },
    "paper_conclusion": {
        "zh": "结论",
        "en": "Conclusion",
        "ja": "結論",
        "fr": "Conclusion",
        "ru": "Заключение",
        "de": "Fazit",
        "it": "Conclusione",
        "es": "Conclusión",
        "pt": "Conclusão",
        "ko": "결론",
    },
    "paper_references": {
        "zh": "参考文献",
        "en": "References",
        "ja": "参考文献",
        "fr": "Références",
        "ru": "Ссылки",
        "de": "Referenzen",
        "it": "Riferimenti",
        "es": "Referencias",
        "pt": "Referências",
        "ko": "참고문헌",
    },
    "wiki_select_kb": {
        "zh": "选择知识库",
        "en": "Select Knowledge Base",
        "ja": "知識ベースを選択",
        "fr": "Sélectionner la base de connaissances",
        "ru": "Выберите базу знаний",
        "de": "Wissensdatenbank auswählen",
        "it": "Seleziona base di conoscenza",
        "es": "Seleccionar base de conocimiento",
        "pt": "Selecionar base de conhecimento",
        "ko": "지식 베이스 선택",
    },
    "wiki_generate": {
        "zh": "生成 Wiki",
        "en": "Generate Wiki",
        "ja": "Wiki を生成",
        "fr": "Générer Wiki",
        "ru": "Создать Wiki",
        "de": "Wiki generieren",
        "it": "Genera Wiki",
        "es": "Generar Wiki",
        "pt": "Gerar Wiki",
        "ko": "Wiki 생성",
    },
    "wiki_cross_kb_label": {
        "zh": "跨库 Wiki（多选）",
        "en": "Cross-KB Wiki (multi-select)",
        "ja": "クロスKB Wiki（複数選択）",
        "fr": "Wiki inter-bases (multi-sélection)",
        "ru": "Кросс-KB Wiki (мульти-выбор)",
        "de": "Cross-KB Wiki (Mehrfachauswahl)",
        "it": "Wiki cross-KB (multi-selezione)",
        "es": "Wiki cross-KB (multi-selección)",
        "pt": "Wiki cross-KB (multi-seleção)",
        "ko": "크로스-KB Wiki (다중 선택)",
    },
    "wiki_generate_cross": {
        "zh": "生成跨库 Wiki",
        "en": "Generate Cross-KB Wiki",
        "ja": "クロスKB Wiki を生成",
        "fr": "Générer Wiki inter-bases",
        "ru": "Создать кросс-KB Wiki",
        "de": "Cross-KB Wiki generieren",
        "it": "Genera Wiki cross-KB",
        "es": "Generar Wiki cross-KB",
        "pt": "Gerar Wiki cross-KB",
        "ko": "크로스-KB Wiki 생성",
    },
    "wiki_empty_select": {
        "zh": "选择知识库并生成 Wiki",
        "en": "Select a KB and generate Wiki",
        "ja": "KB を選択して Wiki を生成",
        "fr": "Sélectionnez une base et générez le Wiki",
        "ru": "Выберите KB и создайте Wiki",
        "de": "KB auswählen und Wiki generieren",
        "it": "Seleziona un KB e genera Wiki",
        "es": "Selecciona un KB y genera Wiki",
        "pt": "Selecione um KB e gere Wiki",
        "ko": "KB 선택 후 Wiki 생성",
    },
    "wiki_welcome_title": {
        "zh": "知识库 Wiki",
        "en": "Knowledge Base Wiki",
        "ja": "知識ベース Wiki",
        "fr": "Wiki de la base de connaissances",
        "ru": "Wiki базы знаний",
        "de": "Wissensdatenbank Wiki",
        "it": "Wiki base di conoscenza",
        "es": "Wiki de base de conocimiento",
        "pt": "Wiki da base de conhecimento",
        "ko": "지식 베이스 Wiki",
    },
    "wiki_welcome_desc_1": {
        "zh": "从左侧选择知识库，点击\u201c生成 Wiki\u201d按钮即可自动生成。",
        "en": "Select a knowledge base from the left and click \"Generate Wiki\" to auto-generate.",
        "ja": "左から知識ベースを選択し、「Wiki を生成」をクリックして自動生成。",
        "fr": "Sélectionnez une base à gauche et cliquez sur \"Générer Wiki\" pour auto-générer.",
        "ru": "Выберите базу знаний слева и нажмите \"Создать Wiki\" для автогенерации.",
        "de": "Wählen Sie links eine KB und klicken Sie auf \"Wiki generieren\".",
        "it": "Seleziona un KB a sinistra e clicca \"Genera Wiki\" per auto-generare.",
        "es": "Selecciona un KB a la izquierda y haz clic en \"Generar Wiki\".",
        "pt": "Selecione um KB à esquerda e clique em \"Gerar Wiki\".",
        "ko": "왼쪽에서 지식 베이스를 선택하고 \"Wiki 생성\"을 클릭하세요.",
    },
    "wiki_welcome_desc_2": {
        "zh": "Wiki 会自动提取文档中的关键概念，并建立内部链接。",
        "en": "Wiki automatically extracts key concepts from documents and creates internal links.",
        "ja": "Wiki はドキュメントから主要概念を自動抽出し、内部リンクを作成します。",
        "fr": "Le Wiki extrait automatiquement les concepts clés et crée des liens internes.",
        "ru": "Wiki автоматически извлекает ключевые концепции и создаёт внутренние ссылки.",
        "de": "Wiki extrahiert automatisch Schlüsselkonzepte und erstellt interne Links.",
        "it": "Wiki estrae automaticamente i concetti chiave e crea collegamenti interni.",
        "es": "Wiki extrae automáticamente conceptos clave y crea enlaces internos.",
        "pt": "Wiki extrai automaticamente conceitos-chave e cria links internos.",
        "ko": "Wiki 는 문서에서 주요 개념을 자동으로 추출하고 내부 링크를 생성합니다.",
    },
    "wiki_cross_title": {
        "zh": "跨库 Wiki",
        "en": "Cross-KB Wiki",
        "ja": "クロスKB Wiki",
        "fr": "Wiki inter-bases",
        "ru": "Кросс-KB Wiki",
        "de": "Cross-KB Wiki",
        "it": "Wiki cross-KB",
        "es": "Wiki cross-KB",
        "pt": "Wiki cross-KB",
        "ko": "크로스-KB Wiki",
    },
    "wiki_cross_desc_1": {
        "zh": "勾选多个知识库，点击\u201c生成跨库 Wiki\u201d可创建统一的概念视图。",
        "en": "Check multiple knowledge bases and click \"Generate Cross-KB Wiki\" to create a unified concept view.",
        "ja": "複数の KB をチェックし、「クロスKB Wiki を生成」をクリックして統一概念ビューを作成。",
        "fr": "Cochez plusieurs bases et cliquez sur \"Générer Wiki inter-bases\" pour une vue unifiée.",
        "ru": "Отметьте несколько KB и нажмите \"Создать кросс-KB Wiki\" для единого обзора.",
        "de": "Wählen Sie mehrere KBs und klicken Sie auf \"Cross-KB Wiki generieren\".",
        "it": "Seleziona più KB e clicca \"Genera Wiki cross-KB\" per una vista unificata.",
        "es": "Marca múltiples KBs y haz clic en \"Generar Wiki cross-KB\".",
        "pt": "Marque múltiplos KBs e clique em \"Gerar Wiki cross-KB\".",
        "ko": "여러 KB 를 선택하고 \"크로스-KB Wiki 생성\"을 클릭하세요.",
    },
    "wiki_cross_desc_2": {
        "zh": "跨库概念会标注来自哪些知识库，方便对比学习。",
        "en": "Cross-KB concepts are labeled with their source KBs for easy comparison.",
        "ja": "クロスKB 概念は出典 KB が表示され、比較学習に便利です。",
        "fr": "Les concepts inter-bases sont étiquetés avec leurs sources pour faciliter la comparaison.",
        "ru": "Кросс-KB концепции помечены источниками для удобного сравнения.",
        "de": "Cross-KB Konzepte sind mit ihren Quellen gekennzeichnet.",
        "it": "I concetti cross-KB sono etichettati con le origini per facilitare il confronto.",
        "es": "Los conceptos cross-KB están etiquetados con sus orígenes.",
        "pt": "Conceitos cross-KB são rotulados com suas origens.",
        "ko": "크로스-KB 개념은 출처 KB 가 표시되어 비교 학습에便利です.",
    },
    "wiki_loading": {
        "zh": "加载中...",
        "en": "Loading...",
        "ja": "読み込み中...",
        "fr": "Chargement...",
        "ru": "Загрузка...",
        "de": "Laden...",
        "it": "Caricamento...",
        "es": "Cargando...",
        "pt": "Carregando...",
        "ko": "로딩 중...",
    },
    "wiki_no_pages": {
        "zh": "暂无 Wiki 页面，点击\u201c生成 Wiki\u201d创建",
        "en": "No Wiki pages yet. Click \"Generate Wiki\" to create.",
        "ja": "Wiki ページがありません。「Wiki を生成」をクリックして作成。",
        "fr": "Pas encore de pages Wiki. Cliquez sur \"Générer Wiki\" pour créer.",
        "ru": "Нет страниц Wiki. Нажмите \"Создать Wiki\" для создания.",
        "de": "Noch keine Wiki-Seiten. Klicken Sie auf \"Wiki generieren\".",
        "it": "Nessuna pagina Wiki. Clicca \"Genera Wiki\" per creare.",
        "es": "Aún no hay páginas Wiki. Haz clic en \"Generar Wiki\".",
        "pt": "Nenhuma página Wiki ainda. Clique em \"Gerar Wiki\".",
        "ko": "Wiki 페이지가 없습니다. \"Wiki 생성\"을 클릭하세요.",
    },
    "wiki_pages_need_update": {
        "zh": "个页面需要更新",
        "en": "pages need updating",
        "ja": "ページの更新が必要",
        "fr": "pages nécessitent une mise à jour",
        "ru": "страниц требуют обновления",
        "de": "Seiten benötigen Aktualisierung",
        "it": "pagine necessitano aggiornamento",
        "es": "páginas necesitan actualización",
        "pt": "páginas precisam de atualização",
        "ko": "개 페이지 업데이트 필요",
    },
    "wiki_incremental_update": {
        "zh": "增量更新",
        "en": "Incremental Update",
        "ja": "差分更新",
        "fr": "Mise à jour incrémentale",
        "ru": "Инкрементальное обновление",
        "de": "Inkrementelles Update",
        "it": "Aggiornamento incrementale",
        "es": "Actualización incremental",
        "pt": "Atualização incremental",
        "ko": "증분 업데이트",
    },
    "wiki_up_to_date": {
        "zh": "已是最新",
        "en": "Up to date",
        "ja": "最新状態",
        "fr": "À jour",
        "ru": "Обновлено",
        "de": "Aktuell",
        "it": "Aggiornato",
        "es": "Actualizado",
        "pt": "Atualizado",
        "ko": "최신 상태",
    },
    "wiki_cat_index": {
        "zh": "索引",
        "en": "Index",
        "ja": "索引",
        "fr": "Index",
        "ru": "Индекс",
        "de": "Index",
        "it": "Indice",
        "es": "Índice",
        "pt": "Índice",
        "ko": "색인",
    },
    "wiki_cat_concept": {
        "zh": "概念",
        "en": "Concept",
        "ja": "概念",
        "fr": "Concept",
        "ru": "Концепция",
        "de": "Konzept",
        "it": "Concetto",
        "es": "Concepto",
        "pt": "Conceito",
        "ko": "개념",
    },
    "wiki_cat_entity": {
        "zh": "实体",
        "en": "Entity",
        "ja": "エンティティ",
        "fr": "Entité",
        "ru": "Сущность",
        "de": "Entität",
        "it": "Entità",
        "es": "Entidad",
        "pt": "Entidade",
        "ko": "엔티티",
    },
    "wiki_cat_other": {
        "zh": "其他",
        "en": "Other",
        "ja": "その他",
        "fr": "Autre",
        "ru": "Другое",
        "de": "Sonstige",
        "it": "Altro",
        "es": "Otro",
        "pt": "Outro",
        "ko": "기타",
    },
    "wiki_load_failed": {
        "zh": "加载失败: ",
        "en": "Load failed: ",
        "ja": "読み込み失敗: ",
        "fr": "Échec du chargement: ",
        "ru": "Ошибка загрузки: ",
        "de": "Laden fehlgeschlagen: ",
        "it": "Caricamento fallito: ",
        "es": "Error al cargar: ",
        "pt": "Falha ao carregar: ",
        "ko": "로딩 실패: ",
    },
    "wiki_page_not_found": {
        "zh": "页面不存在",
        "en": "Page not found",
        "ja": "ページが見つかりません",
        "fr": "Page introuvable",
        "ru": "Страница не найдена",
        "de": "Seite nicht gefunden",
        "it": "Pagina non trovata",
        "es": "Página no encontrada",
        "pt": "Página não encontrada",
        "ko": "페이지를 찾을 수 없습니다",
    },
    "wiki_no_cross_pages": {
        "zh": "暂无跨库 Wiki 页面，点击\u201c生成跨库 Wiki\u201d创建",
        "en": "No cross-KB Wiki pages. Click \"Generate Cross-KB Wiki\" to create.",
        "ja": "クロスKB Wiki ページがありません。「クロスKB Wiki を生成」をクリック。",
        "fr": "Pas de pages Wiki inter-bases. Cliquez sur \"Générer Wiki inter-bases\".",
        "ru": "Нет кросс-KB Wiki страниц. Нажмите \"Создать кросс-KB Wiki\".",
        "de": "Keine Cross-KB Wiki-Seiten. Klicken Sie auf \"Cross-KB Wiki generieren\".",
        "it": "Nessuna pagina Wiki cross-KB. Clicca \"Genera Wiki cross-KB\".",
        "es": "No hay páginas Wiki cross-KB. Haz clic en \"Generar Wiki cross-KB\".",
        "pt": "Nenhuma página Wiki cross-KB. Clique em \"Gerar Wiki cross-KB\".",
        "ko": "크로스-KB Wiki 페이지가 없습니다. \"크로스-KB Wiki 생성\"을 클릭하세요.",
    },
    "wiki_cross_header": {
        "zh": "跨库 Wiki",
        "en": "Cross-KB Wiki",
        "ja": "クロスKB Wiki",
        "fr": "Wiki inter-bases",
        "ru": "Кросс-KB Wiki",
        "de": "Cross-KB Wiki",
        "it": "Wiki cross-KB",
        "es": "Wiki cross-KB",
        "pt": "Wiki cross-KB",
        "ko": "크로스-KB Wiki",
    },
    "wiki_cross_kb_unit": {
        "zh": "库",
        "en": "KB",
        "ja": "KB",
        "fr": "Base",
        "ru": "KB",
        "de": "KB",
        "it": "KB",
        "es": "KB",
        "pt": "KB",
        "ko": "KB",
    },
    "wiki_please_select_kb": {
        "zh": "请先选择知识库",
        "en": "Please select a knowledge base first",
        "ja": "まず知識ベースを選択してください",
        "fr": "Veuillez d'abord sélectionner une base de connaissances",
        "ru": "Сначала выберите базу знаний",
        "de": "Bitte zuerst eine Wissensdatenbank auswählen",
        "it": "Seleziona prima una base di conoscenza",
        "es": "Primero selecciona una base de conocimiento",
        "pt": "Selecione primeiro uma base de conhecimento",
        "ko": "먼저 지식 베이스를 선택하세요",
    },
    "wiki_generating": {
        "zh": "生成中...",
        "en": "Generating...",
        "ja": "生成中...",
        "fr": "Génération...",
        "ru": "Генерация...",
        "de": "Generieren...",
        "it": "Generazione...",
        "es": "Generando...",
        "pt": "Gerando...",
        "ko": "생성 중...",
    },
    "wiki_building_status": {
        "zh": "正在生成 Wiki",
        "en": "Generating Wiki",
        "ja": "Wiki 生成中",
        "fr": "Génération du Wiki",
        "ru": "Создание Wiki",
        "de": "Wiki wird generiert",
        "it": "Generazione Wiki",
        "es": "Generando Wiki",
        "pt": "Gerando Wiki",
        "ko": "Wiki 생성 중",
    },
    "wiki_llm_enhanced": {
        "zh": "(LLM 增强)",
        "en": "(LLM Enhanced)",
        "ja": "(LLM 強化)",
        "fr": "(Amélioré par LLM)",
        "ru": "(Улучшено LLM)",
        "de": "(LLM-verbessert)",
        "it": "(Migliorato da LLM)",
        "es": "(Mejorado por LLM)",
        "pt": "(Aprimorado por LLM)",
        "ko": "(LLM 강화)",
    },
    "wiki_may_take_minutes": {
        "zh": "，这可能需要几分钟...",
        "en": ", this may take a few minutes...",
        "ja": "、数分かかる場合があります...",
        "fr": ", cela peut prendre quelques minutes...",
        "ru": ", это может занять несколько минут...",
        "de": ", dies kann einige Minuten dauern...",
        "it": ", potrebbe richiedere alcuni minuti...",
        "es": ", esto puede tardar unos minutos...",
        "pt": ", isso pode levar alguns minutos...",
        "ko": ", 몇 분 정도 소요될 수 있습니다...",
    },
    "wiki_generation_complete": {
        "zh": "生成完成！",
        "en": "Generation complete!",
        "ja": "生成完了！",
        "fr": "Génération terminée !",
        "ru": "Генерация завершена!",
        "de": "Generierung abgeschlossen!",
        "it": "Generazione completata!",
        "es": "¡Generación completada!",
        "pt": "Geração concluída!",
        "ko": "생성 완료!",
    },
    "wiki_pages_count": {
        "zh": "个页面",
        "en": "pages",
        "ja": "ページ",
        "fr": "pages",
        "ru": "страниц",
        "de": "Seiten",
        "it": "pagine",
        "es": "páginas",
        "pt": "páginas",
        "ko": "개 페이지",
    },
    "wiki_keywords_count": {
        "zh": "个关键词",
        "en": "keywords",
        "ja": "キーワード",
        "fr": "mots-clés",
        "ru": "ключевых слов",
        "de": "Schlüsselwörter",
        "it": "parole chiave",
        "es": "palabras clave",
        "pt": "palavras-chave",
        "ko": "개 키워드",
    },
    "wiki_links_count": {
        "zh": "个内部链接",
        "en": "internal links",
        "ja": "内部リンク",
        "fr": "liens internes",
        "ru": "внутренних ссылок",
        "de": "interne Links",
        "it": "collegamenti interni",
        "es": "enlaces internos",
        "pt": "links internos",
        "ko": "개 내부 링크",
    },
    "wiki_updated_count": {
        "zh": "，更新",
        "en": ", updated",
        "ja": "、更新",
        "fr": ", mis à jour",
        "ru": ", обновлено",
        "de": ", aktualisiert",
        "it": ", aggiornato",
        "es": ", actualizado",
        "pt": ", atualizado",
        "ko": ", 업데이트",
    },
    "wiki_skipped_count": {
        "zh": "页，跳过",
        "en": "pages, skipped",
        "ja": "ページ、スキップ",
        "fr": "pages, ignorées",
        "ru": "страниц, пропущено",
        "de": "Seiten, übersprungen",
        "it": "pagine, saltate",
        "es": "páginas, omitidas",
        "pt": "páginas, ignoradas",
        "ko": "페이지, 건너뜀",
    },
    "wiki_generation_failed": {
        "zh": "生成失败: ",
        "en": "Generation failed: ",
        "ja": "生成失敗: ",
        "fr": "Échec de la génération: ",
        "ru": "Ошибка генерации: ",
        "de": "Generierung fehlgeschlagen: ",
        "it": "Generazione fallita: ",
        "es": "Error de generación: ",
        "pt": "Falha na geração: ",
        "ko": "생성 실패: ",
    },
    "wiki_select_at_least_2": {
        "zh": "请至少选择 2 个知识库",
        "en": "Please select at least 2 knowledge bases",
        "ja": "少なくとも 2 つの知識ベースを選択してください",
        "fr": "Veuillez sélectionner au moins 2 bases de connaissances",
        "ru": "Выберите как минимум 2 базы знаний",
        "de": "Bitte mindestens 2 Wissensdatenbanken auswählen",
        "it": "Seleziona almeno 2 basi di conoscenza",
        "es": "Selecciona al menos 2 bases de conocimiento",
        "pt": "Selecione pelo menos 2 bases de conhecimento",
        "ko": "최소 2 개의 지식 베이스를 선택하세요",
    },
    "wiki_building_cross": {
        "zh": "正在生成跨库 Wiki...",
        "en": "Generating cross-KB Wiki...",
        "ja": "クロスKB Wiki 生成中...",
        "fr": "Génération du Wiki inter-bases...",
        "ru": "Создание кросс-KB Wiki...",
        "de": "Cross-KB Wiki wird generiert...",
        "it": "Generazione Wiki cross-KB...",
        "es": "Generando Wiki cross-KB...",
        "pt": "Gerando Wiki cross-KB...",
        "ko": "크로스-KB Wiki 생성 중...",
    },
    "wiki_cross_complete": {
        "zh": "跨库 Wiki 生成完成！",
        "en": "Cross-KB Wiki generation complete!",
        "ja": "クロスKB Wiki 生成完了！",
        "fr": "Génération du Wiki inter-bases terminée !",
        "ru": "Создание кросс-KB Wiki завершено!",
        "de": "Cross-KB Wiki Generierung abgeschlossen!",
        "it": "Generazione Wiki cross-KB completata!",
        "es": "¡Generación Wiki cross-KB completada!",
        "pt": "Geração Wiki cross-KB concluída!",
        "ko": "크로스-KB Wiki 생성 완료!",
    },
    "wiki_kbs_count": {
        "zh": "个知识库",
        "en": "knowledge bases",
        "ja": "知識ベース",
        "fr": "bases de connaissances",
        "ru": "баз знаний",
        "de": "Wissensdatenbanken",
        "it": "basi di conoscenza",
        "es": "bases de conocimiento",
        "pt": "bases de conhecimento",
        "ko": "개 지식 베이스",
    },
    "wiki_updating_affected": {
        "zh": "正在更新受影响的页面...",
        "en": "Updating affected pages...",
        "ja": "影響を受けたページを更新中...",
        "fr": "Mise à jour des pages affectées...",
        "ru": "Обновление затронутых страниц...",
        "de": "Betroffene Seiten werden aktualisiert...",
        "it": "Aggiornamento pagine interessate...",
        "es": "Actualizando páginas afectadas...",
        "pt": "Atualizando páginas afetadas...",
        "ko": "영향 받은 페이지 업데이트 중...",
    },
    "wiki_incremental_complete": {
        "zh": "增量更新完成！更新",
        "en": "Incremental update complete! Updated",
        "ja": "差分更新完了！更新",
        "fr": "Mise à jour incrémentale terminée ! Mis à jour",
        "ru": "Инкрементальное обновление завершено! Обновлено",
        "de": "Inkrementelles Update abgeschlossen! Aktualisiert",
        "it": "Aggiornamento incrementale completato! Aggiornate",
        "es": "¡Actualización incremental completada! Actualizado",
        "pt": "Atualização incremental concluída! Atualizado",
        "ko": "증분 업데이트 완료! 업데이트",
    },
    "wiki_update_failed": {
        "zh": "更新失败: ",
        "en": "Update failed: ",
        "ja": "更新失敗: ",
        "fr": "Échec de la mise à jour: ",
        "ru": "Ошибка обновления: ",
        "de": "Update fehlgeschlagen: ",
        "it": "Aggiornamento fallito: ",
        "es": "Error de actualización: ",
        "pt": "Falha na atualização: ",
        "ko": "업데이트 실패: ",
    },
    "wiki_regenerating": {
        "zh": "正在重新生成",
        "en": "Regenerating",
        "ja": "再生成中",
        "fr": "Régénération",
        "ru": "Повторная генерация",
        "de": "Neu generieren",
        "it": "Rigenerazione",
        "es": "Regenerando",
        "pt": "Regenerando",
        "ko": "재생성 중",
    },
    "wiki_regeneration_complete": {
        "zh": "重新生成完成！更新",
        "en": "Regeneration complete! Updated",
        "ja": "再生成完了！更新",
        "fr": "Régénération terminée ! Mis à jour",
        "ru": "Повторная генерация завершена! Обновлено",
        "de": "Neu generierung abgeschlossen! Aktualisiert",
        "it": "Rigenerazione completata! Aggiornate",
        "es": "¡Regeneración completada! Actualizado",
        "pt": "Regeneração concluída! Atualizado",
        "ko": "재생성 완료! 업데이트",
    },
    "wiki_not_found_count": {
        "zh": "，未找到",
        "en": ", not found",
        "ja": "、見つかりません",
        "fr": ", introuvable",
        "ru": ", не найдено",
        "de": ", nicht gefunden",
        "it": ", non trovate",
        "es": ", no encontrado",
        "pt": ", não encontrado",
        "ko": ", 찾을 수 없음",
    },
    "wiki_regeneration_failed": {
        "zh": "重新生成失败: ",
        "en": "Regeneration failed: ",
        "ja": "再生成失敗: ",
        "fr": "Échec de la régénération: ",
        "ru": "Ошибка повторной генерации: ",
        "de": "Neu generierung fehlgeschlagen: ",
        "it": "Rigenerazione fallita: ",
        "es": "Error de regeneración: ",
        "pt": "Falha na regeneração: ",
        "ko": "재생성 실패: ",
    },
    "wiki_page_suffix": {
        "zh": "页",
        "en": "pages",
        "ja": "ページ",
        "fr": "pages",
        "ru": "страниц",
        "de": "Seiten",
        "it": "pagine",
        "es": "páginas",
        "pt": "páginas",
        "ko": "페이지",
    },
    "llm_assisted": {
        "zh": "LLM 增强生成",
        "en": "LLM Assisted Generation",
        "ja": "LLM 支援生成",
        "fr": "Génération assistée par LLM",
        "ru": "Генерация с помощью LLM",
        "de": "LLM-gestützte Generierung",
        "it": "Generazione assistita da LLM",
        "es": "Generación asistida por LLM",
        "pt": "Geração assistida por LLM",
        "ko": "LLM 지원 생성",
    },
    # Paper Search & Library
    "paper_library": {
        "zh": "论文库",
        "en": "Paper Library",
        "ja": "論文ライブラリ",
        "fr": "Bibliothèque de articles",
        "ru": "Библиотека статей",
        "de": "Paper-Bibliothek",
        "it": "Libreria articoli",
        "es": "Biblioteca de artículos",
        "pt": "Biblioteca de artigos",
        "ko": "논문 라이브러리",
    },
    "paper_search": {
        "zh": "论文搜索",
        "en": "Paper Search",
        "ja": "論文検索",
        "fr": "Recherche d'articles",
        "ru": "Поиск статей",
        "de": "Paper-Suche",
        "it": "Ricerca articoli",
        "es": "Búsqueda de artículos",
        "pt": "Pesquisa de artigos",
        "ko": "논문 검색",
    },
    "search_query": {
        "zh": "搜索查询",
        "en": "Search Query",
        "ja": "検索クエリ",
        "fr": "Requête de recherche",
        "ru": "Поисковый запрос",
        "de": "Suchanfrage",
        "it": "Query di ricerca",
        "es": "Consulta de búsqueda",
        "pt": "Consulta de pesquisa",
        "ko": "검색 쿼리",
    },
    "search_query_placeholder": {
        "zh": "例如：transformer attention mechanism",
        "en": "e.g., transformer attention mechanism",
        "ja": "例：transformer attention mechanism",
        "fr": "ex. : transformer attention mechanism",
        "ru": "напр., transformer attention mechanism",
        "de": "z.B. transformer attention mechanism",
        "it": "es. transformer attention mechanism",
        "es": "ej. transformer attention mechanism",
        "pt": "ex. transformer attention mechanism",
        "ko": "예: transformer attention mechanism",
    },
    "search_sources": {
        "zh": "搜索来源",
        "en": "Search Sources",
        "ja": "検索ソース",
        "fr": "Sources de recherche",
        "ru": "Источники поиска",
        "de": "Suchquellen",
        "it": "Fonti di ricerca",
        "es": "Fuentes de búsqueda",
        "pt": "Fontes de pesquisa",
        "ko": "검색 소스",
    },
    "max_results": {
        "zh": "最大结果数",
        "en": "Max Results",
        "ja": "最大結果数",
        "fr": "Résultats max",
        "ru": "Макс. результатов",
        "de": "Max Ergebnisse",
        "it": "Risultati massimi",
        "es": "Resultados máx.",
        "pt": "Resultados máx.",
        "ko": "최대 결과",
    },
    "expand_query": {
        "zh": "LLM 扩展查询",
        "en": "LLM Expand Query",
        "ja": "LLM クエリ拡張",
        "fr": "Extension de requête LLM",
        "ru": "Расширение запроса LLM",
        "de": "LLM-Anfrage erweitern",
        "it": "Espansione query LLM",
        "es": "Expansión de consulta LLM",
        "pt": "Expansão de consulta LLM",
        "ko": "LLM 쿼리 확장",
    },
    "search_papers": {
        "zh": "搜索论文",
        "en": "Search Papers",
        "ja": "論文を検索",
        "fr": "Rechercher des articles",
        "ru": "Поиск статей",
        "de": "Papers suchen",
        "it": "Cerca articoli",
        "es": "Buscar artículos",
        "pt": "Pesquisar artigos",
        "ko": "논문 검색",
    },
    "download_selected": {
        "zh": "下载选中",
        "en": "Download Selected",
        "ja": "選択項目をダウンロード",
        "fr": "Télécharger la sélection",
        "ru": "Скачать выбранное",
        "de": "Ausgewählte herunterladen",
        "it": "Scarica selezionati",
        "es": "Descargar seleccionados",
        "pt": "Baixar selecionados",
        "ko": "선택 다운로드",
    },
    "research_settings": {
        "zh": "研究设置",
        "en": "Research Settings",
        "ja": "研究設定",
        "fr": "Paramètres de recherche",
        "ru": "Настройки исследования",
        "de": "Forschungseinstellungen",
        "it": "Impostazioni ricerca",
        "es": "Configuración de investigación",
        "pt": "Configurações de pesquisa",
        "ko": "연구 설정",
    },
    "downloaded_papers": {
        "zh": "已下载论文",
        "en": "Downloaded Papers",
        "ja": "ダウンロード済み論文",
        "fr": "Articles téléchargés",
        "ru": "Загруженные статьи",
        "de": "Heruntergeladene Papers",
        "it": "Articoli scaricati",
        "es": "Artículos descargados",
        "pt": "Artigos baixados",
        "ko": "다운로드된 논문",
    },
    "no_papers_found": {
        "zh": "未找到论文",
        "en": "No papers found",
        "ja": "論文が見つかりません",
        "fr": "Aucun article trouvé",
        "ru": "Статьи не найдены",
        "de": "Keine Papers gefunden",
        "it": "Nessun articolo trovato",
        "es": "No se encontraron artículos",
        "pt": "Nenhum artigo encontrado",
        "ko": "논문을 찾을 수 없습니다",
    },
    "enter_search_query": {
        "zh": "输入搜索查询以查找论文",
        "en": "Enter a search query to find papers",
        "ja": "論文を検索するには検索クエリを入力してください",
        "fr": "Entrez une requête pour trouver des articles",
        "ru": "Введите запрос для поиска статей",
        "de": "Suchanfrage eingeben, um Papers zu finden",
        "it": "Inserisci una query per cercare articoli",
        "es": "Ingresa una consulta para encontrar artículos",
        "pt": "Digite uma consulta para encontrar artigos",
        "ko": "논문을 찾으려면 검색 쿼리를 입력하세요",
    },
    "searching": {
        "zh": "搜索中...",
        "en": "Searching...",
        "ja": "検索中...",
        "fr": "Recherche...",
        "ru": "Поиск...",
        "de": "Suche...",
        "it": "Ricerca...",
        "es": "Buscando...",
        "pt": "Pesquisando...",
        "ko": "검색 중...",
    },
    "no_downloaded_papers": {
        "zh": "暂无已下载论文",
        "en": "No downloaded papers",
        "ja": "ダウンロード済み論文なし",
        "fr": "Aucun article téléchargé",
        "ru": "Нет загруженных статей",
        "de": "Keine heruntergeladenen Papers",
        "it": "Nessun articolo scaricato",
        "es": "No hay artículos descargados",
        "pt": "Nenhum artigo baixado",
        "ko": "다운로드된 논문 없음",
    },
    "view_markdown": {
        "zh": "查看 Markdown",
        "en": "View MD",
        "ja": "Markdown を表示",
        "fr": "Voir MD",
        "ru": "Просмотр MD",
        "de": "MD anzeigen",
        "it": "Vedi MD",
        "es": "Ver MD",
        "pt": "Ver MD",
        "ko": "MD 보기",
    },
    "delete": {
        "zh": "删除",
        "en": "Delete",
        "ja": "削除",
        "fr": "Supprimer",
        "ru": "Удалить",
        "de": "Löschen",
        "it": "Elimina",
        "es": "Eliminar",
        "pt": "Excluir",
        "ko": "삭제",
    },
    "delete_paper_confirm": {
        "zh": "确定删除此论文及其文件吗？",
        "en": "Delete this paper and its files?",
        "ja": "この論文とファイルを削除しますか？",
        "fr": "Supprimer cet article et ses fichiers ?",
        "ru": "Удалить эту статью и её файлы?",
        "de": "Dieses Paper und seine Dateien löschen?",
        "it": "Eliminare questo articolo e i suoi file?",
        "es": "¿Eliminar este artículo y sus archivos?",
        "pt": "Excluir este artigo e seus arquivos?",
        "ko": "이 논문과 파일을 삭제하시겠습니까?",
    },
    "paper_deleted": {
        "zh": "论文已删除",
        "en": "Paper deleted",
        "ja": "論文を削除しました",
        "fr": "Article supprimé",
        "ru": "Статья удалена",
        "de": "Paper gelöscht",
        "it": "Articolo eliminato",
        "es": "Artículo eliminado",
        "pt": "Artigo excluído",
        "ko": "논문이 삭제되었습니다",
    },
    "download_complete": {
        "zh": "下载完成",
        "en": "Download complete",
        "ja": "ダウンロード完了",
        "fr": "Téléchargement terminé",
        "ru": "Загрузка завершена",
        "de": "Download abgeschlossen",
        "it": "Download completato",
        "es": "Descarga completada",
        "pt": "Download concluído",
        "ko": "다운로드 완료",
    },
    "download_failed": {
        "zh": "下载失败",
        "en": "Download failed",
        "ja": "ダウンロード失敗",
        "fr": "Échec du téléchargement",
        "ru": "Ошибка загрузки",
        "de": "Download fehlgeschlagen",
        "it": "Download fallito",
        "es": "Error de descarga",
        "pt": "Falha no download",
        "ko": "다운로드 실패",
    },
    "downloading": {
        "zh": "下载中...",
        "en": "Downloading...",
        "ja": "ダウンロード中...",
        "fr": "Téléchargement...",
        "ru": "Загрузка...",
        "de": "Herunterladen...",
        "it": "Download in corso...",
        "es": "Descargando...",
        "pt": "Baixando...",
        "ko": "다운로드 중...",
    },
    "download_pdf": {
        "zh": "下载 PDF",
        "en": "Download PDF",
        "ja": "PDF をダウンロード",
        "fr": "Télécharger PDF",
        "ru": "Скачать PDF",
        "de": "PDF herunterladen",
        "it": "Scarica PDF",
        "es": "Descargar PDF",
        "pt": "Baixar PDF",
        "ko": "PDF 다운로드",
    },
    "close": {
        "zh": "关闭",
        "en": "Close",
        "ja": "閉じる",
        "fr": "Fermer",
        "ru": "Закрыть",
        "de": "Schließen",
        "it": "Chiudi",
        "es": "Cerrar",
        "pt": "Fechar",
        "ko": "닫기",
    },
    "citations": {
        "zh": "引用",
        "en": "Citations",
        "ja": "引用",
        "fr": "Citations",
        "ru": "Цитирования",
        "de": "Zitationen",
        "it": "Citazioni",
        "es": "Citas",
        "pt": "Citações",
        "ko": "인용",
    },
    "references": {
        "zh": "参考文献",
        "en": "References",
        "ja": "参考文献",
        "fr": "Références",
        "ru": "Ссылки",
        "de": "Referenzen",
        "it": "Riferimenti",
        "es": "Referencias",
        "pt": "Referências",
        "ko": "참고문헌",
    },
    "similar_papers": {
        "zh": "相似论文",
        "en": "Similar",
        "ja": "類似論文",
        "fr": "Similaires",
        "ru": "Похожие",
        "de": "Ähnlich",
        "it": "Simili",
        "es": "Similares",
        "pt": "Similares",
        "ko": "유사",
    },
    "click_tab_load_related": {
        "zh": "点击标签页加载相关论文",
        "en": "Click a tab to load related papers",
        "ja": "タブをクリックして関連論文を読み込む",
        "fr": "Cliquez sur un onglet pour charger les articles connexes",
        "ru": "Нажмите на вкладку для загрузки похожих статей",
        "de": "Klicke auf einen Tab, um ähnliche Papers zu laden",
        "it": "Clicca una scheda per caricare articoli correlati",
        "es": "Haz clic en una pestaña para cargar artículos relacionados",
        "pt": "Clique em uma aba para carregar artigos relacionados",
        "ko": "탭을 클릭하여 관련 논문을 로드하세요",
    },
    "loading": {
        "zh": "加载中...",
        "en": "Loading...",
        "ja": "読み込み中...",
        "fr": "Chargement...",
        "ru": "Загрузка...",
        "de": "Laden...",
        "it": "Caricamento...",
        "es": "Cargando...",
        "pt": "Carregando...",
        "ko": "로딩 중...",
    },
    "no_related_papers": {
        "zh": "未找到相关论文",
        "en": "No related papers found",
        "ja": "関連論文が見つかりません",
        "fr": "Aucun article connexe trouvé",
        "ru": "Похожие статьи не найдены",
        "de": "Keine ähnlichen Papers gefunden",
        "it": "Nessun articolo correlato trovato",
        "es": "No se encontraron artículos relacionados",
        "pt": "Nenhum artigo relacionado encontrado",
        "ko": "관련 논문을 찾을 수 없습니다",
    },
    "no_paper_id": {
        "zh": "无可用论文 ID",
        "en": "No paper ID available",
        "ja": "論文 ID がありません",
        "fr": "Aucun ID d'article disponible",
        "ru": "Нет ID статьи",
        "de": "Keine Paper-ID verfügbar",
        "it": "Nessun ID articolo disponibile",
        "es": "No hay ID de artículo disponible",
        "pt": "Nenhum ID de artigo disponível",
        "ko": "논문 ID를 사용할 수 없습니다",
    },
    "save_settings": {
        "zh": "保存设置",
        "en": "Save Settings",
        "ja": "設定を保存",
        "fr": "Enregistrer les paramètres",
        "ru": "Сохранить настройки",
        "de": "Einstellungen speichern",
        "it": "Salva impostazioni",
        "es": "Guardar configuración",
        "pt": "Salvar configurações",
        "ko": "설정 저장",
    },
    "settings_saved": {
        "zh": "设置已保存",
        "en": "Settings saved",
        "ja": "設定を保存しました",
        "fr": "Paramètres enregistrés",
        "ru": "Настройки сохранены",
        "de": "Einstellungen gespeichert",
        "it": "Impostazioni salvate",
        "es": "Configuración guardada",
        "pt": "Configurações salvas",
        "ko": "설정이 저장되었습니다",
    },
    "save_failed": {
        "zh": "保存失败",
        "en": "Save failed",
        "ja": "保存に失敗しました",
        "fr": "Échec de l'enregistrement",
        "ru": "Ошибка сохранения",
        "de": "Speichern fehlgeschlagen",
        "it": "Salvataggio fallito",
        "es": "Error al guardar",
        "pt": "Falha ao salvar",
        "ko": "저장 실패",
    },
    "untitled": {
        "zh": "无标题",
        "en": "Untitled",
        "ja": "無題",
        "fr": "Sans titre",
        "ru": "Без названия",
        "de": "Ohne Titel",
        "it": "Senza titolo",
        "es": "Sin título",
        "pt": "Sem título",
        "ko": "제목 없음",
    },
    "unknown": {
        "zh": "未知",
        "en": "Unknown",
        "ja": "不明",
        "fr": "Inconnu",
        "ru": "Неизвестно",
        "de": "Unbekannt",
        "it": "Sconosciuto",
        "es": "Desconocido",
        "pt": "Desconhecido",
        "ko": "알 수 없음",
    },
    "na": {
        "zh": "暂无",
        "en": "N/A",
        "ja": "N/A",
        "fr": "N/A",
        "ru": "Н/Д",
        "de": "N/A",
        "it": "N/D",
        "es": "N/D",
        "pt": "N/D",
        "ko": "N/A",
    },
    "year": {
        "zh": "年份",
        "en": "Year",
        "ja": "年",
        "fr": "Année",
        "ru": "Год",
        "de": "Jahr",
        "it": "Anno",
        "es": "Año",
        "pt": "Ano",
        "ko": "연도",
    },
    "journal": {
        "zh": "期刊",
        "en": "Journal",
        "ja": "ジャーナル",
        "fr": "Journal",
        "ru": "Журнал",
        "de": "Zeitschrift",
        "it": "Rivista",
        "es": "Revista",
        "pt": " Periódico",
        "ko": "저널",
    },
    "venue": {
        "zh": "会议/ venue",
        "en": "Venue",
        "ja": "会議/会場",
        "fr": "Lieu",
        "ru": "Место",
        "de": "Veranstaltungsort",
        "it": "Sede",
        "es": "Sede",
        "pt": "Local",
        "ko": "학회/장소",
    },
    "auto_rename_pdfs": {
        "zh": "自动重命名 PDF",
        "en": "Auto-rename PDFs",
        "ja": "PDF を自動リネーム",
        "fr": "Renommer automatiquement les PDF",
        "ru": "Автопереименование PDF",
        "de": "PDFs automatisch umbenennen",
        "it": "Rinomina PDF automaticamente",
        "es": "Renombrar PDFs automáticamente",
        "pt": "Renomear PDFs automaticamente",
        "ko": "PDF 자동 이름 변경",
    },
    "auto_convert_md": {
        "zh": "自动转换为 Markdown",
        "en": "Auto-convert to Markdown",
        "ja": "Markdown に自動変換",
        "fr": "Convertir automatiquement en Markdown",
        "ru": "Автоконвертация в Markdown",
        "de": "Automatisch zu Markdown konvertieren",
        "it": "Converti automaticamente in Markdown",
        "es": "Convertir automáticamente a Markdown",
        "pt": "Converter automaticamente para Markdown",
        "ko": "Markdown 자동 변환",
    },
}


def t(key: str, lang: Optional[str] = None, *args: Any) -> str:
    """Translate a key to the specified language.

    Parameters
    ----------
    key : str
        Translation key.
    lang : str or None
        Language code (defaults to CONFIG.language).
    *args
        Format arguments for parameterized translations.

    Returns
    -------
    str
        Translated text.
    """
    if key not in TRANSLATIONS:
        return key

    if lang is None:
        lang = CONFIG.language

    translations = TRANSLATIONS[key]
    text = translations.get(lang, translations.get("en", key))

    if args:
        return text.format(*args)

    return text
