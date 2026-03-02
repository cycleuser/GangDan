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
    # Proxy settings
    proxy_mode: str = "none"  # "none", "system", "manual"
    proxy_http: str = ""
    proxy_https: str = ""
    # RAG behavior settings
    strict_kb_mode: bool = False  # If True, refuse to answer when KB has no results
    # Vector database settings
    vector_db_type: str = "chroma"  # "chroma", "faiss", "memory"


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


def save_user_kb(internal_name: str, display_name: str, file_count: int, languages: List[str] = None):
    """Add or update a user KB entry in the manifest."""
    kbs = load_user_kbs()
    kbs[internal_name] = {
        "display_name": display_name,
        "created": datetime.now().isoformat(),
        "file_count": file_count,
        "languages": languages or [],
    }
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
}


def t(key: str, lang: str = None) -> str:
    """Get translated text."""
    lang = lang or CONFIG.language
    if key in TRANSLATIONS:
        return TRANSLATIONS[key].get(lang, TRANSLATIONS[key].get("en", key))
    return key
