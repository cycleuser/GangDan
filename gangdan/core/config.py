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
from typing import Any, Dict, List, Optional

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
        "ja": "Ollama と ChromaDB を使用したローカルオフラインプログラミングアシスタント",
        "fr": "Assistant de programmation hors-ligne basé sur Ollama et ChromaDB",
        "ru": "Локальный офлайн-помощник на базе Ollama и ChromaDB",
        "de": "Lokaler Offline-Programmierassistent mit Ollama und ChromaDB",
        "it": "Assistente di programmazione offline basato su Ollama e ChromaDB",
        "es": "Asistente de programación offline basado en Ollama y ChromaDB",
        "pt": "Assistente de programação offline baseado em Ollama e ChromaDB",
        "ko": "Ollama 와 ChromaDB 기반 로컬 오프라인 프로그래밍 어시스턴트",
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
        "ja": "コマンドの生成、結果の分析、エラーの説明をお手伝いします。",
        "fr": "Demandez-moi de générer des commandes, d'analyser des résultats ou d'expliquer des erreurs.",
        "ru": "Попросите меня сгенерировать команды, проанализировать результаты или объяснить ошибки.",
        "de": "Bitten Sie mich, Befehle zu generieren, Ergebnisse zu analysieren oder Fehler zu erklären.",
        "it": "Chiedimi di generare comandi, analizzare risultati o spiegare errori.",
        "es": "Pídale generar comandos, analizar resultados o explicar errores.",
        "pt": "Peça para gerar comandos, analisar resultados ou explicar erros.",
        "ko": "명령 생성, 결과 분석, 오류 설명을 요청하세요.",
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
