"""Configuration management for GangDan.

This module handles global configuration, internationalization (i18n),
and utility functions for the GangDan application.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
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
    except (json.JSONDecodeError, OSError):
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

    if total == 0:
        return "en"

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
}


def t(key: str, lang: Optional[str] = None, *args) -> str:
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
