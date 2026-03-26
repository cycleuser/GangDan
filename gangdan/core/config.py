"""Configuration management for GangDan."""

import os
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass


# =============================================================================
# Data Directory
# =============================================================================

def _get_data_dir() -> Path:
    """Determine the data directory based on environment or install context."""
    env = os.environ.get('GANGDAN_DATA_DIR')
    if env:
        return Path(env).expanduser().resolve()
    pkg_dir = Path(__file__).resolve().parent.parent
    if 'site-packages' in str(pkg_dir) or 'dist-packages' in str(pkg_dir):
        return Path.home() / '.gangdan'
    return Path('./data')


DATA_DIR = _get_data_dir()
DOCS_DIR = DATA_DIR / "docs"
CHROMA_DIR = DATA_DIR / "chroma"


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class Config:
    ollama_url: str = "http://localhost:11434"
    embedding_model: str = ""
    chat_model: str = ""
    reranker_model: str = ""
    chunk_size: int = 800
    chunk_overlap: int = 150
    top_k: int = 15
    max_context_tokens: int = 3000
    language: str = "zh"
    context_length: int = 4096
    # Proxy settings
    proxy_mode: str = "none"  # "none", "system", "manual"
    proxy_http: str = ""
    proxy_https: str = ""
    # RAG behavior settings
    strict_kb_mode: bool = False  # If True, refuse to answer when KB has no results
    # Vector database settings
    vector_db_type: str = "chroma"  # "chroma", "faiss", "memory"
    # Deep Research LLM Provider settings (separate from chat)
    research_provider: str = "ollama"  # "ollama", "openai", "dashscope", "deepseek", "moonshot", "zhipu", "siliconflow", "custom"
    research_api_key: str = ""
    research_api_base_url: str = ""
    research_model: str = ""


CONFIG = Config()
CONFIG_FILE = DATA_DIR / "gangdan_config.json"


def get_proxies() -> Optional[Dict[str, str]]:
    """Get proxy configuration based on settings."""
    if CONFIG.proxy_mode == "none":
        return None
    elif CONFIG.proxy_mode == "system":
        http_proxy = os.environ.get("HTTP_PROXY", os.environ.get("http_proxy", ""))
        https_proxy = os.environ.get("HTTPS_PROXY", os.environ.get("https_proxy", ""))
        if http_proxy or https_proxy:
            return {"http": http_proxy, "https": https_proxy or http_proxy}
        return None
    elif CONFIG.proxy_mode == "manual":
        if CONFIG.proxy_http or CONFIG.proxy_https:
            return {
                "http": CONFIG.proxy_http,
                "https": CONFIG.proxy_https or CONFIG.proxy_http
            }
        return None
    return None


def load_config():
    """Load configuration from disk."""
    global CONFIG
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text())
            CONFIG.ollama_url = data.get("ollama_url", CONFIG.ollama_url)
            CONFIG.embedding_model = data.get("embedding_model", "")
            CONFIG.chat_model = data.get("chat_model", "")
            CONFIG.reranker_model = data.get("reranker_model", "")
            CONFIG.top_k = data.get("top_k", CONFIG.top_k)
            CONFIG.language = data.get("language", "zh")
            CONFIG.proxy_mode = data.get("proxy_mode", "none")
            CONFIG.proxy_http = data.get("proxy_http", "")
            CONFIG.proxy_https = data.get("proxy_https", "")
            CONFIG.strict_kb_mode = data.get("strict_kb_mode", False)
            CONFIG.vector_db_type = data.get("vector_db_type", "chroma")
            # Deep Research LLM Provider settings
            CONFIG.research_provider = data.get("research_provider", "ollama")
            CONFIG.research_api_key = data.get("research_api_key", "")
            CONFIG.research_api_base_url = data.get("research_api_base_url", "")
            CONFIG.research_model = data.get("research_model", "")
        except:
            pass


def save_config():
    """Save configuration to disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps({
        "ollama_url": CONFIG.ollama_url,
        "embedding_model": CONFIG.embedding_model,
        "chat_model": CONFIG.chat_model,
        "reranker_model": CONFIG.reranker_model,
        "top_k": CONFIG.top_k,
        "language": CONFIG.language,
        "proxy_mode": CONFIG.proxy_mode,
        "proxy_http": CONFIG.proxy_http,
        "proxy_https": CONFIG.proxy_https,
        "strict_kb_mode": CONFIG.strict_kb_mode,
        "vector_db_type": CONFIG.vector_db_type,
        "research_provider": CONFIG.research_provider,
        "research_api_key": CONFIG.research_api_key,
        "research_api_base_url": CONFIG.research_api_base_url,
        "research_model": CONFIG.research_model,
    }, indent=2))


# =============================================================================
# User Knowledge Base Manifest
# =============================================================================

USER_KBS_FILE = DATA_DIR / "user_kbs.json"


def load_user_kbs() -> dict:
    """Load user-created knowledge base manifest."""
    if USER_KBS_FILE.exists():
        try:
            return json.loads(USER_KBS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_user_kb(internal_name: str, display_name: str, file_count: int, languages: List[str] = None, output_word_limit: int = None):
    """Add or update a user KB entry in the manifest."""
    kbs = load_user_kbs()
    entry = {
        "display_name": display_name,
        "created": datetime.now().isoformat(),
        "file_count": file_count,
        "languages": languages or [],
    }
    if output_word_limit is not None:
        entry["output_word_limit"] = output_word_limit
    kbs[internal_name] = entry
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    USER_KBS_FILE.write_text(json.dumps(kbs, indent=2, ensure_ascii=False), encoding="utf-8")


def delete_user_kb(internal_name: str):
    """Remove a user KB entry from the manifest."""
    kbs = load_user_kbs()
    kbs.pop(internal_name, None)
    USER_KBS_FILE.write_text(json.dumps(kbs, indent=2, ensure_ascii=False), encoding="utf-8")


def sanitize_kb_name(name: str) -> str:
    """Sanitize user-provided KB name to a safe internal name with user_ prefix."""
    import re
    
    safe = re.sub(r'[^a-zA-Z0-9\s-]', '', name.strip()).strip()
    safe = re.sub(r'[\s-]+', '_', safe).lower()
    
    if not safe or len(safe) < 3:
        name_hash = hashlib.md5(name.encode('utf-8')).hexdigest()[:8]
        safe = f"kb_{name_hash}"
    
    return f"user_{safe}"


# =============================================================================
# Language Detection
# =============================================================================

def detect_language(text: str) -> str:
    """Detect language using Unicode character ranges.
    
    Returns ISO 639-1 code: zh, en, ja, ko, ru, fr, de, es, pt, it
    Defaults to 'unknown' if unclear.
    """
    if not text:
        return "unknown"
    
    sample = text[:500]
    
    cjk = sum(1 for c in sample if '\u4e00' <= c <= '\u9fff')
    hiragana = sum(1 for c in sample if '\u3040' <= c <= '\u309f')
    katakana = sum(1 for c in sample if '\u30a0' <= c <= '\u30ff')
    hangul = sum(1 for c in sample if '\uac00' <= c <= '\ud7af')
    cyrillic = sum(1 for c in sample if '\u0400' <= c <= '\u04ff')
    
    total = len(sample)
    if total == 0:
        return "unknown"
    
    if (hiragana + katakana) / total > 0.1:
        return "ja"
    if hangul / total > 0.1:
        return "ko"
    if cjk / total > 0.1:
        return "zh"
    if cyrillic / total > 0.1:
        return "ru"
    return "en"


# =============================================================================
# Internationalization (i18n) - 10 Languages
# =============================================================================

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
    "ko": "한국어"
}

TRANSLATIONS = {
    "app_title": {
        "zh": "纲担", "en": "GangDan",
        "ja": "GangDan", "fr": "GangDan",
        "ru": "GangDan", "de": "GangDan",
        "it": "GangDan", "es": "GangDan",
        "pt": "GangDan", "ko": "GangDan"
    },
    "app_subtitle": {
        "zh": "有纲领有担当，基于 Ollama 和 ChromaDB 的离线开发助手",
        "en": "Local offline programming assistant powered by Ollama and ChromaDB",
        "ja": "OllamaとChromaDBを使用したローカルオフラインプログラミングアシスタント",
        "fr": "Assistant de programmation hors-ligne basé sur Ollama et ChromaDB",
        "ru": "Локальный офлайн-помощник на базе Ollama и ChromaDB",
        "de": "Lokaler Offline-Programmierassistent mit Ollama und ChromaDB",
        "it": "Assistente di programmazione offline basato su Ollama e ChromaDB",
        "es": "Asistente de programación offline basado en Ollama y ChromaDB",
        "pt": "Assistente de programação offline baseado em Ollama e ChromaDB",
        "ko": "Ollama와 ChromaDB 기반 로컬 오프라인 프로그래밍 어시스턴트"
    },
    "chat": {"zh": "对话", "en": "Chat", "ja": "チャット", "fr": "Chat", "ru": "Чат", "de": "Chat", "it": "Chat", "es": "Chat", "pt": "Chat", "ko": "채팅"},
    "docs": {"zh": "文档", "en": "Docs", "ja": "ドキュメント", "fr": "Docs", "ru": "Документы", "de": "Dokumente", "it": "Documenti", "es": "Docs", "pt": "Docs", "ko": "문서"},
    "settings": {"zh": "设置", "en": "Settings", "ja": "設定", "fr": "Paramètres", "ru": "Настройки", "de": "Einstellungen", "it": "Impostazioni", "es": "Configuración", "pt": "Configurações", "ko": "설정"},
    "send": {"zh": "发送", "en": "Send", "ja": "送信", "fr": "Envoyer", "ru": "Отправить", "de": "Senden", "it": "Invia", "es": "Enviar", "pt": "Enviar", "ko": "보내기"},
    "stop": {"zh": "停止", "en": "Stop", "ja": "停止", "fr": "Arrêter", "ru": "Стоп", "de": "Stopp", "it": "Ferma", "es": "Parar", "pt": "Parar", "ko": "중지"},
    "clear": {"zh": "清除", "en": "Clear", "ja": "クリア", "fr": "Effacer", "ru": "Очистить", "de": "Löschen", "it": "Cancella", "es": "Borrar", "pt": "Limpar", "ko": "지우기"},
    "export": {"zh": "导出", "en": "Export", "ja": "エクスポート", "fr": "Exporter", "ru": "Экспорт", "de": "Exportieren", "it": "Esporta", "es": "Exportar", "pt": "Exportar", "ko": "내보내기"},
    "save_conversation": {"zh": "保存对话", "en": "Save Chat", "ja": "会話を保存", "fr": "Enregistrer le chat", "ru": "Сохранить чат", "de": "Chat speichern", "it": "Salva chat", "es": "Guardar chat", "pt": "Salvar chat", "ko": "대화 저장"},
    "load_conversation": {"zh": "加载对话", "en": "Load Chat", "ja": "会話を読み込む", "fr": "Charger le chat", "ru": "Загрузить чат", "de": "Chat laden", "it": "Carica chat", "es": "Cargar chat", "pt": "Carregar chat", "ko": "대화 불러오기"},
    "conversation_loaded": {"zh": "已加载 {0} 条消息", "en": "Loaded {0} messages", "ja": "{0}件のメッセージを読み込みました", "fr": "{0} messages chargés", "ru": "Загружено {0} сообщений", "de": "{0} Nachrichten geladen", "it": "{0} messaggi caricati", "es": "{0} mensajes cargados", "pt": "{0} mensagens carregadas", "ko": "{0}개 메시지 로드됨"},
    "invalid_conversation_file": {"zh": "无效的对话文件", "en": "Invalid conversation file", "ja": "無効な会話ファイル", "fr": "Fichier de conversation invalide", "ru": "Неверный файл разговора", "de": "Ungültige Konversationsdatei", "it": "File conversazione non valido", "es": "Archivo de conversación inválido", "pt": "Arquivo de conversa inválido", "ko": "잘못된 대화 파일"},
    "use_kb": {"zh": "使用知识库", "en": "Use Knowledge Base", "ja": "知識ベースを使用", "fr": "Utiliser la base de connaissances", "ru": "Использовать базу знаний", "de": "Wissensdatenbank verwenden", "it": "Usa base di conoscenza", "es": "Usar base de conocimiento", "pt": "Usar base de conhecimento", "ko": "지식 베이스 사용"},
    "use_web": {"zh": "搜索网络", "en": "Search Web", "ja": "ウェブ検索", "fr": "Rechercher sur le Web", "ru": "Поиск в интернете", "de": "Web durchsuchen", "it": "Cerca sul Web", "es": "Buscar en la Web", "pt": "Pesquisar na Web", "ko": "웹 검색"},
    "download": {"zh": "下载", "en": "Download", "ja": "ダウンロード", "fr": "Télécharger", "ru": "Скачать", "de": "Herunterladen", "it": "Scarica", "es": "Descargar", "pt": "Baixar", "ko": "다운로드"},
    "index": {"zh": "索引", "en": "Index", "ja": "インデックス", "fr": "Indexer", "ru": "Индексировать", "de": "Indexieren", "it": "Indicizza", "es": "Indexar", "pt": "Indexar", "ko": "인덱스"},
    "refresh": {"zh": "刷新", "en": "Refresh", "ja": "更新", "fr": "Actualiser", "ru": "Обновить", "de": "Aktualisieren", "it": "Aggiorna", "es": "Actualizar", "pt": "Atualizar", "ko": "새로고침"},
    "save": {"zh": "保存", "en": "Save", "ja": "保存", "fr": "Enregistrer", "ru": "Сохранить", "de": "Speichern", "it": "Salva", "es": "Guardar", "pt": "Salvar", "ko": "저장"},
    "embedding_model": {"zh": "嵌入模型", "en": "Embedding Model", "ja": "埋め込みモデル", "fr": "Modèle d'embedding", "ru": "Модель эмбеддинга", "de": "Embedding-Modell", "it": "Modello di embedding", "es": "Modelo de embedding", "pt": "Modelo de embedding", "ko": "임베딩 모델"},
    "chat_model": {"zh": "聊天模型", "en": "Chat Model", "ja": "チャットモデル", "fr": "Modèle de chat", "ru": "Модель чата", "de": "Chat-Modell", "it": "Modello di chat", "es": "Modelo de chat", "pt": "Modelo de chat", "ko": "채팅 모델"},
    "language": {"zh": "界面语言", "en": "UI Language", "ja": "UI言語", "fr": "Langue de l'interface", "ru": "Язык интерфейса", "de": "Oberflächensprache", "it": "Lingua dell'interfaccia", "es": "Idioma de interfaz", "pt": "Idioma da interface", "ko": "인터페이스 언어"},
    "select_source": {"zh": "选择源", "en": "Select Source", "ja": "ソースを選択", "fr": "Sélectionner la source", "ru": "Выбрать источник", "de": "Quelle auswählen", "it": "Seleziona fonte", "es": "Seleccionar fuente", "pt": "Selecionar fonte", "ko": "소스 선택"},
    "downloaded": {"zh": "已下载", "en": "Downloaded", "ja": "ダウンロード済み", "fr": "Téléchargé", "ru": "Загружено", "de": "Heruntergeladen", "it": "Scaricato", "es": "Descargado", "pt": "Baixado", "ko": "다운로드됨"},
    "indexed": {"zh": "已索引", "en": "Indexed", "ja": "インデックス済み", "fr": "Indexé", "ru": "Проиндексировано", "de": "Indexiert", "it": "Indicizzato", "es": "Indexado", "pt": "Indexado", "ko": "인덱스됨"},
    "status": {"zh": "状态", "en": "Status", "ja": "状態", "fr": "État", "ru": "Статус", "de": "Status", "it": "Stato", "es": "Estado", "pt": "Estado", "ko": "상태"},
    "ollama_url": {"zh": "Ollama 地址", "en": "Ollama URL", "ja": "Ollama URL", "fr": "URL Ollama", "ru": "URL Ollama", "de": "Ollama-URL", "it": "URL Ollama", "es": "URL de Ollama", "pt": "URL do Ollama", "ko": "Ollama URL"},
    "test_connection": {"zh": "测试连接", "en": "Test Connection", "ja": "接続テスト", "fr": "Tester la connexion", "ru": "Тест соединения", "de": "Verbindung testen", "it": "Test connessione", "es": "Probar conexión", "pt": "Testar conexão", "ko": "연결 테스트"},
    "type_message": {"zh": "输入消息...", "en": "Type a message...", "ja": "メッセージを入力...", "fr": "Tapez un message...", "ru": "Введите сообщение...", "de": "Nachricht eingeben...", "it": "Digita un messaggio...", "es": "Escribe un mensaje...", "pt": "Digite uma mensagem...", "ko": "메시지를 입력하세요..."},
    "no_models": {"zh": "未检测到模型，请先拉取模型", "en": "No models detected, please pull models first", "ja": "モデルが検出されません。最初にモデルをプルしてください", "fr": "Aucun modèle détecté, veuillez d'abord télécharger des modèles", "ru": "Модели не обнаружены, сначала загрузите модели", "de": "Keine Modelle erkannt, bitte zuerst Modelle laden", "it": "Nessun modello rilevato, prima scarica i modelli", "es": "No se detectaron modelos, primero descargue modelos", "pt": "Nenhum modelo detectado, primeiro baixe modelos", "ko": "모델이 감지되지 않았습니다. 먼저 모델을 다운로드하세요"},
    "generation_stopped": {"zh": "生成已停止", "en": "Generation stopped", "ja": "生成が停止しました", "fr": "Génération arrêtée", "ru": "Генерация остановлена", "de": "Generierung gestoppt", "it": "Generazione interrotta", "es": "Generación detenida", "pt": "Geração interrompida", "ko": "생성이 중지되었습니다"},
    "proxy_settings": {"zh": "代理设置", "en": "Proxy Settings", "ja": "プロキシ設定", "fr": "Paramètres proxy", "ru": "Настройки прокси", "de": "Proxy-Einstellungen", "it": "Impostazioni proxy", "es": "Configuración de proxy", "pt": "Configurações de proxy", "ko": "프록시 설정"},
    "no_proxy": {"zh": "不使用代理", "en": "No Proxy", "ja": "プロキシなし", "fr": "Pas de proxy", "ru": "Без прокси", "de": "Kein Proxy", "it": "Nessun proxy", "es": "Sin proxy", "pt": "Sem proxy", "ko": "프록시 없음"},
    "system_proxy": {"zh": "系统代理", "en": "System Proxy", "ja": "システムプロキシ", "fr": "Proxy système", "ru": "Системный прокси", "de": "System-Proxy", "it": "Proxy di sistema", "es": "Proxy del sistema", "pt": "Proxy do sistema", "ko": "시스템 프록시"},
    "manual_proxy": {"zh": "手动设置", "en": "Manual Proxy", "ja": "手動プロキシ", "fr": "Proxy manuel", "ru": "Ручной прокси", "de": "Manueller Proxy", "it": "Proxy manuale", "es": "Proxy manual", "pt": "Proxy manual", "ko": "수동 프록시"},
    "ai_assistant": {"zh": "AI 命令助手", "en": "AI Command Assistant", "ja": "AIコマンドアシスタント", "fr": "Assistant de commandes IA", "ru": "AI Командный помощник", "de": "KI-Befehlsassistent", "it": "Assistente comandi IA", "es": "Asistente de comandos IA", "pt": "Assistente de comandos IA", "ko": "AI 명령 어시스턴트"},
    "command_line": {"zh": "命令行", "en": "Command Line", "ja": "コマンドライン", "fr": "Ligne de commande", "ru": "Командная строка", "de": "Befehlszeile", "it": "Riga di comando", "es": "Línea de comandos", "pt": "Linha de comando", "ko": "명령줄"},
    "ai_ask_desc": {"zh": "输入问题或描述任务...", "en": "Describe what you want to do...", "ja": "やりたいことを入力...", "fr": "Décrivez ce que vous voulez faire...", "ru": "Опишите, что вы хотите сделать...", "de": "Beschreiben Sie, was Sie tun möchten...", "it": "Descrivi cosa vuoi fare...", "es": "Describa lo que quiere hacer...", "pt": "Descreva o que deseja fazer...", "ko": "원하는 작업을 설명하세요..."},
    "enter_command": {"zh": "输入命令...", "en": "Enter command...", "ja": "コマンドを入力...", "fr": "Entrer une commande...", "ru": "Введите команду...", "de": "Befehl eingeben...", "it": "Inserisci comando...", "es": "Ingrese comando...", "pt": "Digite o comando...", "ko": "명령어 입력..."},
    "ai_cleared": {"zh": "AI 助手已清空", "en": "AI assistant cleared", "ja": "AIアシスタントがクリアされました", "fr": "Assistant IA effacé", "ru": "AI помощник очищен", "de": "KI-Assistent gelöscht", "it": "Assistente IA cancellato", "es": "Asistente IA borrado", "pt": "Assistente IA limpo", "ko": "AI 어시스턴트 초기화됨"},
    "ai_intro": {"zh": "输入问题让我帮你生成命令、分析结果或解释错误。", "en": "Ask me to generate commands, analyze results, or explain errors.", "ja": "コマンドの生成、結果の分析、エラーの説明をお手伝いします。", "fr": "Demandez-moi de générer des commandes, d'analyser des résultats ou d'expliquer des erreurs.", "ru": "Попросите меня сгенерировать команды, проанализировать результаты или объяснить ошибки.", "de": "Bitten Sie mich, Befehle zu generieren, Ergebnisse zu analysieren oder Fehler zu erklären.", "it": "Chiedimi di generare comandi, analizzare risultati o spiegare errori.", "es": "Pídale generar comandos, analizar resultados o explicar errores.", "pt": "Peça para gerar comandos, analisar resultados ou explicar erros.", "ko": "명령 생성, 결과 분석, 오류 설명을 요청하세요."},
    "terminal_ready": {"zh": "终端就绪", "en": "Terminal Ready", "ja": "ターミナル準備完了", "fr": "Terminal prêt", "ru": "Терминал готов", "de": "Terminal bereit", "it": "Terminale pronto", "es": "Terminal listo", "pt": "Terminal pronto", "ko": "터미널 준비됨"},
    "terminal_hint": {"zh": "输入命令或从AI助手拖拽。", "en": "Type commands or drag from AI assistant.", "ja": "コマンドを入力するかAIアシスタントからドラッグ。", "fr": "Tapez des commandes ou glissez depuis l'assistant IA.", "ru": "Введите команды или перетащите из AI-помощника.", "de": "Befehle eingeben oder vom KI-Assistenten ziehen.", "it": "Digita comandi o trascina dall'assistente IA.", "es": "Escriba comandos o arrastre desde el asistente IA.", "pt": "Digite comandos ou arraste do assistente IA.", "ko": "명령어를 입력하거나 AI 어시스턴트에서 드래그하세요."},
    "proxy": {"zh": "代理设置", "en": "Proxy", "ja": "プロキシ", "fr": "Proxy", "ru": "Прокси", "de": "Proxy", "it": "Proxy", "es": "Proxy", "pt": "Proxy", "ko": "프록시"},
    "quick_download": {"zh": "快速下载", "en": "Quick Download", "ja": "クイックダウンロード", "fr": "Téléchargement rapide", "ru": "Быстрая загрузка", "de": "Schnell-Download", "it": "Download rapido", "es": "Descarga rápida", "pt": "Download rápido", "ko": "빠른 다운로드"},
    "batch_download": {"zh": "批量下载", "en": "Batch Download", "ja": "一括ダウンロード", "fr": "Téléchargement par lot", "ru": "Пакетная загрузка", "de": "Batch-Download", "it": "Download multiplo", "es": "Descarga por lotes", "pt": "Download em lote", "ko": "일괄 다운로드"},
    "batch_index": {"zh": "批量索引", "en": "Batch Index", "ja": "一括インデックス", "fr": "Indexer par lot", "ru": "Пакетная индексация", "de": "Batch-Index", "it": "Indicizza multiplo", "es": "Indexar por lotes", "pt": "Indexar em lote", "ko": "일괄 인덱스"},
    "select_all": {"zh": "全选", "en": "Select All", "ja": "全選択", "fr": "Tout sélectionner", "ru": "Выбрать все", "de": "Alle auswählen", "it": "Seleziona tutto", "es": "Seleccionar todo", "pt": "Selecionar tudo", "ko": "전체 선택"},
    "deselect_all": {"zh": "清空", "en": "Deselect", "ja": "選択解除", "fr": "Désélectionner", "ru": "Снять выбор", "de": "Auswahl aufheben", "it": "Deseleziona", "es": "Deseleccionar", "pt": "Desmarcar", "ko": "선택 해제"},
    "web_search_kb": {"zh": "网络搜索入库", "en": "Web Search to KB", "ja": "ウェブ検索をKBへ", "fr": "Recherche web vers KB", "ru": "Поиск в базу знаний", "de": "Websuche zu KB", "it": "Ricerca web a KB", "es": "Búsqueda web a KB", "pt": "Pesquisa web para KB", "ko": "웹 검색 KB"},
    "search_add_kb": {"zh": "搜索入库", "en": "Search & Add", "ja": "検索して追加", "fr": "Rechercher et ajouter", "ru": "Найти и добавить", "de": "Suchen und hinzufügen", "it": "Cerca e aggiungi", "es": "Buscar y añadir", "pt": "Pesquisar e adicionar", "ko": "검색 및 추가"},
    "github_search": {"zh": "GitHub 搜索", "en": "GitHub Search", "ja": "GitHub検索", "fr": "Recherche GitHub", "ru": "Поиск GitHub", "de": "GitHub-Suche", "it": "Ricerca GitHub", "es": "Búsqueda GitHub", "pt": "Pesquisa GitHub", "ko": "GitHub 검색"},
    "all_languages": {"zh": "所有语言", "en": "All Languages", "ja": "全言語", "fr": "Toutes les langues", "ru": "Все языки", "de": "Alle Sprachen", "it": "Tutte le lingue", "es": "Todos los idiomas", "pt": "Todos os idiomas", "ko": "모든 언어"},
    "search": {"zh": "搜索", "en": "Search", "ja": "検索", "fr": "Rechercher", "ru": "Поиск", "de": "Suchen", "it": "Cerca", "es": "Buscar", "pt": "Pesquisar", "ko": "검색"},
    "search_keyword": {"zh": "搜索关键词...", "en": "Search keywords...", "ja": "キーワード検索...", "fr": "Mots-clés...", "ru": "Ключевые слова...", "de": "Suchbegriffe...", "it": "Parole chiave...", "es": "Palabras clave...", "pt": "Palavras-chave...", "ko": "검색 키워드..."},
    "search_docs": {"zh": "搜索技术文档...", "en": "Search tech docs...", "ja": "技術文書を検索...", "fr": "Rechercher des docs...", "ru": "Поиск документации...", "de": "Techdocs suchen...", "it": "Cerca documentazione...", "es": "Buscar documentación...", "pt": "Pesquisar documentação...", "ko": "기술 문서 검색..."},
    "kb_name": {"zh": "知识库名称", "en": "KB Name", "ja": "KB名", "fr": "Nom de la KB", "ru": "Имя БЗ", "de": "KB-Name", "it": "Nome KB", "es": "Nombre KB", "pt": "Nome da KB", "ko": "KB 이름"},
    "connection_status": {"zh": "连接状态", "en": "Connection Status", "ja": "接続状態", "fr": "État de connexion", "ru": "Статус подключения", "de": "Verbindungsstatus", "it": "Stato connessione", "es": "Estado de conexión", "pt": "Estado de conexão", "ko": "연결 상태"},
    "embedding": {"zh": "嵌入模型", "en": "Embedding", "ja": "エンベディング", "fr": "Embedding", "ru": "Эмбеддинг", "de": "Embedding", "it": "Embedding", "es": "Embedding", "pt": "Embedding", "ko": "임베딩"},
    "reranker": {"zh": "重排模型", "en": "Reranker", "ja": "リランカー", "fr": "Reranker", "ru": "Реранкер", "de": "Reranker", "it": "Reranker", "es": "Reranker", "pt": "Reranker", "ko": "리랭커"},
    "optional": {"zh": "可选", "en": "Optional", "ja": "オプション", "fr": "Optionnel", "ru": "Необязательно", "de": "Optional", "it": "Opzionale", "es": "Opcional", "pt": "Opcional", "ko": "선택사항"},
    "mode": {"zh": "模式", "en": "Mode", "ja": "モード", "fr": "Mode", "ru": "Режим", "de": "Modus", "it": "Modalità", "es": "Modo", "pt": "Modo", "ko": "모드"},
    "no_proxy_opt": {"zh": "不使用", "en": "None", "ja": "なし", "fr": "Aucun", "ru": "Нет", "de": "Keiner", "it": "Nessuno", "es": "Ninguno", "pt": "Nenhum", "ko": "없음"},
    "system_proxy_opt": {"zh": "系统代理", "en": "System", "ja": "システム", "fr": "Système", "ru": "Системный", "de": "System", "it": "Sistema", "es": "Sistema", "pt": "Sistema", "ko": "시스템"},
    "manual_proxy_opt": {"zh": "手动设置", "en": "Manual", "ja": "手動", "fr": "Manuel", "ru": "Ручной", "de": "Manuell", "it": "Manuale", "es": "Manual", "pt": "Manual", "ko": "수동"},
    "save_settings": {"zh": "保存设置", "en": "Save Settings", "ja": "設定を保存", "fr": "Enregistrer les paramètres", "ru": "Сохранить настройки", "de": "Einstellungen speichern", "it": "Salva impostazioni", "es": "Guardar configuración", "pt": "Salvar configurações", "ko": "설정 저장"},
    "analyzing": {"zh": "分析中...", "en": "Analyzing...", "ja": "分析中...", "fr": "Analyse en cours...", "ru": "Анализ...", "de": "Analyse...", "it": "Analizzando...", "es": "Analizando...", "pt": "Analisando...", "ko": "분석 중..."},
    "context_found": {"zh": "检索到相关上下文，正在分析...", "en": "Found relevant context, analyzing...", "ja": "関連コンテキストを検出、分析中...", "fr": "Contexte pertinent trouvé, analyse en cours...", "ru": "Найден релевантный контекст, анализ...", "de": "Relevanter Kontext gefunden, Analyse...", "it": "Contesto rilevante trovato, analisi...", "es": "Contexto relevante encontrado, analizando...", "pt": "Contexto relevante encontrado, analisando...", "ko": "관련 컨텍스트 발견, 분석 중..."},
    "context_stale": {"zh": "上次执行已过期，将重新生成命令", "en": "Previous context is stale, regenerating command", "ja": "前回のコンテキストが古いため、コマンドを再生成します", "fr": "Contexte précédent expiré, régénération de la commande", "ru": "Предыдущий контекст устарел, перегенерация команды", "de": "Vorheriger Kontext veraltet, Befehl wird neu generiert", "it": "Contesto precedente scaduto, rigenerazione comando", "es": "Contexto anterior expirado, regenerando comando", "pt": "Contexto anterior expirado, regenerando comando", "ko": "이전 컨텍스트 만료, 명령 재생성"},
    "context_low_match": {"zh": "与之前的上下文匹配度较低，将重新生成命令", "en": "Low match with previous context, regenerating command", "ja": "前回のコンテキストとの一致度が低いため、再生成します", "fr": "Faible correspondance, régénération de la commande", "ru": "Низкое совпадение, перегенерация команды", "de": "Geringe Übereinstimmung, Befehl wird neu generiert", "it": "Bassa corrispondenza, rigenerazione comando", "es": "Baja coincidencia, regenerando comando", "pt": "Baixa correspondência, regenerando comando", "ko": "이전 컨텍스트와 일치도 낮음, 명령 재생성"},
    "context_session_stale": {"zh": "会话已超时，将重新生成命令", "en": "Session timed out, regenerating command", "ja": "セッションタイムアウト、コマンドを再生成します", "fr": "Session expirée, régénération de la commande", "ru": "Сессия истекла, перегенерация команды", "de": "Sitzung abgelaufen, Befehl wird neu generiert", "it": "Sessione scaduta, rigenerazione comando", "es": "Sesión expirada, regenerando comando", "pt": "Sessão expirada, regenerando comando", "ko": "세션 만료, 명령 재생성"},
    "based_on_history": {"zh": "基于历史记录生成", "en": "Based on history", "ja": "履歴に基づいて生成", "fr": "Basé sur l'historique", "ru": "На основе истории", "de": "Basierend auf Verlauf", "it": "Basato sulla cronologia", "es": "Basado en historial", "pt": "Baseado no histórico", "ko": "기록 기반 생성"},
    "min_ago": {"zh": "分钟前", "en": "min ago", "ja": "分前", "fr": "min", "ru": "мин назад", "de": "Min. zuvor", "it": "min fa", "es": "min atrás", "pt": "min atrás", "ko": "분 전"},
    "expand_content": {"zh": "展开查看完整内容", "en": "Expand to see full content", "ja": "全文を表示", "fr": "Développer le contenu", "ru": "Развернуть", "de": "Vollständig anzeigen", "it": "Espandi contenuto", "es": "Expandir contenido", "pt": "Expandir conteúdo", "ko": "전체 내용 보기"},
    "collapse_content": {"zh": "收起内容", "en": "Collapse", "ja": "折りたたむ", "fr": "Réduire", "ru": "Свернуть", "de": "Einklappen", "it": "Comprimi", "es": "Contraer", "pt": "Recolher", "ko": "접기"},
    "cmd_drag_hint": {"zh": "拖拽到终端或点击运行", "en": "Drag to terminal or click Run", "ja": "ターミナルにドラッグまたは実行をクリック", "fr": "Glissez ou cliquez sur Exécuter", "ru": "Перетащите или нажмите Запустить", "de": "Zum Terminal ziehen oder Ausführen klicken", "it": "Trascina al terminale o clicca Esegui", "es": "Arrastre o haga clic en Ejecutar", "pt": "Arraste ou clique em Executar", "ko": "터미널로 드래그하거나 실행 클릭"},
    "run_summarize": {"zh": "执行并总结", "en": "Run & Summarize", "ja": "実行して要約", "fr": "Exécuter et résumer", "ru": "Выполнить и обобщить", "de": "Ausführen und zusammenfassen", "it": "Esegui e riassumi", "es": "Ejecutar y resumir", "pt": "Executar e resumir", "ko": "실행 및 요약"},
    "executing": {"zh": "正在执行并准备总结...", "en": "Executing and preparing summary...", "ja": "実行中、要約を準備中...", "fr": "Exécution et préparation du résumé...", "ru": "Выполнение и подготовка сводки...", "de": "Ausführung und Zusammenfassung wird vorbereitet...", "it": "Esecuzione e preparazione del riepilogo...", "es": "Ejecutando y preparando resumen...", "pt": "Executando e preparando resumo...", "ko": "실행 및 요약 준비 중..."},
    "analyzing_results": {"zh": "分析结果...", "en": "Analyzing results...", "ja": "結果を分析中...", "fr": "Analyse des résultats...", "ru": "Анализ результатов...", "de": "Ergebnisse analysieren...", "it": "Analisi dei risultati...", "es": "Analizando resultados...", "pt": "Analisando resultados...", "ko": "결과 분석 중..."},
    "cmd_dropped": {"zh": "命令已就位！点击运行执行。", "en": "Command dropped! Press Run to execute.", "ja": "コマンドがセットされました！実行をクリック。", "fr": "Commande déposée ! Appuyez sur Exécuter.", "ru": "Команда установлена! Нажмите Выполнить.", "de": "Befehl bereit! Zum Ausführen klicken.", "it": "Comando inserito! Premi Esegui.", "es": "¡Comando listo! Presione Ejecutar.", "pt": "Comando pronto! Pressione Executar.", "ko": "명령 준비 완료! 실행을 누르세요."},
    "upload_docs": {"zh": "上传文档", "en": "Upload Documents", "ja": "ドキュメントをアップロード", "fr": "Télécharger des documents", "ru": "Загрузить документы", "de": "Dokumente hochladen", "it": "Carica documenti", "es": "Subir documentos", "pt": "Enviar documentos", "ko": "문서 업로드"},
    "kb_name_label": {"zh": "知识库名称", "en": "Knowledge Base Name", "ja": "ナレッジベース名", "fr": "Nom de la base", "ru": "Имя базы знаний", "de": "Wissensbasis-Name", "it": "Nome base di conoscenza", "es": "Nombre de la base", "pt": "Nome da base", "ko": "지식 베이스 이름"},
    "upload_kb_placeholder": {"zh": "例如：我的Python笔记", "en": "e.g. My Python Notes", "ja": "例：私のPythonノート", "fr": "ex. Mes notes Python", "ru": "напр. Мои заметки Python", "de": "z.B. Meine Python-Notizen", "it": "es. Le mie note Python", "es": "ej. Mis notas de Python", "pt": "ex. Minhas notas Python", "ko": "예: 나의 Python 노트"},
    "select_files": {"zh": "选择文件 (.md, .txt)", "en": "Select Files (.md, .txt)", "ja": "ファイルを選択 (.md, .txt)", "fr": "Sélectionner des fichiers (.md, .txt)", "ru": "Выбрать файлы (.md, .txt)", "de": "Dateien wählen (.md, .txt)", "it": "Seleziona file (.md, .txt)", "es": "Seleccionar archivos (.md, .txt)", "pt": "Selecionar arquivos (.md, .txt)", "ko": "파일 선택 (.md, .txt)"},
    "upload_and_index": {"zh": "上传并索引", "en": "Upload & Index", "ja": "アップロードしてインデックス", "fr": "Télécharger et indexer", "ru": "Загрузить и индексировать", "de": "Hochladen und indexieren", "it": "Carica e indicizza", "es": "Subir e indexar", "pt": "Enviar e indexar", "ko": "업로드 및 인덱스"},
    "select_kbs": {"zh": "知识库范围", "en": "KB Scope", "ja": "KB範囲", "fr": "Portée KB", "ru": "Область БЗ", "de": "KB-Bereich", "it": "Ambito KB", "es": "Alcance KB", "pt": "Escopo KB", "ko": "KB 범위"},
    "all_kbs_selected": {"zh": "全部", "en": "All", "ja": "すべて", "fr": "Tout", "ru": "Все", "de": "Alle", "it": "Tutti", "es": "Todos", "pt": "Todos", "ko": "전체"},
    "none_selected": {"zh": "无", "en": "None", "ja": "なし", "fr": "Aucun", "ru": "Нет", "de": "Keine", "it": "Nessuno", "es": "Ninguno", "pt": "Nenhum", "ko": "없음"},
    "user_kb_type": {"zh": "用户", "en": "User", "ja": "ユーザー", "fr": "Utilisateur", "ru": "Пользователь", "de": "Benutzer", "it": "Utente", "es": "Usuario", "pt": "Usuário", "ko": "사용자"},
    "builtin_kb_type": {"zh": "内置", "en": "Built-in", "ja": "内蔵", "fr": "Intégré", "ru": "Встроенный", "de": "Eingebaut", "it": "Integrato", "es": "Integrado", "pt": "Integrado", "ko": "내장"},
    "strict_kb_mode": {"zh": "严格知识库模式", "en": "Strict KB Mode", "ja": "厳密KBモード", "fr": "Mode KB strict", "ru": "Строгий режим БЗ", "de": "Strenger KB-Modus", "it": "Modalità KB rigorosa", "es": "Modo KB estricto", "pt": "Modo KB estrito", "ko": "엄격 KB 모드"},
    "strict_kb_mode_desc": {"zh": "无检索结果时拒绝回答", "en": "Refuse to answer when no KB results", "ja": "KB結果がない場合は回答を拒否", "fr": "Refuser de répondre sans résultats KB", "ru": "Отказ от ответа без результатов БЗ", "de": "Antwort verweigern ohne KB-Ergebnisse", "it": "Rifiuta risposta senza risultati KB", "es": "Rechazar respuesta sin resultados KB", "pt": "Recusar resposta sem resultados KB", "ko": "KB 결과 없으면 답변 거부"},
    "kb_no_results_strict": {"zh": "抱歉，在知识库中未找到相关内容。严格模式下无法回答此问题。", "en": "Sorry, no relevant content found in the knowledge base. Cannot answer in strict mode.", "ja": "申し訳ありませんが、ナレッジベースに関連コンテンツが見つかりませんでした。厳密モードでは回答できません。", "fr": "Désolé, aucun contenu pertinent trouvé dans la base de connaissances. Impossible de répondre en mode strict.", "ru": "Извините, в базе знаний не найдено релевантного контента. В строгом режиме ответить невозможно.", "de": "Entschuldigung, keine relevanten Inhalte in der Wissensdatenbank gefunden. Im strengen Modus kann nicht geantwortet werden.", "it": "Spiacente, nessun contenuto rilevante trovato nella base di conoscenza. Impossibile rispondere in modalità rigorosa.", "es": "Lo siento, no se encontró contenido relevante en la base de conocimiento. No se puede responder en modo estricto.", "pt": "Desculpe, nenhum conteúdo relevante encontrado na base de conhecimento. Não é possível responder no modo estrito.", "ko": "죄송합니다. 지식 베이스에서 관련 콘텐츠를 찾을 수 없습니다. 엄격 모드에서는 답변할 수 없습니다."},
    "references": {"zh": "参考文献", "en": "References", "ja": "参考文献", "fr": "Références", "ru": "Ссылки", "de": "Referenzen", "it": "Riferimenti", "es": "Referencias", "pt": "Referências", "ko": "참고 문헌"},
    "duplicate_files_found": {"zh": "发现重复文件", "en": "Duplicate Files Found", "ja": "重複ファイルが見つかりました", "fr": "Fichiers en double trouvés", "ru": "Найдены дубликаты файлов", "de": "Doppelte Dateien gefunden", "it": "File duplicati trovati", "es": "Archivos duplicados encontrados", "pt": "Arquivos duplicados encontrados", "ko": "중복 파일 발견"},
    "duplicate_files_msg": {"zh": "以下文件已存在于知识库中：", "en": "The following files already exist in the knowledge base:", "ja": "以下のファイルはナレッジベースに既に存在します：", "fr": "Les fichiers suivants existent déjà dans la base de connaissances :", "ru": "Следующие файлы уже существуют в базе знаний:", "de": "Die folgenden Dateien existieren bereits in der Wissensdatenbank:", "it": "I seguenti file esistono già nella base di conoscenza:", "es": "Los siguientes archivos ya existen en la base de conocimiento:", "pt": "Os seguintes arquivos já existem na base de conhecimento:", "ko": "다음 파일이 이미 지식 베이스에 존재합니다:"},
    "skip_duplicates": {"zh": "跳过重复", "en": "Skip Duplicates", "ja": "重複をスキップ", "fr": "Ignorer les doublons", "ru": "Пропустить дубликаты", "de": "Duplikate überspringen", "it": "Salta duplicati", "es": "Omitir duplicados", "pt": "Pular duplicados", "ko": "중복 건너뛰기"},
    "overwrite_duplicates": {"zh": "覆盖重复", "en": "Overwrite Duplicates", "ja": "重複を上書き", "fr": "Écraser les doublons", "ru": "Перезаписать дубликаты", "de": "Duplikate überschreiben", "it": "Sovrascrivi duplicati", "es": "Sobrescribir duplicados", "pt": "Sobrescrever duplicados", "ko": "중복 덮어쓰기"},
    "cancel": {"zh": "取消", "en": "Cancel", "ja": "キャンセル", "fr": "Annuler", "ru": "Отмена", "de": "Abbrechen", "it": "Annulla", "es": "Cancelar", "pt": "Cancelar", "ko": "취소"},
    "files_skipped": {"zh": "已跳过 {0} 个重复文件", "en": "{0} duplicate file(s) skipped", "ja": "{0}個の重複ファイルをスキップしました", "fr": "{0} fichier(s) en double ignoré(s)", "ru": "Пропущено {0} дубликат(ов)", "de": "{0} Duplikat(e) übersprungen", "it": "{0} file duplicato/i saltato/i", "es": "{0} archivo(s) duplicado(s) omitido(s)", "pt": "{0} arquivo(s) duplicado(s) pulado(s)", "ko": "중복 파일 {0}개 건너뛰기"},
    "files_overwritten": {"zh": "已覆盖 {0} 个文件", "en": "{0} file(s) overwritten", "ja": "{0}個のファイルを上書きしました", "fr": "{0} fichier(s) écrasé(s)", "ru": "Перезаписано {0} файл(ов)", "de": "{0} Datei(en) überschrieben", "it": "{0} file sovrascritto/i", "es": "{0} archivo(s) sobrescrito(s)", "pt": "{0} arquivo(s) sobrescrito(s)", "ko": "파일 {0}개 덮어씀"},
    "dark_theme": {"zh": "暗色主题", "en": "Dark Theme", "ja": "ダークテーマ", "fr": "Thème sombre", "ru": "Тёмная тема", "de": "Dunkles Design", "it": "Tema scuro", "es": "Tema oscuro", "pt": "Tema escuro", "ko": "다크 테마"},
    "light_theme": {"zh": "亮色主题", "en": "Light Theme", "ja": "ライトテーマ", "fr": "Thème clair", "ru": "Светлая тема", "de": "Helles Design", "it": "Tema chiaro", "es": "Tema claro", "pt": "Tema claro", "ko": "라이트 테마"},
    "toggle_theme": {"zh": "切换主题", "en": "Toggle Theme", "ja": "テーマ切替", "fr": "Changer de thème", "ru": "Переключить тему", "de": "Design wechseln", "it": "Cambia tema", "es": "Cambiar tema", "pt": "Alternar tema", "ko": "테마 전환"},
    # LLM Provider Settings
    "llm_provider": {"zh": "LLM 提供商", "en": "LLM Provider", "ja": "LLMプロバイダー", "fr": "Fournisseur LLM", "ru": "Провайдер LLM", "de": "LLM-Anbieter", "it": "Provider LLM", "es": "Proveedor LLM", "pt": "Provedor LLM", "ko": "LLM 공급자"},
    "llm_provider_desc": {"zh": "选择 LLM 提供商", "en": "Select LLM provider", "ja": "LLMプロバイダーを選択", "fr": "Choisir le fournisseur LLM", "ru": "Выберите провайдера LLM", "de": "LLM-Anbieter wählen", "it": "Seleziona provider LLM", "es": "Seleccionar proveedor LLM", "pt": "Selecionar provedor LLM", "ko": "LLM 공급자 선택"},
    "api_key": {"zh": "API 密钥", "en": "API Key", "ja": "APIキー", "fr": "Clé API", "ru": "API ключ", "de": "API-Schlüssel", "it": "Chiave API", "es": "Clave API", "pt": "Chave API", "ko": "API 키"},
    "api_key_placeholder": {"zh": "输入 API 密钥", "en": "Enter API key", "ja": "APIキーを入力", "fr": "Entrez la clé API", "ru": "Введите API ключ", "de": "API-Schlüssel eingeben", "it": "Inserisci chiave API", "es": "Introducir clave API", "pt": "Digite a chave API", "ko": "API 키 입력"},
    "api_base_url": {"zh": "API 地址", "en": "API Base URL", "ja": "APIベースURL", "fr": "URL de base API", "ru": "Базовый URL API", "de": "API-Basis-URL", "it": "URL base API", "es": "URL base API", "pt": "URL base API", "ko": "API 기본 URL"},
    "api_base_url_placeholder": {"zh": "自定义 API 端点", "en": "Custom API endpoint", "ja": "カスタムAPIエンドポイント", "fr": "Point de terminaison API personnalisé", "ru": "Пользовательская конечная точка API", "de": "Benutzerdefinierter API-Endpunkt", "it": "Endpoint API personalizzato", "es": "Endpoint API personalizado", "pt": "Endpoint API personalizado", "ko": "사용자 정의 API 엔드포인트"},
    "provider_ollama": {"zh": "Ollama (本地)", "en": "Ollama (Local)", "ja": "Ollama (ローカル)", "fr": "Ollama (Local)", "ru": "Ollama (Локальный)", "de": "Ollama (Lokal)", "it": "Ollama (Locale)", "es": "Ollama (Local)", "pt": "Ollama (Local)", "ko": "Ollama (로컬)"},
    "provider_openai": {"zh": "OpenAI", "en": "OpenAI", "ja": "OpenAI", "fr": "OpenAI", "ru": "OpenAI", "de": "OpenAI", "it": "OpenAI", "es": "OpenAI", "pt": "OpenAI", "ko": "OpenAI"},
    "provider_dashscope": {"zh": "通义千问 (DashScope)", "en": "Qwen (DashScope)", "ja": "Qwen (DashScope)", "fr": "Qwen (DashScope)", "ru": "Qwen (DashScope)", "de": "Qwen (DashScope)", "it": "Qwen (DashScope)", "es": "Qwen (DashScope)", "pt": "Qwen (DashScope)", "ko": "Qwen (DashScope)"},
    "provider_deepseek": {"zh": "DeepSeek", "en": "DeepSeek", "ja": "DeepSeek", "fr": "DeepSeek", "ru": "DeepSeek", "de": "DeepSeek", "it": "DeepSeek", "es": "DeepSeek", "pt": "DeepSeek", "ko": "DeepSeek"},
    "provider_moonshot": {"zh": "月之暗面 (Moonshot)", "en": "Moonshot", "ja": "Moonshot", "fr": "Moonshot", "ru": "Moonshot", "de": "Moonshot", "it": "Moonshot", "es": "Moonshot", "pt": "Moonshot", "ko": "Moonshot"},
    "provider_zhipu": {"zh": "智谱 AI", "en": "Zhipu AI", "ja": "Zhipu AI", "fr": "Zhipu AI", "ru": "Zhipu AI", "de": "Zhipu AI", "it": "Zhipu AI", "es": "Zhipu AI", "pt": "Zhipu AI", "ko": "Zhipu AI"},
    "provider_siliconflow": {"zh": "硅基流动", "en": "SiliconFlow", "ja": "SiliconFlow", "fr": "SiliconFlow", "ru": "SiliconFlow", "de": "SiliconFlow", "it": "SiliconFlow", "es": "SiliconFlow", "pt": "SiliconFlow", "ko": "SiliconFlow"},
    "provider_custom": {"zh": "自定义", "en": "Custom", "ja": "カスタム", "fr": "Personnalisé", "ru": "Пользовательский", "de": "Benutzerdefiniert", "it": "Personalizzato", "es": "Personalizado", "pt": "Personalizado", "ko": "사용자 정의"},
    "api_key_required": {"zh": "此提供商需要 API 密钥", "en": "API key required for this provider", "ja": "このプロバイダーにはAPIキーが必要です", "fr": "Clé API requise pour ce fournisseur", "ru": "Для этого провайдера требуется API ключ", "de": "Für diesen Anbieter ist ein API-Schlüssel erforderlich", "it": "Chiave API richiesta per questo provider", "es": "Se requiere clave API para este proveedor", "pt": "Chave API necessária para este provedor", "ko": "이 공급자에는 API 키가 필요합니다"},
    "connection_test_success": {"zh": "连接成功", "en": "Connection successful", "ja": "接続成功", "fr": "Connexion réussie", "ru": "Подключение успешно", "de": "Verbindung erfolgreich", "it": "Connessione riuscita", "es": "Conexión exitosa", "pt": "Conexão bem-sucedida", "ko": "연결 성공"},
    "connection_test_failed": {"zh": "连接失败", "en": "Connection failed", "ja": "接続失敗", "fr": "Échec de la connexion", "ru": "Ошибка подключения", "de": "Verbindung fehlgeschlagen", "it": "Connessione fallita", "es": "Conexión fallida", "pt": "Falha na conexão", "ko": "연결 실패"},
    # Learning Module - Navigation
    "learning_features": {"zh": "学习功能", "en": "Learning", "ja": "学習", "fr": "Apprentissage", "ru": "Обучение", "de": "Lernen", "it": "Apprendimento", "es": "Aprendizaje", "pt": "Aprendizagem", "ko": "학습"},
    "question_generator": {"zh": "出题练习", "en": "Question Generator", "ja": "問題生成", "fr": "Générateur de questions", "ru": "Генератор вопросов", "de": "Fragengenerator", "it": "Generatore domande", "es": "Generador de preguntas", "pt": "Gerador de questões", "ko": "문제 생성"},
    "guided_learning": {"zh": "引导学习", "en": "Guided Learning", "ja": "ガイド学習", "fr": "Apprentissage guidé", "ru": "Управляемое обучение", "de": "Geführtes Lernen", "it": "Apprendimento guidato", "es": "Aprendizaje guiado", "pt": "Aprendizagem guiada", "ko": "가이드 학습"},
    "deep_research": {"zh": "深度研究", "en": "Deep Research", "ja": "深層研究", "fr": "Recherche approfondie", "ru": "Глубокое исследование", "de": "Tiefenforschung", "it": "Ricerca approfondita", "es": "Investigación profunda", "pt": "Pesquisa profunda", "ko": "심층 연구"},
    "back_to_main": {"zh": "返回主页", "en": "Back to Main", "ja": "メインに戻る", "fr": "Retour", "ru": "Назад", "de": "Zurück", "it": "Torna indietro", "es": "Volver", "pt": "Voltar", "ko": "메인으로"},
    # Learning Module - Question Generator
    "question_topic": {"zh": "出题主题", "en": "Topic", "ja": "トピック", "fr": "Sujet", "ru": "Тема", "de": "Thema", "it": "Argomento", "es": "Tema", "pt": "Tópico", "ko": "주제"},
    "question_topic_placeholder": {"zh": "例如：机器学习基础", "en": "e.g. Machine Learning Basics", "ja": "例：機械学習の基礎", "fr": "ex. Bases du ML", "ru": "напр. Основы ML", "de": "z.B. ML-Grundlagen", "it": "es. Basi del ML", "es": "ej. Bases de ML", "pt": "ex. Bases de ML", "ko": "예: ML 기초"},
    "question_count": {"zh": "题目数量", "en": "Number of Questions", "ja": "問題数", "fr": "Nombre de questions", "ru": "Количество вопросов", "de": "Fragenanzahl", "it": "Numero domande", "es": "Número de preguntas", "pt": "Número de questões", "ko": "문제 수"},
    "question_type": {"zh": "题型", "en": "Question Type", "ja": "問題タイプ", "fr": "Type de question", "ru": "Тип вопроса", "de": "Fragetyp", "it": "Tipo domanda", "es": "Tipo de pregunta", "pt": "Tipo de questão", "ko": "문제 유형"},
    "question_type_choice": {"zh": "选择题", "en": "Multiple Choice", "ja": "選択問題", "fr": "Choix multiple", "ru": "Выбор", "de": "Mehrfachauswahl", "it": "Scelta multipla", "es": "Opción múltiple", "pt": "Múltipla escolha", "ko": "객관식"},
    "question_type_written": {"zh": "简答题", "en": "Short Answer", "ja": "記述式", "fr": "Réponse courte", "ru": "Краткий ответ", "de": "Kurzantwort", "it": "Risposta breve", "es": "Respuesta corta", "pt": "Resposta curta", "ko": "단답형"},
    "question_type_fill_blank": {"zh": "填空题", "en": "Fill in the Blank", "ja": "穴埋め", "fr": "Texte à trous", "ru": "Заполните пробел", "de": "Lückentext", "it": "Riempi spazi", "es": "Rellenar espacio", "pt": "Preencher lacuna", "ko": "빈칸 채우기"},
    "question_type_true_false": {"zh": "判断题", "en": "True/False", "ja": "正誤問題", "fr": "Vrai/Faux", "ru": "Верно/Неверно", "de": "Wahr/Falsch", "it": "Vero/Falso", "es": "Verdadero/Falso", "pt": "Verdadeiro/Falso", "ko": "참/거짓"},
    "difficulty": {"zh": "难度", "en": "Difficulty", "ja": "難易度", "fr": "Difficulté", "ru": "Сложность", "de": "Schwierigkeit", "it": "Difficoltà", "es": "Dificultad", "pt": "Dificuldade", "ko": "난이도"},
    "difficulty_easy": {"zh": "简单", "en": "Easy", "ja": "簡単", "fr": "Facile", "ru": "Легко", "de": "Einfach", "it": "Facile", "es": "Fácil", "pt": "Fácil", "ko": "쉬움"},
    "difficulty_medium": {"zh": "中等", "en": "Medium", "ja": "普通", "fr": "Moyen", "ru": "Средне", "de": "Mittel", "it": "Medio", "es": "Medio", "pt": "Médio", "ko": "보통"},
    "difficulty_hard": {"zh": "困难", "en": "Hard", "ja": "難しい", "fr": "Difficile", "ru": "Сложно", "de": "Schwer", "it": "Difficile", "es": "Difícil", "pt": "Difícil", "ko": "어려움"},
    "generate_questions": {"zh": "生成题目", "en": "Generate Questions", "ja": "問題を生成", "fr": "Générer des questions", "ru": "Генерировать вопросы", "de": "Fragen generieren", "it": "Genera domande", "es": "Generar preguntas", "pt": "Gerar questões", "ko": "문제 생성"},
    "generating_questions": {"zh": "正在生成题目...", "en": "Generating questions...", "ja": "問題を生成中...", "fr": "Génération en cours...", "ru": "Генерация вопросов...", "de": "Fragen werden generiert...", "it": "Generazione in corso...", "es": "Generando preguntas...", "pt": "Gerando questões...", "ko": "문제 생성 중..."},
    "show_answer": {"zh": "显示答案", "en": "Show Answer", "ja": "答えを表示", "fr": "Afficher la réponse", "ru": "Показать ответ", "de": "Antwort anzeigen", "it": "Mostra risposta", "es": "Mostrar respuesta", "pt": "Mostrar resposta", "ko": "답 보기"},
    "hide_answer": {"zh": "隐藏答案", "en": "Hide Answer", "ja": "答えを隠す", "fr": "Masquer la réponse", "ru": "Скрыть ответ", "de": "Antwort verbergen", "it": "Nascondi risposta", "es": "Ocultar respuesta", "pt": "Ocultar resposta", "ko": "답 숨기기"},
    "no_kb_selected": {"zh": "请先选择知识库", "en": "Please select a knowledge base first", "ja": "まずナレッジベースを選択してください", "fr": "Veuillez d'abord sélectionner une base", "ru": "Сначала выберите базу знаний", "de": "Bitte zuerst eine KB auswählen", "it": "Seleziona prima una base di conoscenza", "es": "Seleccione primero una base de conocimiento", "pt": "Selecione primeiro uma base de conhecimento", "ko": "먼저 지식 베이스를 선택하세요"},
    "saved_batches": {"zh": "历史记录", "en": "History", "ja": "履歴", "fr": "Historique", "ru": "История", "de": "Verlauf", "it": "Cronologia", "es": "Historial", "pt": "Histórico", "ko": "기록"},
    # Learning Module - Guided Learning
    "select_kb_learn": {"zh": "选择知识库开始学习", "en": "Select KB to Start Learning", "ja": "KBを選んで学習開始", "fr": "Sélectionner une KB pour apprendre", "ru": "Выберите БЗ для обучения", "de": "KB zum Lernen auswählen", "it": "Seleziona KB per studiare", "es": "Seleccione KB para aprender", "pt": "Selecione KB para aprender", "ko": "학습할 KB 선택"},
    "create_session": {"zh": "创建学习计划", "en": "Create Learning Plan", "ja": "学習プラン作成", "fr": "Créer un plan d'apprentissage", "ru": "Создать план обучения", "de": "Lernplan erstellen", "it": "Crea piano di studio", "es": "Crear plan de aprendizaje", "pt": "Criar plano de aprendizagem", "ko": "학습 계획 만들기"},
    "creating_session": {"zh": "正在分析知识库...", "en": "Analyzing knowledge base...", "ja": "ナレッジベースを分析中...", "fr": "Analyse de la base...", "ru": "Анализ базы знаний...", "de": "Wissensbasis wird analysiert...", "it": "Analisi della base...", "es": "Analizando la base...", "pt": "Analisando a base...", "ko": "지식 베이스 분석 중..."},
    "start_learning": {"zh": "开始学习", "en": "Start Learning", "ja": "学習開始", "fr": "Commencer", "ru": "Начать обучение", "de": "Lernen starten", "it": "Inizia a studiare", "es": "Empezar", "pt": "Começar", "ko": "학습 시작"},
    "next_point": {"zh": "下一个知识点", "en": "Next Point", "ja": "次へ", "fr": "Suivant", "ru": "Далее", "de": "Weiter", "it": "Prossimo", "es": "Siguiente", "pt": "Próximo", "ko": "다음"},
    "lesson_content": {"zh": "教学内容", "en": "Lesson Content", "ja": "授業内容", "fr": "Contenu de la leçon", "ru": "Содержание урока", "de": "Lektionsinhalt", "it": "Contenuto lezione", "es": "Contenido de lección", "pt": "Conteúdo da lição", "ko": "수업 내용"},
    "ask_question": {"zh": "提问...", "en": "Ask a question...", "ja": "質問する...", "fr": "Poser une question...", "ru": "Задать вопрос...", "de": "Frage stellen...", "it": "Fai una domanda...", "es": "Hacer pregunta...", "pt": "Fazer pergunta...", "ko": "질문하기..."},
    "learning_progress": {"zh": "学习进度", "en": "Progress", "ja": "進捗", "fr": "Progression", "ru": "Прогресс", "de": "Fortschritt", "it": "Progresso", "es": "Progreso", "pt": "Progresso", "ko": "진도"},
    "learning_complete": {"zh": "学习完成！", "en": "Learning Complete!", "ja": "学習完了！", "fr": "Apprentissage terminé !", "ru": "Обучение завершено!", "de": "Lernen abgeschlossen!", "it": "Studio completato!", "es": "¡Aprendizaje completo!", "pt": "Aprendizagem completa!", "ko": "학습 완료!"},
    "generate_summary": {"zh": "生成学习总结", "en": "Generate Summary", "ja": "まとめを生成", "fr": "Générer un résumé", "ru": "Создать итог", "de": "Zusammenfassung erstellen", "it": "Genera riepilogo", "es": "Generar resumen", "pt": "Gerar resumo", "ko": "요약 생성"},
    "knowledge_point": {"zh": "知识点", "en": "Knowledge Point", "ja": "知識ポイント", "fr": "Point de connaissance", "ru": "Тема", "de": "Wissenspunkt", "it": "Punto di conoscenza", "es": "Punto de conocimiento", "pt": "Ponto de conhecimento", "ko": "학습 포인트"},
    "resume_session": {"zh": "继续学习", "en": "Resume", "ja": "再開", "fr": "Reprendre", "ru": "Продолжить", "de": "Fortsetzen", "it": "Riprendi", "es": "Continuar", "pt": "Retomar", "ko": "이어서"},
    "session_list": {"zh": "学习记录", "en": "Sessions", "ja": "セッション", "fr": "Sessions", "ru": "Сессии", "de": "Sitzungen", "it": "Sessioni", "es": "Sesiones", "pt": "Sessões", "ko": "세션"},
    # Learning Module - Deep Research
    "research_topic": {"zh": "研究主题", "en": "Research Topic", "ja": "研究トピック", "fr": "Sujet de recherche", "ru": "Тема исследования", "de": "Forschungsthema", "it": "Argomento di ricerca", "es": "Tema de investigación", "pt": "Tópico de pesquisa", "ko": "연구 주제"},
    "research_topic_placeholder": {"zh": "例如：深度学习在NLP中的应用", "en": "e.g. Deep Learning in NLP", "ja": "例：NLPにおける深層学習", "fr": "ex. Deep Learning en NLP", "ru": "напр. DL в NLP", "de": "z.B. Deep Learning in NLP", "it": "es. Deep Learning in NLP", "es": "ej. Deep Learning en NLP", "pt": "ex. Deep Learning em NLP", "ko": "예: NLP에서의 딥러닝"},
    "research_depth": {"zh": "研究深度", "en": "Research Depth", "ja": "研究深度", "fr": "Profondeur", "ru": "Глубина", "de": "Forschungstiefe", "it": "Profondità", "es": "Profundidad", "pt": "Profundidade", "ko": "연구 깊이"},
    "depth_quick": {"zh": "快速 (2-3个子主题)", "en": "Quick (2-3 subtopics)", "ja": "クイック (2-3)", "fr": "Rapide (2-3)", "ru": "Быстро (2-3)", "de": "Schnell (2-3)", "it": "Veloce (2-3)", "es": "Rápido (2-3)", "pt": "Rápido (2-3)", "ko": "빠름 (2-3)"},
    "depth_medium": {"zh": "中等 (4-5个子主题)", "en": "Medium (4-5 subtopics)", "ja": "標準 (4-5)", "fr": "Moyen (4-5)", "ru": "Средне (4-5)", "de": "Mittel (4-5)", "it": "Medio (4-5)", "es": "Medio (4-5)", "pt": "Médio (4-5)", "ko": "보통 (4-5)"},
    "depth_deep": {"zh": "深度 (5-7个子主题)", "en": "Deep (5-7 subtopics)", "ja": "深層 (5-7)", "fr": "Profond (5-7)", "ru": "Глубоко (5-7)", "de": "Tief (5-7)", "it": "Profondo (5-7)", "es": "Profundo (5-7)", "pt": "Profundo (5-7)", "ko": "심층 (5-7)"},
    "depth_auto": {"zh": "自动（迭代深度）", "en": "Auto (iterative deep)", "ja": "自動（反復深層）", "fr": "Auto (itératif)", "ru": "Авто (итеративно)", "de": "Auto (iterativ)", "it": "Auto (iterativo)", "es": "Auto (iterativo)", "pt": "Auto (iterativo)", "ko": "자동 (반복 심층)"},
    "start_research": {"zh": "开始研究", "en": "Start Research", "ja": "研究開始", "fr": "Commencer la recherche", "ru": "Начать исследование", "de": "Forschung starten", "it": "Inizia ricerca", "es": "Iniciar investigación", "pt": "Iniciar pesquisa", "ko": "연구 시작"},
    "planning_phase": {"zh": "规划阶段", "en": "Planning", "ja": "計画中", "fr": "Planification", "ru": "Планирование", "de": "Planung", "it": "Pianificazione", "es": "Planificación", "pt": "Planejamento", "ko": "계획"},
    "rephrasing_phase": {"zh": "优化主题", "en": "Rephrasing", "ja": "トピック最適化", "fr": "Reformulation", "ru": "Перефразирование", "de": "Umformulierung", "it": "Riformulazione", "es": "Reformulación", "pt": "Reformulação", "ko": "주제 최적화"},
    "enable_web_search": {"zh": "启用网络搜索", "en": "Enable Web Search", "ja": "ウェブ検索を有効化", "fr": "Activer la recherche web", "ru": "Включить веб-поиск", "de": "Websuche aktivieren", "it": "Abilita ricerca web", "es": "Activar búsqueda web", "pt": "Ativar busca web", "ko": "웹 검색 활성화"},
    "refining_phase": {"zh": "深化研究", "en": "Refining", "ja": "精査中", "fr": "Affinement", "ru": "Уточнение", "de": "Verfeinerung", "it": "Raffinamento", "es": "Refinamiento", "pt": "Refinamento", "ko": "심화"},
    "evaluating_findings": {"zh": "正在评估研究结果...", "en": "Evaluating findings...", "ja": "調査結果を評価中...", "fr": "Évaluation des résultats...", "ru": "Оценка результатов...", "de": "Ergebnisse werden bewertet...", "it": "Valutazione dei risultati...", "es": "Evaluando resultados...", "pt": "Avaliando resultados...", "ko": "연구 결과 평가 중..."},
    "expanding_research": {"zh": "正在扩展研究...", "en": "Expanding research...", "ja": "調査を拡大中...", "fr": "Extension de la recherche...", "ru": "Расширение исследования...", "de": "Forschung wird erweitert...", "it": "Estensione della ricerca...", "es": "Ampliando investigación...", "pt": "Expandindo pesquisa...", "ko": "연구 확장 중..."},
    "findings_sufficient": {"zh": "研究结果充分", "en": "Findings sufficient", "ja": "調査結果十分", "fr": "Résultats suffisants", "ru": "Результаты достаточны", "de": "Ergebnisse ausreichend", "it": "Risultati sufficienti", "es": "Resultados suficientes", "pt": "Resultados suficientes", "ko": "연구 결과 충분"},
    "web_unavailable": {"zh": "网络搜索不可用，仅使用知识库", "en": "Web search unavailable, using KB only", "ja": "ウェブ検索不可、KB のみ使用", "fr": "Recherche web indisponible, KB uniquement", "ru": "Веб-поиск недоступен, только БЗ", "de": "Websuche nicht verfügbar, nur KB", "it": "Ricerca web non disponibile, solo KB", "es": "Búsqueda web no disponible, solo KB", "pt": "Busca web indisponível, apenas KB", "ko": "웹 검색 불가, KB만 사용"},
    "researching_phase": {"zh": "研究阶段", "en": "Researching", "ja": "調査中", "fr": "Recherche", "ru": "Исследование", "de": "Forschung", "it": "Ricerca", "es": "Investigando", "pt": "Pesquisando", "ko": "연구 중"},
    "reporting_phase": {"zh": "报告阶段", "en": "Reporting", "ja": "報告作成中", "fr": "Rédaction", "ru": "Отчёт", "de": "Berichterstellung", "it": "Stesura", "es": "Redacción", "pt": "Relatório", "ko": "보고서"},
    "research_complete": {"zh": "研究完成", "en": "Research Complete", "ja": "研究完了", "fr": "Recherche terminée", "ru": "Исследование завершено", "de": "Forschung abgeschlossen", "it": "Ricerca completata", "es": "Investigación completa", "pt": "Pesquisa completa", "ko": "연구 완료"},
    "export_report": {"zh": "导出报告", "en": "Export Report", "ja": "レポートをエクスポート", "fr": "Exporter le rapport", "ru": "Экспорт отчёта", "de": "Bericht exportieren", "it": "Esporta rapporto", "es": "Exportar informe", "pt": "Exportar relatório", "ko": "보고서 내보내기"},
    "copy_report": {"zh": "复制报告", "en": "Copy Report", "ja": "レポートをコピー", "fr": "Copier le rapport", "ru": "Копировать отчёт", "de": "Bericht kopieren", "it": "Copia rapporto", "es": "Copiar informe", "pt": "Copiar relatório", "ko": "보고서 복사"},
    "subtopic": {"zh": "子主题", "en": "Subtopic", "ja": "サブトピック", "fr": "Sous-sujet", "ru": "Подтема", "de": "Unterthema", "it": "Sotto-argomento", "es": "Subtema", "pt": "Subtópico", "ko": "하위 주제"},
    "saved_reports": {"zh": "历史报告", "en": "Saved Reports", "ja": "保存済みレポート", "fr": "Rapports sauvegardés", "ru": "Сохранённые отчёты", "de": "Gespeicherte Berichte", "it": "Rapporti salvati", "es": "Informes guardados", "pt": "Relatórios salvos", "ko": "저장된 보고서"},
    "no_chat_model": {"zh": "请先在设置中配置聊天模型", "en": "Please configure a chat model in Settings first", "ja": "まず設定でチャットモデルを設定してください", "fr": "Veuillez d'abord configurer un modèle de chat", "ru": "Сначала настройте модель чата", "de": "Bitte zuerst Chat-Modell konfigurieren", "it": "Configura prima un modello di chat", "es": "Configure primero un modelo de chat", "pt": "Configure primeiro um modelo de chat", "ko": "먼저 채팅 모델을 설정하세요"},
    # Learning Module - Lecture Maker
    "lecture_maker": {"zh": "讲义制作", "en": "Lecture Maker", "ja": "講義作成", "fr": "Cr\u00e9ateur de cours", "ru": "Создание лекций", "de": "Vorlesungsersteller", "it": "Creatore lezioni", "es": "Creador de lecciones", "pt": "Criador de aulas", "ko": "강의 제작"},
    "lecture_topic": {"zh": "讲义主题", "en": "Lecture Topic", "ja": "講義トピック", "fr": "Sujet du cours", "ru": "Тема лекции", "de": "Vorlesungsthema", "it": "Argomento lezione", "es": "Tema de la lecci\u00f3n", "pt": "T\u00f3pico da aula", "ko": "강의 주제"},
    "lecture_topic_placeholder": {"zh": "例如：Python面向对象编程", "en": "e.g. Python OOP Concepts", "ja": "例：PythonのOOP概念", "fr": "ex. Concepts POO Python", "ru": "напр. Концепции ООП Python", "de": "z.B. Python OOP-Konzepte", "it": "es. Concetti OOP Python", "es": "ej. Conceptos POO Python", "pt": "ex. Conceitos POO Python", "ko": "예: Python OOP 개념"},
    "generate_lecture": {"zh": "生成讲义", "en": "Generate Lecture", "ja": "講義を生成", "fr": "G\u00e9n\u00e9rer le cours", "ru": "Создать лекцию", "de": "Vorlesung generieren", "it": "Genera lezione", "es": "Generar lecci\u00f3n", "pt": "Gerar aula", "ko": "강의 생성"},
    "analyzing_phase": {"zh": "分析", "en": "Analyzing", "ja": "分析中", "fr": "Analyse", "ru": "Анализ", "de": "Analyse", "it": "Analisi", "es": "An\u00e1lisis", "pt": "An\u00e1lise", "ko": "분석"},
    "outlining_phase": {"zh": "大纲", "en": "Outlining", "ja": "アウトライン", "fr": "Plan", "ru": "Структура", "de": "Gliederung", "it": "Schema", "es": "Esquema", "pt": "Estrutura", "ko": "개요"},
    "writing_phase": {"zh": "撰写", "en": "Writing", "ja": "執筆中", "fr": "R\u00e9daction", "ru": "Написание", "de": "Schreiben", "it": "Scrittura", "es": "Redacci\u00f3n", "pt": "Reda\u00e7\u00e3o", "ko": "작성"},
    "summarizing_phase": {"zh": "总结", "en": "Summarizing", "ja": "要約中", "fr": "R\u00e9sum\u00e9", "ru": "Итоги", "de": "Zusammenfassung", "it": "Riepilogo", "es": "Resumen", "pt": "Resumo", "ko": "요약"},
    "saved_lectures": {"zh": "历史讲义", "en": "Saved Lectures", "ja": "保存済み講義", "fr": "Cours sauvegard\u00e9s", "ru": "Сохранённые лекции", "de": "Gespeicherte Vorlesungen", "it": "Lezioni salvate", "es": "Lecciones guardadas", "pt": "Aulas salvas", "ko": "저장된 강의"},
    "export_lecture": {"zh": "导出讲义", "en": "Export Lecture", "ja": "講義をエクスポート", "fr": "Exporter le cours", "ru": "Экспорт лекции", "de": "Vorlesung exportieren", "it": "Esporta lezione", "es": "Exportar lecci\u00f3n", "pt": "Exportar aula", "ko": "강의 내보내기"},
    "copy_lecture": {"zh": "复制讲义", "en": "Copy Lecture", "ja": "講義をコピー", "fr": "Copier le cours", "ru": "Копировать лекцию", "de": "Vorlesung kopieren", "it": "Copia lezione", "es": "Copiar lecci\u00f3n", "pt": "Copiar aula", "ko": "강의 복사"},
    "lecture_complete": {"zh": "讲义生成完成", "en": "Lecture Complete", "ja": "講義完了", "fr": "Cours termin\u00e9", "ru": "Лекция готова", "de": "Vorlesung fertig", "it": "Lezione completata", "es": "Lecci\u00f3n completa", "pt": "Aula completa", "ko": "강의 완료"},
    # Learning Module - Exam Generator
    "exam_generator": {"zh": "试卷生成", "en": "Exam Generator", "ja": "試験作成", "fr": "G\u00e9n\u00e9rateur d'examen", "ru": "Генератор экзаменов", "de": "Pr\u00fcfungsgenerator", "it": "Generatore esami", "es": "Generador de ex\u00e1menes", "pt": "Gerador de provas", "ko": "시험 생성"},
    "exam_topic": {"zh": "考试主题", "en": "Exam Topic", "ja": "試験トピック", "fr": "Sujet d'examen", "ru": "Тема экзамена", "de": "Pr\u00fcfungsthema", "it": "Argomento esame", "es": "Tema de examen", "pt": "T\u00f3pico da prova", "ko": "시험 주제"},
    "exam_topic_placeholder": {"zh": "例如：数据结构与算法", "en": "e.g. Data Structures & Algorithms", "ja": "例：データ構造とアルゴリズム", "fr": "ex. Structures de donn\u00e9es", "ru": "напр. Структуры данных", "de": "z.B. Datenstrukturen", "it": "es. Strutture dati", "es": "ej. Estructuras de datos", "pt": "ex. Estruturas de dados", "ko": "예: 자료구조와 알고리즘"},
    "generate_exam": {"zh": "生成试卷", "en": "Generate Exam", "ja": "試験を生成", "fr": "G\u00e9n\u00e9rer l'examen", "ru": "Создать экзамен", "de": "Pr\u00fcfung generieren", "it": "Genera esame", "es": "Generar examen", "pt": "Gerar prova", "ko": "시험 생성"},
    "generating_phase": {"zh": "生成中", "en": "Generating", "ja": "生成中", "fr": "G\u00e9n\u00e9ration", "ru": "Генерация", "de": "Generierung", "it": "Generazione", "es": "Generando", "pt": "Gerando", "ko": "생성 중"},
    "answer_key_phase": {"zh": "答案", "en": "Answer Key", "ja": "解答", "fr": "Corrig\u00e9", "ru": "Ключ ответов", "de": "L\u00f6sungen", "it": "Risposte", "es": "Respuestas", "pt": "Gabarito", "ko": "정답"},
    "formatting_phase": {"zh": "格式化", "en": "Formatting", "ja": "フォーマット", "fr": "Formatage", "ru": "Форматирование", "de": "Formatierung", "it": "Formattazione", "es": "Formato", "pt": "Formata\u00e7\u00e3o", "ko": "서식"},
    "saved_exams": {"zh": "历史试卷", "en": "Saved Exams", "ja": "保存済み試験", "fr": "Examens sauvegard\u00e9s", "ru": "Сохранённые экзамены", "de": "Gespeicherte Pr\u00fcfungen", "it": "Esami salvati", "es": "Ex\u00e1menes guardados", "pt": "Provas salvas", "ko": "저장된 시험"},
    "exam_paper_tab": {"zh": "试卷", "en": "Exam Paper", "ja": "試験用紙", "fr": "Sujet", "ru": "Билет", "de": "Pr\u00fcfungsbogen", "it": "Foglio esame", "es": "Examen", "pt": "Prova", "ko": "시험지"},
    "answer_key_tab": {"zh": "答案", "en": "Answer Key", "ja": "解答", "fr": "Corrig\u00e9", "ru": "Ответы", "de": "L\u00f6sungen", "it": "Risposte", "es": "Respuestas", "pt": "Gabarito", "ko": "정답"},
    "export_paper": {"zh": "导出试卷", "en": "Export Paper", "ja": "試験をエクスポート", "fr": "Exporter le sujet", "ru": "Экспорт билета", "de": "Pr\u00fcfung exportieren", "it": "Esporta esame", "es": "Exportar examen", "pt": "Exportar prova", "ko": "시험지 내보내기"},
    "export_answer_key": {"zh": "导出答案", "en": "Export Answers", "ja": "解答をエクスポート", "fr": "Exporter le corrig\u00e9", "ru": "Экспорт ответов", "de": "Antworten exportieren", "it": "Esporta risposte", "es": "Exportar respuestas", "pt": "Exportar gabarito", "ko": "정답 내보내기"},
    "exam_complete": {"zh": "试卷生成完成", "en": "Exam Complete", "ja": "試験完了", "fr": "Examen termin\u00e9", "ru": "Экзамен готов", "de": "Pr\u00fcfung fertig", "it": "Esame completato", "es": "Examen completo", "pt": "Prova completa", "ko": "시험 완료"},
    "images": {"zh": "图片", "en": "Images", "ja": "画像", "fr": "Images", "ru": "Изображения", "de": "Bilder", "it": "Immagini", "es": "Imágenes", "pt": "Imagens", "ko": "이미지"},
    "process_images": {"zh": "处理图片", "en": "Process Images", "ja": "画像を処理", "fr": "Traiter les images", "ru": "Обработать изображения", "de": "Bilder verarbeiten", "it": "Elabora immagini", "es": "Procesar imágenes", "pt": "Processar imagens", "ko": "이미지 처리"},
    "image_not_found": {"zh": "图片未找到", "en": "Image not found", "ja": "画像が見つかりません", "fr": "Image non trouvée", "ru": "Изображение не найдено", "de": "Bild nicht gefunden", "it": "Immagine non trovata", "es": "Imagen no encontrada", "pt": "Imagem não encontrada", "ko": "이미지를 찾을 수 없음"},
    "images_processed": {"zh": "已处理 {0} 张图片", "en": "{0} image(s) processed", "ja": "{0}枚の画像を処理しました", "fr": "{0} image(s) traitée(s)", "ru": "Обработано изображений: {0}", "de": "{0} Bild(er) verarbeitet", "it": "{0} immagine/i elaborata/e", "es": "{0} imagen(es) procesada(s)", "pt": "{0} imagem(ns) processada(s)", "ko": "{0}개 이미지 처리됨"},
    "kb_images_count": {"zh": "知识库包含 {0} 张图片", "en": "KB contains {0} image(s)", "ja": "KBに{0}枚の画像が含まれています", "fr": "KB contient {0} image(s)", "ru": "БЗ содержит {0} изображений", "de": "KB enthält {0} Bild(er)", "it": "KB contiene {0} immagine/i", "es": "KB contiene {0} imagen(es)", "pt": "KB contém {0} imagem(ns)", "ko": "KB에 {0}개 이미지 포함"},
    "image_process_mode": {"zh": "图片处理方式", "en": "Image Processing", "ja": "画像処理方式", "fr": "Traitement d'image", "ru": "Обработка изображений", "de": "Bildverarbeitung", "it": "Elaborazione immagini", "es": "Procesamiento de imágenes", "pt": "Processamento de imagem", "ko": "이미지 처리 방식"},
    "image_mode_copy": {"zh": "复制图片到知识库 (推荐)", "en": "Copy images to KB (Recommended)", "ja": "画像をKBにコピー (推奨)", "fr": "Copier dans KB (Recommandé)", "ru": "Копировать в БЗ (Рекомендуется)", "de": "In KB kopieren (Empfohlen)", "it": "Copia in KB (Consigliato)", "es": "Copiar a KB (Recomendado)", "pt": "Copiar para KB (Recomendado)", "ko": "KB에 복사 (권장)"},
    "image_mode_base64": {"zh": "嵌入为 Base64", "en": "Embed as Base64", "ja": "Base64として埋め込み", "fr": "Intégrer en Base64", "ru": "Встроить как Base64", "de": "Als Base64 einbetten", "it": "Incorpora come Base64", "es": "Incrustar como Base64", "pt": "Incorporar como Base64", "ko": "Base64로 포함"},
    "image_mode_reference": {"zh": "保留原始路径", "en": "Keep original paths", "ja": "元のパスを保持", "fr": "Conserver les chemins originaux", "ru": "Сохранить оригинальные пути", "de": "Originale Pfade behalten", "it": "Mantieni percorsi originali", "es": "Mantener rutas originales", "pt": "Manter caminhos originais", "ko": "원본 경로 유지"},
    "image_mode_desc": {"zh": "Markdown 文档中的图片将根据选择的方式处理", "en": "Images in Markdown will be processed as selected", "ja": "Markdown内の画像は選択した方法で処理されます", "fr": "Les images Markdown seront traitées selon le mode choisi", "ru": "Изображения в Markdown будут обработаны выбранным способом", "de": "Bilder in Markdown werden entsprechend verarbeitet", "it": "Le immagini Markdown saranno elaborate come selezionato", "es": "Las imágenes en Markdown se procesarán según la selección", "pt": "Imagens em Markdown serão processadas conforme selecionado", "ko": "Markdown 이미지는 선택한 방식으로 처리됩니다"},
    "images_included": {"zh": "包含 {0} 张图片", "en": "{0} image(s) included", "ja": "{0}枚の画像が含まれています", "fr": "{0} image(s) incluse(s)", "ru": "Включено изображений: {0}", "de": "{0} Bild(er) enthalten", "it": "{0} immagine/i inclusa/e", "es": "{0} imagen(es) incluida(s)", "pt": "{0} imagem(ns) incluída(s)", "ko": "{0}개 이미지 포함"},
    "output_size": {"zh": "输出规模", "en": "Output Size", "ja": "出力サイズ", "fr": "Taille de sortie", "ru": "Размер вывода", "de": "Ausgabegröße", "it": "Dimensione output", "es": "Tamaño de salida", "pt": "Tamanho da saída", "ko": "출력 크기"},
    "output_short": {"zh": "简洁 (约500字)", "en": "Concise (~500 words)", "ja": "簡潔（約500語）", "fr": "Concis (~500 mots)", "ru": "Кратко (~500 слов)", "de": "Kurz (~500 Wörter)", "it": "Conciso (~500 parole)", "es": "Conciso (~500 palabras)", "pt": "Conciso (~500 palavras)", "ko": "간결 (~500단어)"},
    "output_medium": {"zh": "中等 (约1000字)", "en": "Medium (~1000 words)", "ja": "標準（約1000語）", "fr": "Moyen (~1000 mots)", "ru": "Средне (~1000 слов)", "de": "Mittel (~1000 Wörter)", "it": "Medio (~1000 parole)", "es": "Medio (~1000 palabras)", "pt": "Médio (~1000 palavras)", "ko": "보통 (~1000단어)"},
    "output_long": {"zh": "详细 (约2000字)", "en": "Detailed (~2000 words)", "ja": "詳細（約2000語）", "fr": "Détaillé (~2000 mots)", "ru": "Подробно (~2000 слов)", "de": "Detailliert (~2000 Wörter)", "it": "Dettagliato (~2000 parole)", "es": "Detallado (~2000 palabras)", "pt": "Detalhado (~2000 palavras)", "ko": "상세 (~2000단어)"},
    "context_usage": {"zh": "上下文使用情况", "en": "Context Usage", "ja": "コンテキスト使用状況", "fr": "Utilisation du contexte", "ru": "Использование контекста", "de": "Kontextnutzung", "it": "Utilizzo contesto", "es": "Uso de contexto", "pt": "Uso de contexto", "ko": "컨텍스트 사용량"},
    "tokens": {"zh": "词元", "en": "Tokens", "ja": "トークン", "fr": "Jetons", "ru": "Токены", "de": "Tokens", "it": "Token", "es": "Tokens", "pt": "Tokens", "ko": "토큰"},
    "sections": {"zh": "章节", "en": "Sections", "ja": "セクション", "fr": "Sections", "ru": "Разделы", "de": "Abschnitte", "it": "Sezioni", "es": "Secciones", "pt": "Seções", "ko": "섹션"},
    "sources": {"zh": "来源", "en": "Sources", "ja": "ソース", "fr": "Sources", "ru": "Источники", "de": "Quellen", "it": "Fonti", "es": "Fuentes", "pt": "Fontes", "ko": "출처"},
    "rephrasing_phase": {"zh": "优化主题", "en": "Rephrasing", "ja": "トピック最適化", "fr": "Reformulation", "ru": "Переформулировка", "de": "Umformulierung", "it": "Riformulazione", "es": "Reformulación", "pt": "Reformulação", "ko": "주제 최적화"},
    "refining_phase": {"zh": "深化研究", "en": "Refining", "ja": "精査中", "fr": "Affinement", "ru": "Уточнение", "de": "Verfeinerung", "it": "Raffinamento", "es": "Refinamiento", "pt": "Refinamento", "ko": "심화"},
    "saving_progress": {"zh": "正在保存进度...", "en": "Saving progress...", "ja": "進捗を保存中...", "fr": "Enregistrement en cours...", "ru": "Сохранение прогресса...", "de": "Fortschritt wird gespeichert...", "it": "Salvataggio in corso...", "es": "Guardando progreso...", "pt": "Salvando progresso...", "ko": "진행 상황 저장 중..."},
    "progress_saved": {"zh": "进度已保存", "en": "Progress saved", "ja": "進捗が保存されました", "fr": "Progrès enregistré", "ru": "Прогресс сохранён", "de": "Fortschritt gespeichert", "it": "Progresso salvato", "es": "Progreso guardado", "pt": "Progresso salvo", "ko": "진행 상황 저장됨"},
    "lit_review_topic": {"zh": "综述主题/问题", "en": "Review Topic/Question", "ja": "レビュートピック/質問", "fr": "Sujet/Question de la revue", "ru": "Тема/Вопрос обзора", "de": "Überprüfungsthema/Frage", "it": "Argomento/Domanda revisione", "es": "Tema/Pregunta de revisión", "pt": "Tópico/Pergunta de revisão", "ko": "리뷰 주제/질문"},
    "lit_review_topic_placeholder": {"zh": "例如：深度学习在NLP中的最新进展", "en": "e.g. Recent advances in deep learning for NLP", "ja": "例：NLPにおける深層学習の最近の進展", "fr": "ex. Avancées récentes en apprentissage profond pour le NLP", "ru": "напр. Последние достижения в глубоком обучении для NLP", "de": "z.B. Aktuelle Entwicklungen im Deep Learning für NLP", "it": "es. Progressi recenti nel deep learning per NLP", "es": "ej. Avances recientes en aprendizaje profundo para NLP", "pt": "ex. Avanços recentes em aprendizado profundo para NLP", "ko": "예: NLP에서의 딥러닝 최신 발전"},
    "intro": {"zh": "引言", "en": "Introduction", "ja": "はじめに", "fr": "Introduction", "ru": "Введение", "de": "Einführung", "it": "Introduzione", "es": "Introducción", "pt": "Introdução", "ko": "서론"},
    "theme_analysis": {"zh": "主题分析", "en": "Thematic Analysis", "ja": "テーマ分析", "fr": "Analyse thématique", "ru": "Тематический анализ", "de": "Thematische Analyse", "it": "Analisi tematica", "es": "Análisis temático", "pt": "Análise temática", "ko": "주제 분석"},
    "conclusion": {"zh": "结论", "en": "Conclusion", "ja": "結論", "fr": "Conclusion", "ru": "Заключение", "de": "Fazit", "it": "Conclusione", "es": "Conclusión", "pt": "Conclusão", "ko": "결론"},
    "upload_mode": {"zh": "上传模式", "en": "Upload Mode", "ja": "アップロードモード", "fr": "Mode de téléchargement", "ru": "Режим загрузки", "de": "Upload-Modus", "it": "Modalità caricamento", "es": "Modo de carga", "pt": "Modo de envio", "ko": "업로드 모드"},
    "upload_mode_files": {"zh": "选择文件", "en": "Select Files", "ja": "ファイル選択", "fr": "Sélectionner fichiers", "ru": "Выбрать файлы", "de": "Dateien wählen", "it": "Seleziona file", "es": "Seleccionar archivos", "pt": "Selecionar arquivos", "ko": "파일 선택"},
    "upload_mode_folder": {"zh": "选择文件夹", "en": "Select Folder", "ja": "フォルダ選択", "fr": "Sélectionner dossier", "ru": "Выбрать папку", "de": "Ordner wählen", "it": "Seleziona cartella", "es": "Seleccionar carpeta", "pt": "Selecionar pasta", "ko": "폴더 선택"},
    "select_folder": {"zh": "选择文件夹", "en": "Select Folder", "ja": "フォルダを選択", "fr": "Sélectionner un dossier", "ru": "Выбрать папку", "de": "Ordner auswählen", "it": "Seleziona cartella", "es": "Seleccionar carpeta", "pt": "Selecionar pasta", "ko": "폴더 선택"},
    "folder_upload_desc": {"zh": "上传整个文件夹，保留目录结构", "en": "Upload entire folder, preserving directory structure", "ja": "フォルダ全体をアップロード、ディレクトリ構造を保持", "fr": "Télécharger le dossier entier, préserver la structure", "ru": "Загрузить папку целиком, сохраняя структуру", "de": "Gesamten Ordner hochladen, Struktur beibehalten", "it": "Carica intera cartella, preserva struttura", "es": "Subir carpeta completa, preservar estructura", "pt": "Enviar pasta inteira, preservar estrutura", "ko": "전체 폴더 업로드, 디렉토리 구조 유지"},
    "output_length": {"zh": "输出长度限制", "en": "Output Length Limit", "ja": "出力長さ制限", "fr": "Limite de longueur de sortie", "ru": "Лимит длины вывода", "de": "Ausgabelängenlimit", "it": "Limite lunghezza output", "es": "Límite de longitud de salida", "pt": "Limite de comprimento de saída", "ko": "출력 길이 제한"},
    "output_length_desc": {"zh": "限制AI回复的最大字数（0=不限制）", "en": "Limit max words in AI response (0=unlimited)", "ja": "AI応答の最大単語数を制限（0=無制限）", "fr": "Limiter le nombre max de mots (0=illimité)", "ru": "Ограничить макс. слов (0=без лимита)", "de": "Max. Wörter begrenzen (0=unbegrenzt)", "it": "Limita parole max (0=illimitato)", "es": "Limitar palabras máx. (0=sin límite)", "pt": "Limitar palavras máx. (0=ilimitado)", "ko": "AI 응답 최대 단어 수 제한 (0=무제한)"},
    "words": {"zh": "字", "en": "words", "ja": "語", "fr": "mots", "ru": "слов", "de": "Wörter", "it": "parole", "es": "palabras", "pt": "palavras", "ko": "단어"},
    "system_monitor": {"zh": "系统监控", "en": "System Monitor", "ja": "システムモニター", "fr": "Moniteur système", "ru": "Системный монитор", "de": "Systemüberwachung", "it": "Monitor di sistema", "es": "Monitor del sistema", "pt": "Monitor do sistema", "ko": "시스템 모니터"},
    "context_length": {"zh": "当前上下文", "en": "Current Context", "ja": "現在のコンテキスト", "fr": "Contexte actuel", "ru": "Текущий контекст", "de": "Aktueller Kontext", "it": "Contesto attuale", "es": "Contexto actual", "pt": "Contexto atual", "ko": "현재 컨텍스트"},
    "max_context": {"zh": "最大上下文", "en": "Max Context", "ja": "最大コンテキスト", "fr": "Contexte max", "ru": "Макс. контекст", "de": "Max. Kontext", "it": "Contesto max", "es": "Contexto máx", "pt": "Contexto máx", "ko": "최대 컨텍스트"},
    "memory_usage": {"zh": "内存使用", "en": "Memory Usage", "ja": "メモリ使用量", "fr": "Utilisation mémoire", "ru": "Использование памяти", "de": "Speicherverbrauch", "it": "Utilizzo memoria", "es": "Uso de memoria", "pt": "Uso de memória", "ko": "메모리 사용량"},
    "kb_docs": {"zh": "知识库文档", "en": "KB Documents", "ja": "KBドキュメント", "fr": "Documents KB", "ru": "Документы БЗ", "de": "KB-Dokumente", "it": "Documenti KB", "es": "Documentos KB", "pt": "Documentos KB", "ko": "KB 문서"},
    "documents": {"zh": "文档", "en": "documents", "ja": "ドキュメント", "fr": "documents", "ru": "документов", "de": "Dokumente", "it": "documenti", "es": "documentos", "pt": "documentos", "ko": "문서"},
}


def t(key: str, lang: str = None) -> str:
    """Get translated text."""
    lang = lang or CONFIG.language
    if key in TRANSLATIONS:
        return TRANSLATIONS[key].get(lang, TRANSLATIONS[key].get("en", key))
    return key
