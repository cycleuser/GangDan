#!/usr/bin/env python3
"""
纲担 / GangDan - Offline Development Assistant
=====================================================
Flask application backend with:
- Multi-language UI (10 languages)
- Ollama chat with streaming
- ChromaDB vector knowledge base
- Web search with multiple engines
- Documentation download and indexing

Frontend is decoupled into separate files:
- templates/index.html  (Jinja2 template)
- static/css/style.css  (Pure CSS)
- static/js/*.js         (Pure JavaScript modules)

Usage:
    pip install flask flask-cors requests chromadb
    python app.py
"""

import os
import re
import io
import sys
import json
import time
import shutil
import hashlib
import zipfile
import threading
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Iterator, Tuple
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from flask import Flask, render_template, request, jsonify, Response, stream_with_context
    from flask_cors import CORS
    import chromadb
    from chromadb.config import Settings
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("\nPlease install required packages:")
    print("  pip install flask flask-cors requests chromadb")
    sys.exit(1)


# =============================================================================
# Configuration
# =============================================================================

def _get_data_dir() -> Path:
    """Determine the data directory based on environment or install context."""
    env = os.environ.get('GANGDAN_DATA_DIR')
    if env:
        return Path(env).expanduser().resolve()
    pkg_dir = Path(__file__).resolve().parent
    if 'site-packages' in str(pkg_dir) or 'dist-packages' in str(pkg_dir):
        return Path.home() / '.gangdan'
    return Path('./data')

DATA_DIR = _get_data_dir()
DOCS_DIR = DATA_DIR / "docs"
CHROMA_DIR = DATA_DIR / "chroma"

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
        # Use system environment variables
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
    """Sanitize user-provided KB name to a safe internal name with user_ prefix.
    
    ChromaDB requires collection names to contain only [a-zA-Z0-9._-],
    so we convert non-ASCII characters to their pinyin/romanized equivalents
    or use a hash-based fallback.
    """
    import re
    import hashlib
    
    # First try: keep only ASCII alphanumeric and spaces/hyphens
    safe = re.sub(r'[^a-zA-Z0-9\s-]', '', name.strip()).strip()
    safe = re.sub(r'[\s-]+', '_', safe).lower()
    
    # If result is empty (e.g., all Chinese), use hash of original name
    if not safe or len(safe) < 3:
        # Create a short hash from the original name for uniqueness
        name_hash = hashlib.md5(name.encode('utf-8')).hexdigest()[:8]
        safe = f"kb_{name_hash}"
    
    return f"user_{safe}"


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
    # AI Command Assistant
    "ai_assistant": {"zh": "AI 命令助手", "en": "AI Command Assistant", "ja": "AIコマンドアシスタント", "fr": "Assistant de commandes IA", "ru": "AI Командный помощник", "de": "KI-Befehlsassistent", "it": "Assistente comandi IA", "es": "Asistente de comandos IA", "pt": "Assistente de comandos IA", "ko": "AI 명령 어시스턴트"},
    "command_line": {"zh": "命令行", "en": "Command Line", "ja": "コマンドライン", "fr": "Ligne de commande", "ru": "Командная строка", "de": "Befehlszeile", "it": "Riga di comando", "es": "Línea de comandos", "pt": "Linha de comando", "ko": "명령줄"},
    "ai_ask_desc": {"zh": "输入问题或描述任务...", "en": "Describe what you want to do...", "ja": "やりたいことを入力...", "fr": "Décrivez ce que vous voulez faire...", "ru": "Опишите, что вы хотите сделать...", "de": "Beschreiben Sie, was Sie tun möchten...", "it": "Descrivi cosa vuoi fare...", "es": "Describa lo que quiere hacer...", "pt": "Descreva o que deseja fazer...", "ko": "원하는 작업을 설명하세요..."},
    "enter_command": {"zh": "输入命令...", "en": "Enter command...", "ja": "コマンドを入力...", "fr": "Entrer une commande...", "ru": "Введите команду...", "de": "Befehl eingeben...", "it": "Inserisci comando...", "es": "Ingrese comando...", "pt": "Digite o comando...", "ko": "명령어 입력..."},
    "ai_cleared": {"zh": "AI 助手已清空", "en": "AI assistant cleared", "ja": "AIアシスタントがクリアされました", "fr": "Assistant IA effacé", "ru": "AI помощник очищен", "de": "KI-Assistent gelöscht", "it": "Assistente IA cancellato", "es": "Asistente IA borrado", "pt": "Assistente IA limpo", "ko": "AI 어시스턴트 초기화됨"},
    "ai_intro": {"zh": "输入问题让我帮你生成命令、分析结果或解释错误。", "en": "Ask me to generate commands, analyze results, or explain errors.", "ja": "コマンドの生成、結果の分析、エラーの説明をお手伝いします。", "fr": "Demandez-moi de générer des commandes, d'analyser des résultats ou d'expliquer des erreurs.", "ru": "Попросите меня сгенерировать команды, проанализировать результаты или объяснить ошибки.", "de": "Bitten Sie mich, Befehle zu generieren, Ergebnisse zu analysieren oder Fehler zu erklären.", "it": "Chiedimi di generare comandi, analizzare risultati o spiegare errori.", "es": "Pídale generar comandos, analizar resultados o explicar errores.", "pt": "Peça para gerar comandos, analisar resultados ou explicar erros.", "ko": "명령 생성, 결과 분석, 오류 설명을 요청하세요."},
    "terminal_ready": {"zh": "终端就绪", "en": "Terminal Ready", "ja": "ターミナル準備完了", "fr": "Terminal prêt", "ru": "Терминал готов", "de": "Terminal bereit", "it": "Terminale pronto", "es": "Terminal listo", "pt": "Terminal pronto", "ko": "터미널 준비됨"},
    "terminal_hint": {"zh": "输入命令或从AI助手拖拽。", "en": "Type commands or drag from AI assistant.", "ja": "コマンドを入力するかAIアシスタントからドラッグ。", "fr": "Tapez des commandes ou glissez depuis l'assistant IA.", "ru": "Введите команды или перетащите из AI-помощника.", "de": "Befehle eingeben oder vom KI-Assistenten ziehen.", "it": "Digita comandi o trascina dall'assistente IA.", "es": "Escriba comandos o arrastre desde el asistente IA.", "pt": "Digite comandos ou arraste do assistente IA.", "ko": "명령어를 입력하거나 AI 어시스턴트에서 드래그하세요."},
    # Docs panel
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
    # Settings panel
    "connection_status": {"zh": "连接状态", "en": "Connection Status", "ja": "接続状態", "fr": "État de connexion", "ru": "Статус подключения", "de": "Verbindungsstatus", "it": "Stato connessione", "es": "Estado de conexión", "pt": "Estado de conexão", "ko": "연결 상태"},
    "embedding": {"zh": "嵌入模型", "en": "Embedding", "ja": "エンベディング", "fr": "Embedding", "ru": "Эмбеддинг", "de": "Embedding", "it": "Embedding", "es": "Embedding", "pt": "Embedding", "ko": "임베딩"},
    "reranker": {"zh": "重排模型", "en": "Reranker", "ja": "リランカー", "fr": "Reranker", "ru": "Реранкер", "de": "Reranker", "it": "Reranker", "es": "Reranker", "pt": "Reranker", "ko": "리랭커"},
    "optional": {"zh": "可选", "en": "Optional", "ja": "オプション", "fr": "Optionnel", "ru": "Необязательно", "de": "Optional", "it": "Opzionale", "es": "Opcional", "pt": "Opcional", "ko": "선택사항"},
    "mode": {"zh": "模式", "en": "Mode", "ja": "モード", "fr": "Mode", "ru": "Режим", "de": "Modus", "it": "Modalità", "es": "Modo", "pt": "Modo", "ko": "모드"},
    "no_proxy_opt": {"zh": "不使用", "en": "None", "ja": "なし", "fr": "Aucun", "ru": "Нет", "de": "Keiner", "it": "Nessuno", "es": "Ninguno", "pt": "Nenhum", "ko": "없음"},
    "system_proxy_opt": {"zh": "系统代理", "en": "System", "ja": "システム", "fr": "Système", "ru": "Системный", "de": "System", "it": "Sistema", "es": "Sistema", "pt": "Sistema", "ko": "시스템"},
    "manual_proxy_opt": {"zh": "手动设置", "en": "Manual", "ja": "手動", "fr": "Manuel", "ru": "Ручной", "de": "Manuell", "it": "Manuale", "es": "Manual", "pt": "Manual", "ko": "수동"},
    "save_settings": {"zh": "保存设置", "en": "Save Settings", "ja": "設定を保存", "fr": "Enregistrer les paramètres", "ru": "Сохранить настройки", "de": "Einstellungen speichern", "it": "Salva impostazioni", "es": "Guardar configuración", "pt": "Salvar configurações", "ko": "설정 저장"},
    # AI context messages
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
    # Document upload & KB scope
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
    # RAG behavior settings
    "strict_kb_mode": {"zh": "严格知识库模式", "en": "Strict KB Mode", "ja": "厳密KBモード", "fr": "Mode KB strict", "ru": "Строгий режим БЗ", "de": "Strenger KB-Modus", "it": "Modalità KB rigorosa", "es": "Modo KB estricto", "pt": "Modo KB estrito", "ko": "엄격 KB 모드"},
    "strict_kb_mode_desc": {"zh": "无检索结果时拒绝回答", "en": "Refuse to answer when no KB results", "ja": "KB結果がない場合は回答を拒否", "fr": "Refuser de répondre sans résultats KB", "ru": "Отказ от ответа без результатов БЗ", "de": "Antwort verweigern ohne KB-Ergebnisse", "it": "Rifiuta risposta senza risultati KB", "es": "Rechazar respuesta sin resultados KB", "pt": "Recusar resposta sem resultados KB", "ko": "KB 결과 없으면 답변 거부"},
    "kb_no_results_strict": {"zh": "抱歉，在知识库中未找到相关内容。严格模式下无法回答此问题。", "en": "Sorry, no relevant content found in the knowledge base. Cannot answer in strict mode.", "ja": "申し訳ありませんが、ナレッジベースに関連コンテンツが見つかりませんでした。厳密モードでは回答できません。", "fr": "Désolé, aucun contenu pertinent trouvé dans la base de connaissances. Impossible de répondre en mode strict.", "ru": "Извините, в базе знаний не найдено релевантного контента. В строгом режиме ответить невозможно.", "de": "Entschuldigung, keine relevanten Inhalte in der Wissensdatenbank gefunden. Im strengen Modus kann nicht geantwortet werden.", "it": "Spiacente, nessun contenuto rilevante trovato nella base di conoscenza. Impossibile rispondere in modalità rigorosa.", "es": "Lo siento, no se encontró contenido relevante en la base de conocimiento. No se puede responder en modo estricto.", "pt": "Desculpe, nenhum conteúdo relevante encontrado na base de conhecimento. Não é possível responder no modo estrito.", "ko": "죄송합니다. 지식 베이스에서 관련 콘텐츠를 찾을 수 없습니다. 엄격 모드에서는 답변할 수 없습니다."},
    "references": {"zh": "参考文献", "en": "References", "ja": "参考文献", "fr": "Références", "ru": "Ссылки", "de": "Referenzen", "it": "Riferimenti", "es": "Referencias", "pt": "Referências", "ko": "참고 문헌"},
    # Duplicate file handling
    "duplicate_files_found": {"zh": "发现重复文件", "en": "Duplicate Files Found", "ja": "重複ファイルが見つかりました", "fr": "Fichiers en double trouvés", "ru": "Найдены дубликаты файлов", "de": "Doppelte Dateien gefunden", "it": "File duplicati trovati", "es": "Archivos duplicados encontrados", "pt": "Arquivos duplicados encontrados", "ko": "중복 파일 발견"},
    "duplicate_files_msg": {"zh": "以下文件已存在于知识库中：", "en": "The following files already exist in the knowledge base:", "ja": "以下のファイルはナレッジベースに既に存在します：", "fr": "Les fichiers suivants existent déjà dans la base de connaissances :", "ru": "Следующие файлы уже существуют в базе знаний:", "de": "Die folgenden Dateien existieren bereits in der Wissensdatenbank:", "it": "I seguenti file esistono già nella base di conoscenza:", "es": "Los siguientes archivos ya existen en la base de conocimiento:", "pt": "Os seguintes arquivos já existem na base de conhecimento:", "ko": "다음 파일이 이미 지식 베이스에 존재합니다:"},
    "skip_duplicates": {"zh": "跳过重复", "en": "Skip Duplicates", "ja": "重複をスキップ", "fr": "Ignorer les doublons", "ru": "Пропустить дубликаты", "de": "Duplikate überspringen", "it": "Salta duplicati", "es": "Omitir duplicados", "pt": "Pular duplicados", "ko": "중복 건너뛰기"},
    "overwrite_duplicates": {"zh": "覆盖重复", "en": "Overwrite Duplicates", "ja": "重複を上書き", "fr": "Écraser les doublons", "ru": "Перезаписать дубликаты", "de": "Duplikate überschreiben", "it": "Sovrascrivi duplicati", "es": "Sobrescribir duplicados", "pt": "Sobrescrever duplicados", "ko": "중복 덮어쓰기"},
    "cancel": {"zh": "取消", "en": "Cancel", "ja": "キャンセル", "fr": "Annuler", "ru": "Отмена", "de": "Abbrechen", "it": "Annulla", "es": "Cancelar", "pt": "Cancelar", "ko": "취소"},
    "files_skipped": {"zh": "已跳过 {0} 个重复文件", "en": "{0} duplicate file(s) skipped", "ja": "{0}個の重複ファイルをスキップしました", "fr": "{0} fichier(s) en double ignoré(s)", "ru": "Пропущено {0} дубликат(ов)", "de": "{0} Duplikat(e) übersprungen", "it": "{0} file duplicato/i saltato/i", "es": "{0} archivo(s) duplicado(s) omitido(s)", "pt": "{0} arquivo(s) duplicado(s) pulado(s)", "ko": "중복 파일 {0}개 건너뛰기"},
    "files_overwritten": {"zh": "已覆盖 {0} 个文件", "en": "{0} file(s) overwritten", "ja": "{0}個のファイルを上書きしました", "fr": "{0} fichier(s) écrasé(s)", "ru": "Перезаписано {0} файл(ов)", "de": "{0} Datei(en) überschrieben", "it": "{0} file sovrascritto/i", "es": "{0} archivo(s) sobrescrito(s)", "pt": "{0} arquivo(s) sobrescrito(s)", "ko": "파일 {0}개 덮어씀"},
    # Vector database settings
    "vector_db": {"zh": "向量数据库", "en": "Vector Database", "ja": "ベクトルDB", "fr": "Base vectorielle", "ru": "Векторная БД", "de": "Vektor-DB", "it": "DB vettoriale", "es": "BD vectorial", "pt": "BD vetorial", "ko": "벡터 DB"},
    "vector_db_chroma": {"zh": "ChromaDB (默认)", "en": "ChromaDB (Default)", "ja": "ChromaDB (デフォルト)", "fr": "ChromaDB (Défaut)", "ru": "ChromaDB (по умолчанию)", "de": "ChromaDB (Standard)", "it": "ChromaDB (Predefinito)", "es": "ChromaDB (Predeterminado)", "pt": "ChromaDB (Padrão)", "ko": "ChromaDB (기본값)"},
    "vector_db_faiss": {"zh": "FAISS (高性能)", "en": "FAISS (High Performance)", "ja": "FAISS (高性能)", "fr": "FAISS (Haute performance)", "ru": "FAISS (высокая производительность)", "de": "FAISS (Hochleistung)", "it": "FAISS (Alta prestazione)", "es": "FAISS (Alto rendimiento)", "pt": "FAISS (Alto desempenho)", "ko": "FAISS (고성능)"},
    "vector_db_memory": {"zh": "内存 (轻量级)", "en": "In-Memory (Lightweight)", "ja": "メモリ (軽量)", "fr": "Mémoire (Léger)", "ru": "Память (легкий)", "de": "Speicher (Leicht)", "it": "Memoria (Leggero)", "es": "Memoria (Ligero)", "pt": "Memória (Leve)", "ko": "메모리 (경량)"},
    "vector_db_restart_required": {"zh": "更改向量数据库需要重启应用", "en": "Changing vector DB requires app restart", "ja": "ベクトルDB変更にはアプリ再起動が必要", "fr": "Le changement de BD nécessite un redémarrage", "ru": "Изменение БД требует перезапуска", "de": "DB-Änderung erfordert Neustart", "it": "Cambio DB richiede riavvio", "es": "Cambiar BD requiere reinicio", "pt": "Mudar BD requer reinício", "ko": "벡터 DB 변경 시 앱 재시작 필요"},
    # Literature review feature
    "lit_review": {"zh": "文献综述", "en": "Literature Review", "ja": "文献レビュー", "fr": "Revue de littérature", "ru": "Обзор литературы", "de": "Literaturübersicht", "it": "Revisione letteratura", "es": "Revisión de literatura", "pt": "Revisão de literatura", "ko": "문헌 리뷰"},
    "generate_lit_review": {"zh": "生成文献综述", "en": "Generate Literature Review", "ja": "文献レビューを生成", "fr": "Générer une revue", "ru": "Создать обзор", "de": "Übersicht erstellen", "it": "Genera revisione", "es": "Generar revisión", "pt": "Gerar revisão", "ko": "문헌 리뷰 생성"},
    "lit_review_desc": {"zh": "为当前知识库生成学术风格的文献综述", "en": "Generate academic-style literature review for current KB", "ja": "現在のKBの学術的な文献レビューを生成", "fr": "Générer une revue académique pour la KB actuelle", "ru": "Создать академический обзор для текущей БЗ", "de": "Akademische Übersicht für aktuelle KB erstellen", "it": "Genera revisione accademica per KB corrente", "es": "Generar revisión académica para KB actual", "pt": "Gerar revisão acadêmica para KB atual", "ko": "현재 KB에 대한 학술적 문헌 리뷰 생성"},
    "generating_lit_review": {"zh": "正在生成文献综述...", "en": "Generating literature review...", "ja": "文献レビューを生成中...", "fr": "Génération de la revue...", "ru": "Создание обзора...", "de": "Übersicht wird erstellt...", "it": "Generazione revisione...", "es": "Generando revisión...", "pt": "Gerando revisão...", "ko": "문헌 리뷰 생성 중..."},
    "lit_review_complete": {"zh": "文献综述生成完成", "en": "Literature review complete", "ja": "文献レビュー完了", "fr": "Revue terminée", "ru": "Обзор завершен", "de": "Übersicht fertig", "it": "Revisione completata", "es": "Revisión completa", "pt": "Revisão completa", "ko": "문헌 리뷰 완료"},
    "no_kb_selected": {"zh": "请先选择知识库", "en": "Please select a knowledge base first", "ja": "最初にKBを選択してください", "fr": "Veuillez d'abord sélectionner une KB", "ru": "Сначала выберите БЗ", "de": "Bitte zuerst KB auswählen", "it": "Seleziona prima una KB", "es": "Primero seleccione una KB", "pt": "Primeiro selecione uma KB", "ko": "먼저 KB를 선택하세요"},
    # Import / Export
    "import_export": {"zh": "导入/导出", "en": "Import / Export", "ja": "インポート/エクスポート", "fr": "Import / Export", "ru": "Импорт / Экспорт", "de": "Import / Export", "it": "Importa / Esporta", "es": "Importar / Exportar", "pt": "Importar / Exportar", "ko": "가져오기 / 내보내기"},
    "export_raw_files": {"zh": "导出原始文件", "en": "Export Raw Files", "ja": "元ファイルをエクスポート", "fr": "Exporter les fichiers bruts", "ru": "Экспорт исходных файлов", "de": "Rohdateien exportieren", "it": "Esporta file originali", "es": "Exportar archivos originales", "pt": "Exportar arquivos originais", "ko": "원본 파일 내보내기"},
    "import_raw_files": {"zh": "导入原始文件", "en": "Import Raw Files", "ja": "元ファイルをインポート", "fr": "Importer les fichiers bruts", "ru": "Импорт исходных файлов", "de": "Rohdateien importieren", "it": "Importa file originali", "es": "Importar archivos originales", "pt": "Importar arquivos originais", "ko": "원본 파일 가져오기"},
    "export_kb": {"zh": "导出知识库", "en": "Export Knowledge Base", "ja": "ナレッジベースをエクスポート", "fr": "Exporter la base de connaissances", "ru": "Экспорт базы знаний", "de": "Wissensdatenbank exportieren", "it": "Esporta base di conoscenza", "es": "Exportar base de conocimiento", "pt": "Exportar base de conhecimento", "ko": "지식 베이스 내보내기"},
    "import_kb": {"zh": "导入知识库", "en": "Import Knowledge Base", "ja": "ナレッジベースをインポート", "fr": "Importer la base de connaissances", "ru": "Импорт базы знаний", "de": "Wissensdatenbank importieren", "it": "Importa base di conoscenza", "es": "Importar base de conocimiento", "pt": "Importar base de conhecimento", "ko": "지식 베이스 가져오기"},
    "exporting": {"zh": "正在导出...", "en": "Exporting...", "ja": "エクスポート中...", "fr": "Exportation en cours...", "ru": "Экспорт...", "de": "Wird exportiert...", "it": "Esportazione...", "es": "Exportando...", "pt": "Exportando...", "ko": "내보내는 중..."},
    "importing": {"zh": "正在导入...", "en": "Importing...", "ja": "インポート中...", "fr": "Importation en cours...", "ru": "Импорт...", "de": "Wird importiert...", "it": "Importazione...", "es": "Importando...", "pt": "Importando...", "ko": "가져오는 중..."},
    "export_success": {"zh": "导出成功", "en": "Export successful", "ja": "エクスポート成功", "fr": "Exportation réussie", "ru": "Экспорт успешен", "de": "Export erfolgreich", "it": "Esportazione riuscita", "es": "Exportación exitosa", "pt": "Exportação bem-sucedida", "ko": "내보내기 성공"},
    "import_success": {"zh": "导入成功", "en": "Import successful", "ja": "インポート成功", "fr": "Importation réussie", "ru": "Импорт успешен", "de": "Import erfolgreich", "it": "Importazione riuscita", "es": "Importación exitosa", "pt": "Importação bem-sucedida", "ko": "가져오기 성공"},
    "no_files_to_export": {"zh": "没有可导出的文件", "en": "No files to export", "ja": "エクスポートするファイルがありません", "fr": "Aucun fichier à exporter", "ru": "Нет файлов для экспорта", "de": "Keine Dateien zum Exportieren", "it": "Nessun file da esportare", "es": "No hay archivos para exportar", "pt": "Nenhum arquivo para exportar", "ko": "내보낼 파일이 없습니다"},
    "no_kb_to_export": {"zh": "没有可导出的知识库", "en": "No knowledge base to export", "ja": "エクスポートするナレッジベースがありません", "fr": "Aucune base de connaissances à exporter", "ru": "Нет базы знаний для экспорта", "de": "Keine Wissensdatenbank zum Exportieren", "it": "Nessuna base di conoscenza da esportare", "es": "No hay base de conocimiento para exportar", "pt": "Nenhuma base de conhecimento para exportar", "ko": "내보낼 지식 베이스가 없습니다"},
    "raw_files_desc": {"zh": "导出/导入所有已下载和上传的原始文档文件", "en": "Export/import all downloaded and uploaded raw document files", "ja": "ダウンロード・アップロードした元ドキュメントファイルをエクスポート/インポート", "fr": "Exporter/importer tous les fichiers de documents bruts", "ru": "Экспорт/импорт всех загруженных документов", "de": "Alle heruntergeladenen Dokumente exportieren/importieren", "it": "Esporta/importa tutti i documenti originali", "es": "Exportar/importar todos los documentos originales", "pt": "Exportar/importar todos os documentos originais", "ko": "모든 다운로드 및 업로드된 원본 문서 파일 내보내기/가져오기"},
    "kb_desc": {"zh": "导出/导入完整的向量知识库（含索引和嵌入向量）", "en": "Export/import the full vector knowledge base (with index and embeddings)", "ja": "ベクトルナレッジベース全体をエクスポート/インポート（インデックスとエンベディング含む）", "fr": "Exporter/importer la base de connaissances vectorielle complète", "ru": "Экспорт/импорт полной векторной базы знаний", "de": "Vollständige Vektor-Wissensdatenbank exportieren/importieren", "it": "Esporta/importa l'intera base di conoscenza vettoriale", "es": "Exportar/importar la base de conocimiento vectorial completa", "pt": "Exportar/importar a base de conhecimento vetorial completa", "ko": "전체 벡터 지식 베이스 내보내기/가져오기 (인덱스 및 임베딩 포함)"},
}

# Merge learning module translations from core config
from gangdan.core.config import TRANSLATIONS as _CORE_TRANSLATIONS
for _k, _v in _CORE_TRANSLATIONS.items():
    if _k not in TRANSLATIONS:
        TRANSLATIONS[_k] = _v

def t(key: str, lang: str = None) -> str:
    """Get translated text."""
    lang = lang or CONFIG.language
    if key in TRANSLATIONS:
        return TRANSLATIONS[key].get(lang, TRANSLATIONS[key].get("en", key))
    return key


def detect_language(text: str) -> str:
    """Detect language using Unicode character ranges.
    
    Returns ISO 639-1 code: zh, en, ja, ko, ru, fr, de, es, pt, it
    Defaults to 'unknown' if unclear.
    """
    if not text:
        return "unknown"
    
    # Sample first 500 chars for efficiency
    sample = text[:500]
    
    # Count character types
    cjk = sum(1 for c in sample if '\u4e00' <= c <= '\u9fff')
    hiragana = sum(1 for c in sample if '\u3040' <= c <= '\u309f')
    katakana = sum(1 for c in sample if '\u30a0' <= c <= '\u30ff')
    hangul = sum(1 for c in sample if '\uac00' <= c <= '\ud7af')
    cyrillic = sum(1 for c in sample if '\u0400' <= c <= '\u04ff')
    
    total = len(sample)
    if total == 0:
        return "unknown"
    
    # Japanese: has hiragana/katakana
    if (hiragana + katakana) / total > 0.1:
        return "ja"
    # Korean: has hangul
    if hangul / total > 0.1:
        return "ko"
    # Chinese: has CJK but no Japanese kana
    if cjk / total > 0.1:
        return "zh"
    # Russian: has cyrillic
    if cyrillic / total > 0.1:
        return "ru"
    # Default to English for Latin scripts
    return "en"


# =============================================================================
# Documentation Sources - Using reliable raw GitHub URLs
# =============================================================================

DOC_SOURCES = {
    # Python Libraries
    "numpy": {
        "name": "NumPy",
        "urls": [
            "https://raw.githubusercontent.com/numpy/numpy/main/doc/source/user/absolute_beginners.rst",
            "https://raw.githubusercontent.com/numpy/numpy/main/doc/source/user/basics.creation.rst",
            "https://raw.githubusercontent.com/numpy/numpy/main/doc/source/user/basics.indexing.rst",
        ]
    },
    "pandas": {
        "name": "Pandas",
        "urls": [
            "https://raw.githubusercontent.com/pandas-dev/pandas/main/doc/source/user_guide/10min.rst",
            "https://raw.githubusercontent.com/pandas-dev/pandas/main/doc/source/user_guide/indexing.rst",
        ]
    },
    "pytorch": {
        "name": "PyTorch",
        "urls": [
            "https://raw.githubusercontent.com/pytorch/pytorch/main/README.md",
            "https://raw.githubusercontent.com/pytorch/tutorials/main/beginner_source/basics/intro.py",
        ]
    },
    "scipy": {
        "name": "SciPy",
        "urls": [
            "https://raw.githubusercontent.com/scipy/scipy/main/doc/source/tutorial/index.rst",
            "https://raw.githubusercontent.com/scipy/scipy/main/doc/source/tutorial/optimize.rst",
            "https://raw.githubusercontent.com/scipy/scipy/main/doc/source/tutorial/interpolate.rst",
            "https://raw.githubusercontent.com/scipy/scipy/main/doc/source/tutorial/linalg.rst",
        ]
    },
    "sklearn": {
        "name": "Scikit-learn",
        "urls": [
            "https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/README.rst",
            "https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/doc/getting_started.rst",
            "https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/doc/modules/clustering.rst",
            "https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/doc/modules/tree.rst",
        ]
    },
    "skimage": {
        "name": "Scikit-image",
        "urls": [
            "https://raw.githubusercontent.com/scikit-image/scikit-image/main/README.md",
            "https://raw.githubusercontent.com/scikit-image/scikit-image/main/doc/source/user_guide/getting_started.rst",
            "https://raw.githubusercontent.com/scikit-image/scikit-image/main/doc/source/user_guide/tutorial_segmentation.rst",
        ]
    },
    "sympy": {
        "name": "SymPy",
        "urls": [
            "https://raw.githubusercontent.com/sympy/sympy/master/README.md",
            "https://raw.githubusercontent.com/sympy/sympy/master/doc/src/tutorials/intro-tutorial/intro.rst",
            "https://raw.githubusercontent.com/sympy/sympy/master/doc/src/tutorials/intro-tutorial/basic_operations.rst",
        ]
    },
    "chempy": {
        "name": "ChemPy",
        "urls": [
            "https://raw.githubusercontent.com/bjodah/chempy/master/README.rst",
            "https://raw.githubusercontent.com/bjodah/chempy/master/CHANGES.rst",
        ]
    },
    "jupyter": {
        "name": "Jupyter",
        "urls": [
            "https://raw.githubusercontent.com/jupyter/notebook/main/README.md",
            "https://raw.githubusercontent.com/jupyterlab/jupyterlab/main/README.md",
            "https://raw.githubusercontent.com/ipython/ipython/main/README.rst",
        ]
    },
    "matplotlib": {
        "name": "Matplotlib",
        "urls": [
            "https://raw.githubusercontent.com/matplotlib/matplotlib/main/README.md",
            "https://raw.githubusercontent.com/matplotlib/matplotlib/main/doc/users/getting_started/index.rst",
        ]
    },
    "pyside6": {
        "name": "PySide6/Qt",
        "urls": [
            "https://raw.githubusercontent.com/pyside/pyside-setup/dev/README.md",
            "https://raw.githubusercontent.com/qt/qtbase/dev/README.md",
        ]
    },
    "pyqtgraph": {
        "name": "PyQtGraph",
        "urls": [
            "https://raw.githubusercontent.com/pyqtgraph/pyqtgraph/master/README.md",
            "https://raw.githubusercontent.com/pyqtgraph/pyqtgraph/master/doc/source/index.rst",
        ]
    },
    "tensorflow": {
        "name": "TensorFlow",
        "urls": [
            "https://raw.githubusercontent.com/tensorflow/tensorflow/master/README.md",
            "https://raw.githubusercontent.com/tensorflow/docs/master/site/en/guide/basics.ipynb",
        ]
    },
    # GPU Computing
    "cuda": {
        "name": "CUDA/PyCUDA",
        "urls": [
            "https://raw.githubusercontent.com/inducer/pycuda/main/README.rst",
            "https://raw.githubusercontent.com/inducer/pycuda/main/doc/source/tutorial.rst",
        ]
    },
    "opencl": {
        "name": "OpenCL/PyOpenCL",
        "urls": [
            "https://raw.githubusercontent.com/inducer/pyopencl/main/README.rst",
            "https://raw.githubusercontent.com/inducer/pyopencl/main/doc/source/index.rst",
        ]
    },
    # Programming Languages
    "rust": {
        "name": "Rust",
        "urls": [
            "https://raw.githubusercontent.com/rust-lang/book/main/src/ch01-00-getting-started.md",
            "https://raw.githubusercontent.com/rust-lang/book/main/src/ch03-00-common-programming-concepts.md",
            "https://raw.githubusercontent.com/rust-lang/book/main/src/ch04-00-understanding-ownership.md",
        ]
    },
    "javascript": {
        "name": "JavaScript",
        "urls": [
            "https://raw.githubusercontent.com/mdn/content/main/files/en-us/web/javascript/guide/introduction/index.md",
            "https://raw.githubusercontent.com/mdn/content/main/files/en-us/web/javascript/guide/grammar_and_types/index.md",
        ]
    },
    "typescript": {
        "name": "TypeScript",
        "urls": [
            "https://raw.githubusercontent.com/microsoft/TypeScript/main/README.md",
            "https://raw.githubusercontent.com/microsoft/TypeScript-Website/v2/packages/documentation/copy/en/handbook-v2/Basics.md",
        ]
    },
    "c_lang": {
        "name": "C Language",
        "urls": [
            "https://raw.githubusercontent.com/torvalds/linux/master/Documentation/process/coding-style.rst",
        ]
    },
    "cpp": {
        "name": "C++",
        "urls": [
            "https://raw.githubusercontent.com/isocpp/CppCoreGuidelines/master/CppCoreGuidelines.md",
        ]
    },
    "go": {
        "name": "Go/Golang",
        "urls": [
            "https://raw.githubusercontent.com/golang/go/master/README.md",
            "https://raw.githubusercontent.com/golang/go/master/doc/effective_go.html",
        ]
    },
    "html_css": {
        "name": "HTML/CSS",
        "urls": [
            "https://raw.githubusercontent.com/mdn/content/main/files/en-us/learn/html/introduction_to_html/index.md",
            "https://raw.githubusercontent.com/mdn/content/main/files/en-us/learn/css/first_steps/index.md",
        ]
    },
    # Shell & Command Line
    "bash": {
        "name": "Bash Shell",
        "urls": [
            "https://raw.githubusercontent.com/dylanaraps/pure-bash-bible/master/README.md",
            "https://raw.githubusercontent.com/jlevy/the-art-of-command-line/master/README.md",
            "https://raw.githubusercontent.com/awesome-lists/awesome-bash/master/README.md",
        ]
    },
    "zsh": {
        "name": "Zsh Shell",
        "urls": [
            "https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/README.md",
            "https://raw.githubusercontent.com/unixorn/awesome-zsh-plugins/main/README.md",
        ]
    },
    "powershell": {
        "name": "PowerShell",
        "urls": [
            "https://raw.githubusercontent.com/PowerShell/PowerShell/master/README.md",
            "https://raw.githubusercontent.com/janikvonrotz/awesome-powershell/master/readme.md",
        ]
    },
    "fish": {
        "name": "Fish Shell",
        "urls": [
            "https://raw.githubusercontent.com/fish-shell/fish-shell/master/README.md",
            "https://raw.githubusercontent.com/jorgebucaran/awsm.fish/main/README.md",
        ]
    },
    "linux_commands": {
        "name": "Linux Commands",
        "urls": [
            "https://raw.githubusercontent.com/jlevy/the-art-of-command-line/master/README.md",
            "https://raw.githubusercontent.com/tldr-pages/tldr/main/README.md",
            "https://raw.githubusercontent.com/chubin/cheat.sh/master/README.md",
        ]
    },
    "git": {
        "name": "Git Commands",
        "urls": [
            "https://raw.githubusercontent.com/git/git/master/README.md",
            "https://raw.githubusercontent.com/git-tips/tips/master/README.md",
            "https://raw.githubusercontent.com/arslanbilal/git-cheat-sheet/master/README.md",
        ]
    },
    "docker": {
        "name": "Docker Commands",
        "urls": [
            "https://raw.githubusercontent.com/docker/docker.github.io/master/README.md",
            "https://raw.githubusercontent.com/wsargent/docker-cheat-sheet/master/README.md",
        ]
    },
    "kubectl": {
        "name": "Kubernetes/kubectl",
        "urls": [
            "https://raw.githubusercontent.com/kubernetes/kubectl/master/README.md",
            "https://raw.githubusercontent.com/dennyzhang/cheatsheet-kubernetes-A4/master/README.org",
        ]
    },
}


# =============================================================================
# Ollama Client
# =============================================================================

class OllamaClient:
    # Comprehensive embedding model patterns (prioritized)
    EMBEDDING_PATTERNS = [
        "nomic-embed", "bge-m3", "bge-large", "bge-base", "bge-small",
        "mxbai-embed", "all-minilm", "snowflake-arctic-embed",
        "multilingual-e5", "e5-large", "e5-base", "e5-small",
        "gte-large", "gte-base", "gte-small", "gte-qwen",
        "jina-embed", "paraphrase", "sentence-t5", "instructor",
        "text-embedding", "embed", "embedding"
    ]
    
    # Reranker model patterns
    RERANKER_PATTERNS = [
        "bge-reranker", "rerank", "ms-marco", "cross-encoder",
        "jina-reranker", "colbert"
    ]
    
    def __init__(self, api_url: str = "http://localhost:11434"):
        self.api_url = api_url.rstrip("/")
        self._session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        self._session.mount("http://", HTTPAdapter(max_retries=retry))
        self._stop_flag = False
    
    def stop_generation(self):
        self._stop_flag = True
    
    def reset_stop(self):
        self._stop_flag = False
    
    def is_stopped(self) -> bool:
        return self._stop_flag
    
    def is_available(self) -> bool:
        try:
            r = self._session.get(f"{self.api_url}/api/tags", timeout=5)
            return r.status_code == 200
        except:
            return False
    
    def get_models(self) -> List[str]:
        try:
            r = self._session.get(f"{self.api_url}/api/tags", timeout=30)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
        except:
            return []
    
    def get_embedding_models(self) -> List[str]:
        """Get embedding models with comprehensive pattern matching."""
        models = self.get_models()
        result = []
        
        # First pass: prioritized patterns
        for pattern in self.EMBEDDING_PATTERNS:
            for m in models:
                m_lower = m.lower()
                # Skip reranker models
                if any(rp in m_lower for rp in self.RERANKER_PATTERNS):
                    continue
                if pattern in m_lower and m not in result:
                    result.append(m)
        
        # Log found models
        if result:
            print(f"[Ollama] Found {len(result)} embedding models: {', '.join(result[:5])}{'...' if len(result) > 5 else ''}", file=sys.stderr)
        
        return result
    
    def get_reranker_models(self) -> List[str]:
        """Get reranker models for improved retrieval."""
        models = self.get_models()
        result = []
        
        for pattern in self.RERANKER_PATTERNS:
            for m in models:
                if pattern in m.lower() and m not in result:
                    result.append(m)
        
        if result:
            print(f"[Ollama] Found {len(result)} reranker models: {', '.join(result)}", file=sys.stderr)
        
        return result
    
    def get_chat_models(self) -> List[str]:
        """Get chat models, excluding embedding and reranker models."""
        models = self.get_models()
        exclude_patterns = self.EMBEDDING_PATTERNS[:10] + self.RERANKER_PATTERNS
        return [m for m in models if not any(x in m.lower() for x in exclude_patterns)]
    
    def embed(self, text: str, model: str) -> List[float]:
        text = text[:500] if len(text) > 500 else text
        r = self._session.post(
            f"{self.api_url}/api/embeddings",
            json={"model": model, "prompt": text},
            timeout=60
        )
        r.raise_for_status()
        return r.json().get("embedding", [])
    
    def translate(self, text: str, from_lang: str, to_lang: str) -> str:
        """Translate text using chat model for cross-lingual RAG search."""
        if not text.strip() or from_lang == to_lang:
            return text
        
        lang_names = {
            "zh": "Chinese", "en": "English", "ja": "Japanese",
            "ko": "Korean", "ru": "Russian", "fr": "French",
            "de": "German", "es": "Spanish", "pt": "Portuguese", "it": "Italian"
        }
        
        from_name = lang_names.get(from_lang, from_lang)
        to_name = lang_names.get(to_lang, to_lang)
        
        prompt = f"Translate the following text from {from_name} to {to_name}. Output ONLY the translation, nothing else:\n\n{text[:500]}"
        
        try:
            r = self._session.post(
                f"{self.api_url}/api/generate",
                json={"model": CONFIG.chat_model, "prompt": prompt, "stream": False},
                timeout=30
            )
            r.raise_for_status()
            return r.json().get("response", "").strip()
        except Exception as e:
            print(f"[Translation] Error: {e}", file=sys.stderr)
            return ""
    
    def chat_complete(self, messages: List[Dict], model: str, temperature: float = 0.7) -> str:
        """Non-streaming chat completion. Returns the full response text."""
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature}
        }
        try:
            r = self._session.post(
                f"{self.api_url}/api/chat",
                json=payload,
                timeout=300
            )
            r.raise_for_status()
            data = r.json()
            return data.get("message", {}).get("content", "")
        except Exception as e:
            print(f"[Ollama] chat_complete error: {e}", file=sys.stderr)
            return ""

    def chat_stream(self, messages: List[Dict], model: str, temperature: float = 0.7) -> Iterator[str]:
        self.reset_stop()
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature}
        }
        try:
            r = self._session.post(
                f"{self.api_url}/api/chat",
                json=payload,
                stream=True,
                timeout=300
            )
            r.raise_for_status()
            for line in r.iter_lines():
                if self._stop_flag:
                    r.close()
                    break
                if line:
                    try:
                        data = json.loads(line)
                        if "message" in data and "content" in data["message"]:
                            yield data["message"]["content"]
                        if data.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            yield f"\n\n[Error: {e}]"


OLLAMA = OllamaClient(CONFIG.ollama_url)


# =============================================================================
# Vector Database (uses abstraction layer from core.vector_db)
# =============================================================================


# =============================================================================
# Document Downloader & Indexer
# =============================================================================

class DocManager:
    def __init__(self, docs_dir: Path, chroma, ollama: OllamaClient):
        self.docs_dir = docs_dir
        self.chroma = chroma
        self.ollama = ollama
        self._session = requests.Session()
    
    def download_source(self, source_name: str) -> Tuple[int, List[str]]:
        if source_name not in DOC_SOURCES:
            print(f"[Download] Unknown source: {source_name}", file=sys.stderr)
            return 0, [f"Unknown source: {source_name}"]
        
        source = DOC_SOURCES[source_name]
        urls = source["urls"]
        downloaded = 0
        errors = []
        proxies = get_proxies()
        
        source_dir = self.docs_dir / source_name
        source_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"[Download] Starting {source_name}: {len(urls)} URLs", file=sys.stderr)
        if proxies:
            print(f"[Download] Using proxy: {proxies.get('http', 'N/A')}", file=sys.stderr)
        
        for url in urls:
            filename = url.split("/")[-1]
            try:
                r = self._session.get(url, timeout=30, proxies=proxies)
                r.raise_for_status()
                content = r.text
                
                # Convert to markdown if needed
                if filename.endswith(".rst"):
                    filename = filename.replace(".rst", ".md")
                elif filename.endswith(".py") or filename.endswith(".ipynb"):
                    content = f"```python\n{content}\n```"
                    filename = filename.replace(".py", ".md").replace(".ipynb", ".md")
                elif filename.endswith(".html"):
                    filename = filename.replace(".html", ".md")
                elif filename.endswith(".texi"):
                    filename = filename.replace(".texi", ".md")
                elif filename.endswith(".cpp"):
                    content = f"```cpp\n{content}\n```"
                    filename = filename.replace(".cpp", ".md")
                elif not filename.endswith(".md"):
                    filename += ".md"
                
                filepath = source_dir / filename
                filepath.write_text(content, encoding="utf-8")
                downloaded += 1
                print(f"[Download]   OK: {filename}", file=sys.stderr)
            except Exception as e:
                err_msg = f"{filename}: {type(e).__name__}"
                errors.append(err_msg)
                print(f"[Download]   FAIL: {err_msg}", file=sys.stderr)
            
            time.sleep(0.2)
        
        print(f"[Download] Completed {source_name}: {downloaded} success, {len(errors)} errors", file=sys.stderr)
        return downloaded, errors
    
    def index_source(self, source_name: str) -> Tuple[int, int]:
        if self.chroma is None or self.chroma.client is None:
            print(f"[Index] Skipped {source_name} - ChromaDB not available", file=sys.stderr)
            return 0, 0
        if not CONFIG.embedding_model:
            print(f"[Index] Skipped {source_name} - no embedding model configured", file=sys.stderr)
            return 0, 0
        
        source_dir = self.docs_dir / source_name
        if not source_dir.exists():
            print(f"[Index] Skipped {source_name} - directory not found", file=sys.stderr)
            return 0, 0
        
        files = list(source_dir.glob("*.md")) + list(source_dir.glob("*.txt"))
        if not files:
            print(f"[Index] Skipped {source_name} - no markdown/text files found", file=sys.stderr)
            return 0, 0
        
        print(f"[Index] Processing {source_name}: {len(files)} files", file=sys.stderr)
        
        documents = []
        embeddings = []
        metadatas = []
        ids = []
        detected_languages = set()
        
        for filepath in files:
            content = filepath.read_text(encoding="utf-8")
            # Detect document language for cross-lingual search
            doc_lang = detect_language(content)
            detected_languages.add(doc_lang)
            print(f"[Index]   {filepath.name}: detected language = {doc_lang}", file=sys.stderr)
            
            # Simple chunking
            chunks = self._chunk_text(content, CONFIG.chunk_size, CONFIG.chunk_overlap)
            file_chunks = 0
            
            for i, chunk in enumerate(chunks):
                if len(chunk.strip()) < 50:
                    continue
                try:
                    emb = self.ollama.embed(chunk, CONFIG.embedding_model)
                    doc_id = hashlib.md5(f"{filepath.name}_{i}".encode()).hexdigest()
                    
                    documents.append(chunk)
                    embeddings.append(emb)
                    metadatas.append({
                        "source": source_name,
                        "file": filepath.name,
                        "chunk": i,
                        "language": doc_lang
                    })
                    ids.append(doc_id)
                    file_chunks += 1
                except Exception as e:
                    print(f"[Index]   Error embedding chunk {i} of {filepath.name}: {e}", file=sys.stderr)
                    continue
            
            print(f"[Index]   {filepath.name}: {file_chunks} chunks", file=sys.stderr)
        
        if documents:
            self.chroma.add_documents(source_name, documents, embeddings, metadatas, ids)
            print(f"[Index] Added {len(documents)} chunks to collection '{source_name}'", file=sys.stderr)
            print(f"[Index] Languages detected: {', '.join(detected_languages)}", file=sys.stderr)
        
        return len(files), len(documents)
    
    def _chunk_text(self, text: str, chunk_size: int, overlap: int) -> List[str]:
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk)
            start = end - overlap
        return chunks
    
    def list_downloaded(self) -> List[Dict]:
        result = []
        if self.docs_dir.exists():
            for d in self.docs_dir.iterdir():
                if d.is_dir():
                    files = list(d.glob("*.md"))
                    result.append({"name": d.name, "files": len(files)})
        return result


# =============================================================================
# Web Search
# =============================================================================

class WebSearcher:
    def __init__(self):
        self._timeout = 15
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        })
    
    def _get_proxies(self):
        return get_proxies()
    
    def search(self, query: str, num_results: int = 5) -> List[Dict]:
        results = []
        proxies = self._get_proxies()
        
        if proxies:
            print(f"[WebSearch] Using proxy: {proxies.get('http', 'N/A')}", file=sys.stderr)
        
        # Try DuckDuckGo
        try:
            url = "https://html.duckduckgo.com/html/"
            resp = self._session.post(url, data={"q": query}, timeout=self._timeout, proxies=proxies)
            resp.raise_for_status()
            
            pattern = re.compile(
                r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>.*?'
                r'<a[^>]*class="result__snippet"[^>]*>([^<]*)</a>',
                re.DOTALL
            )
            
            for match in pattern.finditer(resp.text):
                if len(results) >= num_results:
                    break
                link, title, snippet = match.groups()
                if "uddg=" in link:
                    from urllib.parse import unquote, parse_qs
                    parsed = parse_qs(link.split("?")[-1])
                    link = unquote(parsed.get("uddg", [link])[0])
                
                results.append({
                    "title": title.strip(),
                    "url": link,
                    "snippet": snippet.strip()[:200],
                })
        except Exception as e:
            print(f"[WebSearch] DuckDuckGo error: {e}", file=sys.stderr)
        
        return results


WEB_SEARCHER = WebSearcher()


# =============================================================================
# Conversation Manager
# =============================================================================

class ConversationManager:
    def __init__(self, max_history: int = 20):
        self.max_history = max_history
        self._messages: List[Dict] = []
    
    def add(self, role: str, content: str):
        self._messages.append({"role": role, "content": content})
        if len(self._messages) > self.max_history:
            self._messages = self._messages[-self.max_history:]
    
    def get_messages(self, limit: int = 10) -> List[Dict]:
        return self._messages[-limit:]
    
    def get_all(self) -> List[Dict]:
        return self._messages.copy()
    
    def clear(self):
        self._messages.clear()


CONVERSATION = ConversationManager()


# =============================================================================
# Flask Application
# =============================================================================

app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB upload limit

# Register learning module Blueprint
from gangdan.learning_routes import learning_bp
app.register_blueprint(learning_bp)

# Initialize components
DATA_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DIR.mkdir(parents=True, exist_ok=True)
load_config()

try:
    from gangdan.core.vector_db import create_vector_db_auto
    CHROMA = create_vector_db_auto(str(CHROMA_DIR), preferred=CONFIG.vector_db_type)
except BaseException as e:
    print(f"[CRITICAL] Vector DB init failed: {e}", file=sys.stderr)
    print(f"[CRITICAL] App will run without knowledge base features", file=sys.stderr)
    CHROMA = None

DOC_MANAGER = DocManager(DOCS_DIR, CHROMA, OLLAMA)




# =============================================================================
# API Routes
# =============================================================================

@app.route('/')
def index():
    lang = request.args.get('lang', CONFIG.language)
    CONFIG.language = lang
    save_config()
    
    return render_template(
        'index.html',
        lang=lang,
        languages=LANGUAGES,
        t=t,
        config=CONFIG,
        doc_sources=DOC_SOURCES,
        translations_json=json.dumps(TRANSLATIONS, ensure_ascii=False)
    )


@app.route('/api/models')
def get_models():
    OLLAMA.api_url = CONFIG.ollama_url
    return jsonify({
        "available": OLLAMA.is_available(),
        "chat_models": OLLAMA.get_chat_models(),
        "embed_models": OLLAMA.get_embedding_models(),
        "reranker_models": OLLAMA.get_reranker_models(),
        "current_chat": CONFIG.chat_model,
        "current_embed": CONFIG.embedding_model,
        "current_reranker": CONFIG.reranker_model,
        "vector_db_type": CONFIG.vector_db_type,
    })


@app.route('/api/settings', methods=['POST'])
def update_settings():
    data = request.json
    
    if 'ollama_url' in data:
        CONFIG.ollama_url = data['ollama_url']
        OLLAMA.api_url = data['ollama_url']
    if 'chat_model' in data:
        CONFIG.chat_model = data['chat_model']
    if 'embed_model' in data:
        CONFIG.embedding_model = data['embed_model']
    if 'reranker_model' in data:
        CONFIG.reranker_model = data['reranker_model']
    if 'proxy_mode' in data:
        CONFIG.proxy_mode = data['proxy_mode']
    if 'proxy_http' in data:
        CONFIG.proxy_http = data['proxy_http']
    if 'proxy_https' in data:
        CONFIG.proxy_https = data['proxy_https']
    if 'strict_kb_mode' in data:
        CONFIG.strict_kb_mode = bool(data['strict_kb_mode'])
    if 'vector_db_type' in data:
        CONFIG.vector_db_type = data['vector_db_type']
    
    save_config()
    return jsonify({"success": True, "message": "Settings saved"})


@app.route('/api/set-language', methods=['POST'])
def set_language():
    data = request.json
    lang = data.get('language', 'zh')
    if lang in LANGUAGES:
        CONFIG.language = lang
        save_config()
        return jsonify({"success": True, "language": lang})
    return jsonify({"success": False, "message": "Unsupported language"}), 400


@app.route('/api/test-connection', methods=['POST'])
def test_connection():
    data = request.json
    url = data.get('url', CONFIG.ollama_url)
    
    try:
        r = requests.get(f"{url.rstrip('/')}/api/tags", timeout=5)
        if r.status_code == 200:
            return jsonify({"success": True, "message": "Connection successful"})
        return jsonify({"success": False, "message": f"HTTP {r.status_code}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    message = data.get('message', '')
    use_kb = data.get('use_kb', True)
    use_web = data.get('use_web', False)
    kb_scope = data.get('kb_scope', None)
    
    if not CONFIG.chat_model:
        def error_stream():
            error_data = {'content': 'Error: No chat model selected', 'done': True}
            yield f"data: {json.dumps(error_data)}\n\n"
        return Response(error_stream(), mimetype='text/event-stream')
    
    def generate():
        context = ""
        
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"[Chat] New message received", file=sys.stderr)
        print(f"[Chat] Query: {message[:100]}{'...' if len(message) > 100 else ''}", file=sys.stderr)
        print(f"[Chat] Options: KB={use_kb}, Web={use_web}", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        
        # Web search
        if use_web:
            print(f"\n[WebSearch] Searching for: {message[:50]}...", file=sys.stderr)
            try:
                results = WEB_SEARCHER.search(message)
                print(f"[WebSearch] Found {len(results)} results", file=sys.stderr)
                
                if results:
                    context += "\n--- Web Results ---\n"
                    for i, r in enumerate(results[:3]):
                        context += f"[{r['title']}] {r['snippet']}\n"
                        print(f"[WebSearch]   {i+1}. {r['title'][:50]}...", file=sys.stderr)
                        print(f"[WebSearch]      URL: {r['url'][:60]}...", file=sys.stderr)
                    
                    print(f"[WebSearch] Using top {min(3, len(results))} results in context", file=sys.stderr)
                else:
                    print(f"[WebSearch] No results found", file=sys.stderr)
            except Exception as e:
                print(f"[WebSearch] Error: {type(e).__name__}: {e}", file=sys.stderr)
        
        # RAG retrieval with cross-lingual search
        kb_references = []  # Track sources for citations
        if use_kb and CONFIG.embedding_model:
            print(f"\n[RAG] Searching knowledge base (cross-lingual)...", file=sys.stderr)
            print(f"[RAG] Embedding model: {CONFIG.embedding_model}", file=sys.stderr)
            
            try:
                # 1. Detect query language
                query_lang = detect_language(message)
                print(f"[RAG] Query language: {query_lang}", file=sys.stderr)
                
                collections = CHROMA.list_collections()
                if kb_scope is not None:
                    collections = [c for c in collections if c in kb_scope]
                print(f"[RAG] Querying collections: {', '.join(collections) if collections else 'None'}", file=sys.stderr)
                
                # 2. Get languages present in selected KBs by sampling metadata
                target_langs = set()
                for coll_name in collections:
                    try:
                        sample = CHROMA.get_documents(coll_name, limit=20, include=["metadatas"])
                        for meta in sample.get("metadatas", []):
                            if meta and meta.get("language"):
                                target_langs.add(meta["language"])
                    except Exception:
                        pass
                
                # Remove "unknown" from target languages for translation
                target_langs.discard("unknown")
                print(f"[RAG] Target languages in KBs: {target_langs if target_langs else 'none detected'}", file=sys.stderr)
                
                # 3. Create query variants (original + translations)
                query_variants = {query_lang: message}
                for target_lang in target_langs:
                    if target_lang != query_lang:
                        translated = OLLAMA.translate(message, query_lang, target_lang)
                        if translated and translated != message:
                            query_variants[target_lang] = translated
                            print(f"[RAG] Translated to {target_lang}: {translated[:50]}{'...' if len(translated) > 50 else ''}", file=sys.stderr)
                
                print(f"[RAG] Query variants: {list(query_variants.keys())}", file=sys.stderr)
                
                # 4. Embed all variants and search
                all_results = []
                for lang, query_text in query_variants.items():
                    try:
                        query_emb = OLLAMA.embed(query_text, CONFIG.embedding_model)
                        for coll_name in collections:
                            results = CHROMA.search(coll_name, query_emb, top_k=5)
                            for r in results:
                                if r.get('distance', 1) < 0.5:  # Threshold for relevance
                                    meta = r.get('metadata', {})
                                    all_results.append({
                                        "coll": coll_name,
                                        "doc": r['document'],
                                        "dist": r['distance'],
                                        "id": r.get('id', hashlib.md5(r['document'][:100].encode()).hexdigest()),
                                        "query_lang": lang,
                                        "file": meta.get('file', 'unknown'),
                                        "source": meta.get('source', coll_name),
                                    })
                    except Exception as e:
                        print(f"[RAG] Search error for {lang}: {e}", file=sys.stderr)
                
                # 5. Deduplicate by document ID, keep best score
                seen = {}
                for r in all_results:
                    if r['id'] not in seen or r['dist'] < seen[r['id']]['dist']:
                        seen[r['id']] = r
                
                # 6. Sort by distance and build context with citations
                merged = sorted(seen.values(), key=lambda x: x['dist'])
                total_hits = len(merged)
                
                # Track unique sources for references
                sources_used = set()
                for r in merged[:CONFIG.top_k]:
                    source_file = r.get('file', 'unknown')
                    sources_used.add(source_file)
                    # Add content with source attribution
                    context += f"\n[Source: {source_file}]\n{r['doc'][:500]}\n"
                
                # Build references list
                kb_references = sorted(list(sources_used))
                
                if total_hits == 0:
                    print(f"[RAG] No relevant documents found (threshold: distance < 0.5)", file=sys.stderr)
                else:
                    print(f"[RAG] Total: {total_hits} relevant documents after dedup (using top {min(total_hits, CONFIG.top_k)})", file=sys.stderr)
                    print(f"[RAG] Sources: {', '.join(kb_references)}", file=sys.stderr)
                    
            except Exception as e:
                print(f"[RAG] Error: {type(e).__name__}: {e}", file=sys.stderr)
        elif use_kb and not CONFIG.embedding_model:
            print(f"[RAG] Skipped - no embedding model configured", file=sys.stderr)
        
        print(f"\n[Chat] Context length: {len(context)} chars", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)
        
        # Strict KB mode: refuse to answer if KB enabled but no results found
        if use_kb and CONFIG.strict_kb_mode and not kb_references and not use_web:
            error_msg = t("kb_no_results_strict")
            error_data = {'content': error_msg, 'done': True}
            yield f"data: {json.dumps(error_data)}\n\n"
            return
        
        # Build messages
        messages = CONVERSATION.get_messages(10)
        
        system_prompt = "You are a helpful programming assistant."
        if context:
            system_prompt += f"\n\nContext:\n{context}"
            if kb_references:
                system_prompt += "\n\nIMPORTANT: When answering, cite the source files in your response where appropriate."
        
        chat_messages = [{"role": "system", "content": system_prompt}]
        chat_messages.extend(messages)
        chat_messages.append({"role": "user", "content": message})
        
        # Stream response
        full_response = ""
        try:
            for chunk in OLLAMA.chat_stream(chat_messages, CONFIG.chat_model):
                if OLLAMA.is_stopped():
                    stop_data = {'content': '\n\n[Stopped]', 'stopped': True}
                    yield f"data: {json.dumps(stop_data)}\n\n"
                    break
                full_response += chunk
                yield f"data: {json.dumps({'content': chunk})}\n\n"
            
            # Append references if we have KB sources
            if kb_references and full_response:
                ref_header = t("references")
                ref_text = f"\n\n---\n**{ref_header}:**\n"
                for ref in kb_references:
                    ref_text += f"- {ref}\n"
                ref_data = {'content': ref_text}
                yield f"data: {json.dumps(ref_data)}\n\n"
                full_response += ref_text
            
            yield f"data: {json.dumps({'done': True})}\n\n"
            
            # Save to conversation
            CONVERSATION.add("user", message)
            CONVERSATION.add("assistant", full_response)
        except Exception as e:
            error_data = {'content': f'\n\nError: {e}', 'done': True}
            yield f"data: {json.dumps(error_data)}\n\n"
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@app.route('/api/stop', methods=['POST'])
def stop_generation():
    OLLAMA.stop_generation()
    return jsonify({"success": True})


@app.route('/api/clear', methods=['POST'])
def clear_chat():
    CONVERSATION.clear()
    return jsonify({"success": True})


@app.route('/api/export')
def export_chat():
    messages = CONVERSATION.get_all()
    
    lines = [
        f"# {t('app_title')} - Chat Export",
        f"*Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        "",
        "---",
        ""
    ]
    
    for i, msg in enumerate(messages):
        role = "🧑 User" if msg["role"] == "user" else "🤖 Assistant"
        lines.append(f"### {role}")
        lines.append("")
        lines.append(msg["content"])
        lines.append("")
        lines.append("---")
        lines.append("")
    
    content = "\n".join(lines)
    filename = f"chat_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    
    return jsonify({"content": content, "filename": filename})


@app.route('/api/save-conversation')
def save_conversation():
    messages = CONVERSATION.get_all()
    content = {
        "version": "1.0",
        "app": "GangDan",
        "exported_at": datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        "messages": messages
    }
    filename = f"conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return jsonify({"success": True, "content": content, "filename": filename})


@app.route('/api/load-conversation', methods=['POST'])
def load_conversation():
    data = request.json
    conversation = data.get('conversation', {})
    messages = conversation.get('messages', [])

    if not isinstance(messages, list):
        return jsonify({"success": False, "error": t('invalid_conversation_file')}), 400

    for msg in messages:
        if not isinstance(msg, dict) or 'role' not in msg or 'content' not in msg:
            return jsonify({"success": False, "error": t('invalid_conversation_file')}), 400

    CONVERSATION.clear()
    for msg in messages:
        CONVERSATION.add(msg['role'], msg['content'])

    return jsonify({"success": True, "message_count": len(messages)})


@app.route('/api/docs/list')
def list_docs():
    return jsonify(DOC_MANAGER.list_downloaded())


@app.route('/api/docs/download', methods=['POST'])
def download_docs():
    data = request.json
    source = data.get('source')
    
    downloaded, errors = DOC_MANAGER.download_source(source)
    return jsonify({"downloaded": downloaded, "errors": errors})


@app.route('/api/docs/index', methods=['POST'])
def index_docs():
    data = request.json
    source = data.get('source')
    
    files, chunks = DOC_MANAGER.index_source(source)
    return jsonify({"files": files, "chunks": chunks})


@app.route('/api/docs/batch-download', methods=['POST'])
def batch_download_docs():
    """Batch download multiple documentation sources."""
    data = request.json
    sources = data.get('sources', [])
    
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"[BatchDownload] Starting batch download for {len(sources)} sources", file=sys.stderr)
    print(f"[BatchDownload] Sources: {', '.join(sources)}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    
    results = []
    total_downloaded = 0
    total_errors = 0
    
    for source in sources:
        print(f"[BatchDownload] Downloading: {source}...", file=sys.stderr)
        downloaded, errors = DOC_MANAGER.download_source(source)
        total_downloaded += downloaded
        total_errors += len(errors)
        
        results.append({
            "source": source,
            "downloaded": downloaded,
            "errors": len(errors),
            "error_details": errors
        })
        
        if errors:
            for err in errors:
                print(f"[BatchDownload]   Error in {source}: {err}", file=sys.stderr)
        print(f"[BatchDownload]   {source}: {downloaded} files downloaded, {len(errors)} errors", file=sys.stderr)
    
    print(f"\n[BatchDownload] Summary: {total_downloaded} total files, {total_errors} total errors", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)
    
    return jsonify({"results": results, "total_downloaded": total_downloaded, "total_errors": total_errors})


@app.route('/api/docs/batch-index', methods=['POST'])
def batch_index_docs():
    """Batch index multiple documentation sources."""
    data = request.json
    sources = data.get('sources', [])
    
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"[BatchIndex] Starting batch indexing for {len(sources)} sources", file=sys.stderr)
    print(f"[BatchIndex] Embedding model: {CONFIG.embedding_model or 'NOT SET'}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    
    if not CONFIG.embedding_model:
        print(f"[BatchIndex] ERROR: No embedding model selected!", file=sys.stderr)
        return jsonify({"error": "No embedding model selected", "results": []})
    
    results = []
    total_files = 0
    total_chunks = 0
    
    for source in sources:
        print(f"[BatchIndex] Indexing: {source}...", file=sys.stderr)
        files, chunks = DOC_MANAGER.index_source(source)
        total_files += files
        total_chunks += chunks
        
        results.append({
            "source": source,
            "files": files,
            "chunks": chunks
        })
        print(f"[BatchIndex]   {source}: {files} files -> {chunks} chunks indexed", file=sys.stderr)
    
    print(f"\n[BatchIndex] Summary: {total_files} total files, {total_chunks} total chunks", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)
    
    return jsonify({"results": results, "total_files": total_files, "total_chunks": total_chunks})


@app.route('/api/docs/web-search-to-kb', methods=['POST'])
def web_search_to_kb():
    """Search the web and index results into knowledge base."""
    data = request.json
    query = data.get('query', '')
    kb_name = data.get('name', 'web_search').replace(' ', '_').lower()
    
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"[WebSearchToKB] Query: {query}", file=sys.stderr)
    print(f"[WebSearchToKB] Target KB: {kb_name}", file=sys.stderr)
    print(f"[WebSearchToKB] Embedding model: {CONFIG.embedding_model or 'NOT SET'}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    
    if not CONFIG.embedding_model:
        print(f"[WebSearchToKB] ERROR: No embedding model selected!", file=sys.stderr)
        return jsonify({"error": "No embedding model selected", "found": 0, "indexed": 0})
    
    if not query:
        return jsonify({"error": "No query provided", "found": 0, "indexed": 0})
    
    # Search the web
    print(f"[WebSearchToKB] Searching web...", file=sys.stderr)
    try:
        results = WEB_SEARCHER.search(query, num_results=10)
        print(f"[WebSearchToKB] Found {len(results)} results", file=sys.stderr)
    except Exception as e:
        print(f"[WebSearchToKB] Search error: {e}", file=sys.stderr)
        return jsonify({"error": str(e), "found": 0, "indexed": 0})
    
    if not results:
        print(f"[WebSearchToKB] No results found", file=sys.stderr)
        return jsonify({"found": 0, "indexed": 0})
    
    # Log found results
    for i, r in enumerate(results):
        print(f"[WebSearchToKB]   {i+1}. {r['title'][:50]}... ({r['url'][:50]}...)", file=sys.stderr)
    
    # Index results into KB
    print(f"\n[WebSearchToKB] Indexing results into KB '{kb_name}'...", file=sys.stderr)
    
    documents = []
    embeddings = []
    metadatas = []
    ids = []
    
    for i, result in enumerate(results):
        # Create document from search result
        doc_text = f"Title: {result['title']}\nURL: {result['url']}\nContent: {result['snippet']}"
        
        try:
            emb = OLLAMA.embed(doc_text, CONFIG.embedding_model)
            doc_id = hashlib.md5(f"{kb_name}_{query}_{i}".encode()).hexdigest()
            
            documents.append(doc_text)
            embeddings.append(emb)
            metadatas.append({
                "source": "web_search",
                "query": query,
                "title": result['title'],
                "url": result['url'],
                "index": i
            })
            ids.append(doc_id)
            print(f"[WebSearchToKB]   Embedded result {i+1}: {result['title'][:40]}...", file=sys.stderr)
        except Exception as e:
            print(f"[WebSearchToKB]   Error embedding result {i+1}: {e}", file=sys.stderr)
            continue
    
    if documents:
        try:
            CHROMA.add_documents(kb_name, documents, embeddings, metadatas, ids)
            print(f"\n[WebSearchToKB] Successfully indexed {len(documents)} documents to '{kb_name}'", file=sys.stderr)
        except Exception as e:
            print(f"[WebSearchToKB] Error adding to ChromaDB: {e}", file=sys.stderr)
            return jsonify({"error": str(e), "found": len(results), "indexed": 0})
    
    print(f"{'='*60}\n", file=sys.stderr)
    
    return jsonify({
        "found": len(results),
        "indexed": len(documents),
        "kb_name": kb_name
    })


@app.route('/api/docs/upload', methods=['POST'])
def upload_docs():
    """Upload user documents to create a custom knowledge base.
    
    Supports duplicate handling with 'duplicate_action' parameter:
    - 'skip': skip duplicate files
    - 'overwrite': overwrite duplicate files
    """
    kb_name = request.form.get('kb_name', '').strip()
    if not kb_name:
        return jsonify({"success": False, "error": "Knowledge base name is required"}), 400

    files = request.files.getlist('files')
    if not files:
        return jsonify({"success": False, "error": "No files provided"}), 400

    duplicate_action = request.form.get('duplicate_action', 'skip')  # 'skip' or 'overwrite'
    
    internal_name = sanitize_kb_name(kb_name)
    target_dir = DOCS_DIR / internal_name
    target_dir.mkdir(parents=True, exist_ok=True)

    saved_count = 0
    skipped_count = 0
    overwritten_count = 0
    errors = []
    
    for f in files:
        if not f.filename:
            continue
        ext = Path(f.filename).suffix.lower()
        if ext not in ('.md', '.txt'):
            errors.append(f"{f.filename}: unsupported format (only .md and .txt)")
            continue
        
        safe_name = Path(f.filename).name
        target_path = target_dir / safe_name
        
        # Check if file already exists
        if target_path.exists():
            if duplicate_action == 'skip':
                skipped_count += 1
                print(f"[Upload] Skipped duplicate: {safe_name}", file=sys.stderr)
                continue
            else:  # overwrite
                overwritten_count += 1
                print(f"[Upload] Overwriting: {safe_name}", file=sys.stderr)
        
        f.save(str(target_path))
        saved_count += 1

    total_files = saved_count + skipped_count
    if total_files == 0:
        return jsonify({"success": False, "error": "No valid files uploaded", "details": errors}), 400

    save_user_kb(internal_name, kb_name, total_files)
    print(f"[Upload] Saved {saved_count} files (skipped: {skipped_count}, overwritten: {overwritten_count}) to '{internal_name}'", file=sys.stderr)

    return jsonify({
        "success": True,
        "name": internal_name,
        "display_name": kb_name,
        "file_count": total_files,
        "saved_count": saved_count,
        "skipped_count": skipped_count,
        "overwritten_count": overwritten_count,
        "errors": errors,
    })


@app.route('/api/docs/check-duplicates', methods=['POST'])
def check_duplicates():
    """Check for duplicate files before upload.
    
    Returns a list of filenames that already exist in the target KB.
    """
    kb_name = request.form.get('kb_name', '').strip()
    if not kb_name:
        return jsonify({"success": False, "error": "Knowledge base name is required"}), 400

    files = request.files.getlist('files')
    if not files:
        return jsonify({"success": False, "error": "No files provided"}), 400

    internal_name = sanitize_kb_name(kb_name)
    target_dir = DOCS_DIR / internal_name
    
    duplicates = []
    new_files = []
    
    for f in files:
        if not f.filename:
            continue
        ext = Path(f.filename).suffix.lower()
        if ext not in ('.md', '.txt'):
            continue
        
        safe_name = Path(f.filename).name
        target_path = target_dir / safe_name
        
        if target_path.exists():
            duplicates.append(safe_name)
        else:
            new_files.append(safe_name)
    
    return jsonify({
        "success": True,
        "kb_name": internal_name,
        "duplicates": duplicates,
        "new_files": new_files,
        "has_duplicates": len(duplicates) > 0,
    })


@app.route('/api/kb/list')
def list_kbs():
    """List all available knowledge bases (built-in + user-created)."""
    # Get indexed collections and their doc counts
    stats = {}
    if CHROMA:
        try:
            stats = CHROMA.get_stats()
        except Exception:
            pass

    # Helper to get languages from a collection
    def get_collection_languages(coll_name: str) -> List[str]:
        if not CHROMA or not CHROMA.is_available:
            return []
        try:
            sample = CHROMA.get_documents(coll_name, limit=50, include=["metadatas"])
            langs = set()
            for meta in sample.get("metadatas", []):
                if meta and meta.get("language"):
                    langs.add(meta["language"])
            langs.discard("unknown")
            return sorted(list(langs))
        except Exception:
            return []

    user_kbs = load_user_kbs()
    result = []

    # Built-in doc sources that are indexed
    for key in DOC_SOURCES:
        if key in stats:
            result.append({
                "name": key,
                "display_name": DOC_SOURCES[key]["name"],
                "type": "builtin",
                "doc_count": stats.get(key, 0),
                "languages": get_collection_languages(key),
            })

    # User-created knowledge bases
    for internal_name, meta in user_kbs.items():
        result.append({
            "name": internal_name,
            "display_name": meta.get("display_name", internal_name),
            "type": "user",
            "doc_count": stats.get(internal_name, 0),
            "languages": meta.get("languages", []) or get_collection_languages(internal_name),
        })

    # Any other collections not in DOC_SOURCES or user_kbs (e.g. web search KBs)
    known = set(DOC_SOURCES.keys()) | set(user_kbs.keys())
    for coll_name in stats:
        if coll_name not in known:
            result.append({
                "name": coll_name,
                "display_name": coll_name,
                "type": "other",
                "doc_count": stats.get(coll_name, 0),
                "languages": get_collection_languages(coll_name),
            })

    return jsonify({"kbs": result})


@app.route('/api/kb/reindex', methods=['POST'])
def reindex_kb():
    """Re-index an existing knowledge base to add language metadata.
    
    This is useful for KBs created before language detection was added,
    enabling cross-lingual search for existing documents.
    """
    data = request.json
    kb_name = data.get('name', '').strip()
    
    if not kb_name:
        return jsonify({"success": False, "error": "KB name is required"}), 400
    
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"[Reindex] Starting reindex for: {kb_name}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    
    # Check if KB directory exists
    source_dir = DOCS_DIR / kb_name
    if not source_dir.exists():
        return jsonify({"success": False, "error": f"KB directory not found: {kb_name}"}), 404
    
    # Delete existing collection if present
    if CHROMA and CHROMA.is_available:
        try:
            CHROMA.delete_collection(kb_name)
            print(f"[Reindex] Deleted existing collection: {kb_name}", file=sys.stderr)
        except Exception:
            print(f"[Reindex] No existing collection to delete", file=sys.stderr)
    
    # Re-index with language detection
    files, chunks = DOC_MANAGER.index_source(kb_name)
    
    # Update user KB manifest with detected languages if it's a user KB
    user_kbs = load_user_kbs()
    if kb_name in user_kbs:
        # Get detected languages from the new collection
        detected_langs = []
        if CHROMA and CHROMA.is_available:
            try:
                sample = CHROMA.get_documents(kb_name, limit=50, include=["metadatas"])
                langs = set()
                for meta in sample.get("metadatas", []):
                    if meta and meta.get("language"):
                        langs.add(meta["language"])
                langs.discard("unknown")
                detected_langs = sorted(list(langs))
            except Exception:
                pass
        
        # Update manifest
        save_user_kb(
            kb_name,
            user_kbs[kb_name].get("display_name", kb_name),
            user_kbs[kb_name].get("file_count", files),
            detected_langs
        )
        print(f"[Reindex] Updated manifest with languages: {detected_langs}", file=sys.stderr)
    
    print(f"[Reindex] Completed: {files} files, {chunks} chunks", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)
    
    return jsonify({
        "success": True,
        "name": kb_name,
        "files": files,
        "chunks": chunks
    })


@app.route('/api/kb/literature-review', methods=['POST'])
def generate_literature_review():
    """Generate academic-style literature review for selected knowledge bases.
    
    This endpoint retrieves documents from selected KBs and uses the LLM
    to generate a scholarly literature review with concise summaries of each document.
    """
    data = request.json
    kb_names = data.get('kb_names', [])
    user_lang = data.get('language', CONFIG.language)
    
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"[LitReview] Generating literature review", file=sys.stderr)
    print(f"[LitReview] KBs: {kb_names}", file=sys.stderr)
    print(f"[LitReview] Language: {user_lang}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    
    if not kb_names:
        return jsonify({"success": False, "error": t("no_kb_selected", user_lang)})
    
    if not CONFIG.chat_model:
        return jsonify({"success": False, "error": "No chat model configured"})
    
    # Collect all documents from selected KBs
    all_docs = []
    for kb_name in kb_names:
        kb_dir = DOCS_DIR / kb_name
        if kb_dir.exists():
            for filepath in list(kb_dir.glob("*.md")) + list(kb_dir.glob("*.txt")):
                try:
                    content = filepath.read_text(encoding="utf-8")
                    # Truncate very long documents
                    if len(content) > 5000:
                        content = content[:5000] + "\n\n[... content truncated ...]"
                    all_docs.append({
                        "kb": kb_name,
                        "file": filepath.name,
                        "content": content
                    })
                except Exception as e:
                    print(f"[LitReview] Error reading {filepath}: {e}", file=sys.stderr)
    
    if not all_docs:
        return jsonify({"success": False, "error": "No documents found in selected knowledge bases"})
    
    print(f"[LitReview] Found {len(all_docs)} documents", file=sys.stderr)
    
    # Language mapping for prompt
    LANG_NAMES = {
        "zh": "Chinese (简体中文)", "en": "English", "ja": "Japanese (日本語)",
        "fr": "French (Français)", "ru": "Russian (Русский)", "de": "German (Deutsch)",
        "it": "Italian (Italiano)", "es": "Spanish (Español)", "pt": "Portuguese (Português)",
        "ko": "Korean (한국어)"
    }
    lang_name = LANG_NAMES.get(user_lang, "English")
    
    def generate():
        """Stream the literature review generation."""
        # Header
        header = f"# {t('lit_review', user_lang)}\n\n"
        yield f"data: {json.dumps({'content': header})}\n\n"
        
        for i, doc in enumerate(all_docs):
            print(f"[LitReview] Processing document {i+1}/{len(all_docs)}: {doc['file']}", file=sys.stderr)
            
            # Generate summary for this document
            prompt = f"""You are an academic researcher writing a literature review. Analyze the following document and provide a concise, scholarly summary.

IMPORTANT: 
- Respond ONLY in {lang_name}
- Use formal academic language with precise terminology
- Be concise but comprehensive (2-4 sentences per document)
- Focus on key contributions, methodologies, and findings
- Maintain scholarly objectivity and rigor

Document source: {doc['file']}
Document content:
---
{doc['content'][:3000]}
---

Provide a single paragraph academic summary of this document. Do not include any headers or formatting, just the summary paragraph."""
            
            # Output document header
            doc_header = f"\n## {doc['file']}\n**Source:** {doc['kb']}\n\n"
            yield f"data: {json.dumps({'content': doc_header})}\n\n"
            
            # Stream the LLM response
            try:
                messages = [{"role": "user", "content": prompt}]
                for chunk in OLLAMA.chat_stream(messages, CONFIG.chat_model, temperature=0.3):
                    if OLLAMA.is_stopped():
                        yield f"data: {json.dumps({'content': '\\n\\n[Stopped]', 'stopped': True})}\n\n"
                        return
                    yield f"data: {json.dumps({'content': chunk})}\n\n"
                
                # Add spacing after each summary
                yield f"data: {json.dumps({'content': '\\n\\n---\\n'})}\n\n"
                
            except Exception as e:
                error_msg = f"\n*Error generating summary: {e}*\n\n"
                yield f"data: {json.dumps({'content': error_msg})}\n\n"
        
        # Completion marker
        yield f"data: {json.dumps({'done': True})}\n\n"
        print(f"[LitReview] Generation complete", file=sys.stderr)
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@app.route('/api/execute', methods=['POST'])
def execute_code():
    """Execute code in various languages."""
    data = request.json
    code = data.get('code', '')
    language = data.get('language', '').lower()
    
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"[Execute] Language: {language}", file=sys.stderr)
    print(f"[Execute] Code length: {len(code)} chars", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    
    # Map language aliases
    lang_map = {
        'py': 'python', 'python3': 'python',
        'js': 'javascript', 'node': 'javascript',
        'sh': 'bash', 'shell': 'bash'
    }
    language = lang_map.get(language, language)
    
    # Determine interpreter
    interpreters = {
        'python': ['python3', 'python'],
        'javascript': ['node'],
        'bash': ['bash', 'sh']
    }
    
    if language not in interpreters:
        return jsonify({"error": f"Unsupported language: {language}"})
    
    # Find available interpreter
    interpreter = None
    for cmd in interpreters[language]:
        try:
            subprocess.run([cmd, '--version'], capture_output=True, timeout=5)
            interpreter = cmd
            break
        except:
            continue
    
    if not interpreter:
        return jsonify({"error": f"No interpreter found for {language}"})
    
    print(f"[Execute] Using interpreter: {interpreter}", file=sys.stderr)
    
    try:
        # Create temp file for code
        suffix = {
            'python': '.py',
            'javascript': '.js',
            'bash': '.sh'
        }.get(language, '.txt')
        
        with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as f:
            f.write(code)
            temp_path = f.name
        
        # Execute with timeout
        result = subprocess.run(
            [interpreter, temp_path],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(DATA_DIR)
        )
        
        # Cleanup
        os.unlink(temp_path)
        
        output = result.stdout
        if result.stderr:
            output += "\n[stderr]\n" + result.stderr if output else result.stderr
        
        print(f"[Execute] Exit code: {result.returncode}", file=sys.stderr)
        print(f"[Execute] Output length: {len(output)} chars", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)
        
        return jsonify({
            "output": output,
            "exit_code": result.returncode,
            "error": None if result.returncode == 0 else f"Exit code: {result.returncode}"
        })
        
    except subprocess.TimeoutExpired:
        print(f"[Execute] Timeout after 30s", file=sys.stderr)
        return jsonify({"error": "Execution timed out (30s limit)", "output": ""})
    except Exception as e:
        print(f"[Execute] Error: {type(e).__name__}: {e}", file=sys.stderr)
        return jsonify({"error": str(e), "output": ""})


@app.route('/api/ai-command', methods=['POST'])
def ai_command():
    """Generate shell command or provide analysis using AI based on user description."""
    data = request.json
    query = data.get('query', '')
    terminal_context = data.get('terminal_context', '')
    chat_history = data.get('chat_history', [])
    force_regenerate = data.get('force_regenerate', False)
    context_status = data.get('context_status', {})
    user_lang = data.get('language', CONFIG.language)
    
    # Map language codes to full names for the prompt
    LANG_NAMES = {"zh": "Chinese (简体中文)", "en": "English", "ja": "Japanese (日本語)", "fr": "French (Français)", 
                  "ru": "Russian (Русский)", "de": "German (Deutsch)", "it": "Italian (Italiano)", 
                  "es": "Spanish (Español)", "pt": "Portuguese (Português)", "ko": "Korean (한국어)"}
    lang_name = LANG_NAMES.get(user_lang, "English")
    
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"[AI-Command] Query: {query}", file=sys.stderr)
    print(f"[AI-Command] Language: {user_lang} ({lang_name})", file=sys.stderr)
    print(f"[AI-Command] Force regenerate: {force_regenerate}", file=sys.stderr)
    if context_status:
        print(f"[AI-Command] Context status: {context_status.get('reason', 'unknown')}", file=sys.stderr)
    if terminal_context:
        print(f"[AI-Command] Terminal context: {len(terminal_context)} chars", file=sys.stderr)
    if chat_history:
        print(f"[AI-Command] Chat history: {len(chat_history)} messages", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    
    if not query:
        return jsonify({"error": "No query provided"})
    
    if not CONFIG.chat_model:
        return jsonify({"error": "No chat model configured"})
    
    # Build context section if terminal output is available
    context_section = ""
    if terminal_context:
        # Check for errors in terminal output
        has_error = any(err in terminal_context.lower() for err in ['error', 'failed', 'not found', 'permission denied', 'no such file', 'command not found'])
        
        context_section = f"""
CURRENT TERMINAL CONTEXT (recent commands and output):
```
{terminal_context[-2000:]}
```
{"NOTE: There appear to be ERRORS in the terminal output. Consider this when generating your response." if has_error else ""}
"""
    
    # Build chat history context
    history_context = ""
    if chat_history:
        history_context = "\n\nPREVIOUS CONVERSATION:\n"
        for msg in chat_history[-6:]:
            role = "User" if msg.get('role') == 'user' else "Assistant"
            history_context += f"{role}: {msg.get('content', '')[:300]}\n"
    
    # Add regeneration instruction if needed
    regen_instruction = ""
    if force_regenerate:
        reason = context_status.get('reason', 'unknown')
        if reason == 'stale':
            regen_instruction = "\nIMPORTANT: Previous context is outdated. Generate a FRESH command to get current information."
        elif reason == 'low_relevance':
            regen_instruction = "\nIMPORTANT: Previous context doesn't match well. Generate a NEW appropriate command."
        elif reason == 'no_context':
            regen_instruction = "\nNOTE: No previous execution context available. Generate an appropriate command."
        elif reason == 'session_stale':
            regen_instruction = "\nIMPORTANT: Session has been idle. Generate a fresh command for current state."
    
    # Determine if user wants a command or analysis/summary
    analysis_keywords = ['explain', 'summarize', 'analyze', 'what', 'why', 'how', 'describe', 'interpret', 
                         '解释', '总结', '分析', '什么', '为什么', '怎么', '描述', '整理',
                         'detail', 'verbose', '详细', '详解', '展开']
    needs_analysis = any(kw in query.lower() for kw in analysis_keywords)
    
    # Determine if user asks for detailed/verbose output
    detail_keywords = ['detail', 'verbose', 'in depth', 'thorough', 'comprehensive',
                       '详细', '详解', '展开', '深入', '全面']
    wants_detail = any(kw in query.lower() for kw in detail_keywords)
    
    # Length constraint - 500 chars unless user explicitly asks for detail
    length_instruction = ""
    if not wants_detail:
        length_instruction = "\nIMPORTANT LENGTH CONSTRAINT: Keep your ENTIRE response (including explanation/analysis) under 500 characters. Be concise and to the point. Do NOT add unnecessary details or verbose explanations."
    
    # Create prompt for command generation or analysis
    prompt = f"""You are a Linux/Unix command line expert assistant. You can see the user's terminal context and recent execution history.
IMPORTANT: You MUST respond in {lang_name}. All explanations, analysis, and text output must be in {lang_name}.{length_instruction}
{context_section}
{history_context}
{regen_instruction}

USER REQUEST: "{query}"

Based on the user's request, determine what they need:

1. If they want to EXECUTE something (create, list, find, delete, move, run, etc.):
   Generate a shell command and respond in this exact format:
   TYPE: COMMAND
   COMMAND: <the actual shell command>
   EXPLANATION: <brief explanation of what the command does>

2. If they want to UNDERSTAND, ANALYZE, or get a SUMMARY of results:
   Provide analysis and respond in this format:
   TYPE: ANALYSIS
   RESPONSE: <your detailed analysis with markdown formatting - use tables, lists, code blocks as needed>

Important:
- For commands: Only generate safe commands (no rm -rf /, no dd, no destructive operations without confirmation)
- For analysis: Use proper Markdown formatting including tables for data, code blocks for technical content, and bullet points for lists
- Consider the terminal context when formulating your response
- If context is stale or missing, generate appropriate commands to gather fresh information
- Be concise - keep explanations brief and focused. Avoid unnecessary details unless the user explicitly asks for them."""

    try:
        messages = [{"role": "user", "content": prompt}]
        full_response = ""
        
        for chunk in OLLAMA.chat_stream(messages, CONFIG.chat_model, temperature=0.3):
            full_response += chunk
        
        # Parse response
        response_type = "COMMAND"
        command = ""
        explanation = ""
        analysis = ""
        
        for line in full_response.split('\n'):
            line_stripped = line.strip()
            if line_stripped.startswith('TYPE:'):
                response_type = line_stripped.replace('TYPE:', '').strip().upper()
            elif line_stripped.startswith('COMMAND:'):
                command = line_stripped.replace('COMMAND:', '').strip()
            elif line_stripped.startswith('EXPLANATION:'):
                explanation = line_stripped.replace('EXPLANATION:', '').strip()
            elif line_stripped.startswith('RESPONSE:'):
                # Capture everything after RESPONSE:
                idx = full_response.find('RESPONSE:')
                if idx >= 0:
                    analysis = full_response[idx + 9:].strip()
                break
        
        # Fallback parsing if format wasn't followed exactly
        if response_type == "COMMAND" and not command:
            # Try to extract command from code block
            code_match = re.search(r'```(?:bash|sh)?\n?(.*?)\n?```', full_response, re.DOTALL)
            if code_match:
                command = code_match.group(1).strip()
            else:
                # Check if this should be analysis instead
                if needs_analysis or len(full_response) > 200:
                    analysis = full_response
                    response_type = "ANALYSIS"
                else:
                    # Just take the first line that looks like a command
                    for line in full_response.split('\n'):
                        line = line.strip()
                        if line and not line.startswith('#') and len(line) < 200:
                            command = line
                            break
        
        if not explanation and command:
            explanation = "Generated command for your request"
        
        print(f"[AI-Command] Response type: {response_type}", file=sys.stderr)
        if command:
            print(f"[AI-Command] Generated command: {command}", file=sys.stderr)
        if analysis:
            print(f"[AI-Command] Analysis length: {len(analysis)} chars", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)
        
        if response_type == "ANALYSIS" or analysis:
            return jsonify({
                "response": analysis or full_response,
                "command": None,
                "explanation": None
            })
        else:
            return jsonify({
                "command": command,
                "explanation": explanation,
                "response": None
            })
        
    except Exception as e:
        print(f"[AI-Command] Error: {e}", file=sys.stderr)
        return jsonify({"error": str(e)})


@app.route('/api/ai-summarize', methods=['POST'])
def ai_summarize():
    """Summarize command execution results using AI."""
    data = request.json
    command = data.get('command', '')
    output = data.get('output', '')
    is_error = data.get('is_error', False)
    user_lang = data.get('language', CONFIG.language)
    
    LANG_NAMES = {"zh": "Chinese (简体中文)", "en": "English", "ja": "Japanese (日本語)", "fr": "French (Français)", 
                  "ru": "Russian (Русский)", "de": "German (Deutsch)", "it": "Italian (Italiano)", 
                  "es": "Spanish (Español)", "pt": "Portuguese (Português)", "ko": "Korean (한국어)"}
    lang_name = LANG_NAMES.get(user_lang, "English")
    
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"[AI-Summarize] Command: {command}", file=sys.stderr)
    print(f"[AI-Summarize] Language: {user_lang} ({lang_name})", file=sys.stderr)
    print(f"[AI-Summarize] Output length: {len(output)} chars", file=sys.stderr)
    print(f"[AI-Summarize] Is error: {is_error}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    
    if not CONFIG.chat_model:
        return jsonify({"error": "No chat model configured"})
    
    # Create prompt for summarization
    prompt = f"""You are a system administrator assistant. Analyze and summarize the following command execution result.
IMPORTANT: You MUST respond in {lang_name}. All text output must be in {lang_name}.

COMMAND EXECUTED: `{command}`
STATUS: {"ERROR" if is_error else "SUCCESS"}

OUTPUT:
```
{output[:3000]}
```

Please provide a clear, well-formatted summary using Markdown. Keep the total response under 500 characters:

1. **Overview**: What the command did and whether it succeeded
2. **Key Findings**: Important information from the output
3. **Recommendations**: Suggested next steps (if any)

Format guidelines:
- Use tables for structured data (disk space, file sizes, process lists, etc.)
- Use code blocks for paths, commands, or technical details
- Be concise - focus on key results, not verbose explanations
- If there are errors, briefly explain what went wrong and how to fix it"""

    try:
        messages = [{"role": "user", "content": prompt}]
        full_response = ""
        
        for chunk in OLLAMA.chat_stream(messages, CONFIG.chat_model, temperature=0.5):
            full_response += chunk
        
        print(f"[AI-Summarize] Summary length: {len(full_response)} chars", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)
        
        return jsonify({"summary": full_response})
        
    except Exception as e:
        print(f"[AI-Summarize] Error: {e}", file=sys.stderr)
        return jsonify({"error": str(e)})


@app.route('/api/github-search', methods=['POST'])
def github_search():
    """Search GitHub for documentation repositories."""
    data = request.json
    query = data.get('query', '')
    language = data.get('language', '')
    
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"[GitHub] Searching: {query} (lang: {language or 'any'})", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    
    if not query:
        return jsonify({"error": "No query provided", "results": []})
    
    # Build search query
    search_query = f"{query} documentation tutorial"
    if language:
        search_query += f" language:{language}"
    
    proxies = get_proxies()
    
    try:
        # Use GitHub API (no auth needed for basic search)
        url = "https://api.github.com/search/repositories"
        params = {
            "q": search_query,
            "sort": "stars",
            "order": "desc",
            "per_page": 10
        }
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GangDan-Dev-Assistant"
        }
        
        r = requests.get(url, params=params, headers=headers, proxies=proxies, timeout=30)
        r.raise_for_status()
        
        data = r.json()
        results = []
        
        for item in data.get("items", [])[:10]:
            results.append({
                "name": item["name"],
                "full_name": item["full_name"],
                "description": item.get("description", "")[:100],
                "stars": item["stargazers_count"],
                "url": item["html_url"]
            })
        
        print(f"[GitHub] Found {len(results)} results", file=sys.stderr)
        for r in results[:3]:
            print(f"[GitHub]   - {r['name']} ({r['stars']} stars)", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)
        
        return jsonify({"results": results})
        
    except Exception as e:
        print(f"[GitHub] Error: {e}", file=sys.stderr)
        return jsonify({"error": str(e), "results": []})


@app.route('/api/github-download', methods=['POST'])
def github_download():
    """Download README and documentation files from a GitHub repo."""
    data = request.json
    repo = data.get('repo', '')  # format: owner/repo
    name = data.get('name', repo.split('/')[-1] if repo else 'github_doc')
    
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"[GitHub-DL] Downloading from: {repo}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    
    if not repo:
        return jsonify({"success": False, "error": "No repo specified"})
    
    proxies = get_proxies()
    
    # Create directory
    doc_dir = DOCS_DIR / name.replace('/', '_')
    doc_dir.mkdir(parents=True, exist_ok=True)
    
    files_downloaded = 0
    
    # Files to try downloading
    doc_files = [
        "README.md",
        "readme.md",
        "README.rst",
        "CONTRIBUTING.md",
        "docs/README.md",
        "docs/index.md",
        "doc/README.md",
        "documentation/README.md",
        "TUTORIAL.md",
        "GUIDE.md",
    ]
    
    try:
        for doc_file in doc_files:
            url = f"https://raw.githubusercontent.com/{repo}/main/{doc_file}"
            try:
                r = requests.get(url, proxies=proxies, timeout=15)
                if r.status_code == 200:
                    filename = doc_file.replace('/', '_')
                    filepath = doc_dir / filename
                    filepath.write_text(r.text, encoding='utf-8')
                    files_downloaded += 1
                    print(f"[GitHub-DL]   OK: {doc_file}", file=sys.stderr)
            except:
                pass
            
            # Also try master branch
            url = f"https://raw.githubusercontent.com/{repo}/master/{doc_file}"
            try:
                r = requests.get(url, proxies=proxies, timeout=15)
                if r.status_code == 200:
                    filename = doc_file.replace('/', '_') 
                    if not (doc_dir / filename).exists():
                        filepath = doc_dir / filename
                        filepath.write_text(r.text, encoding='utf-8')
                        files_downloaded += 1
                        print(f"[GitHub-DL]   OK: {doc_file} (master)", file=sys.stderr)
            except:
                pass
        
        print(f"[GitHub-DL] Downloaded {files_downloaded} files", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)
        
        return jsonify({
            "success": True,
            "files": files_downloaded,
            "name": name
        })
        
    except Exception as e:
        print(f"[GitHub-DL] Error: {e}", file=sys.stderr)
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/export-raw-files')
def export_raw_files():
    """Export all raw document files as a zip archive."""
    if not DOCS_DIR.exists() or not any(DOCS_DIR.iterdir()):
        return jsonify({"success": False, "error": t("no_files_to_export")}), 404

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"[ExportRawFiles] Exporting from: {DOCS_DIR}", file=sys.stderr)

    buffer = io.BytesIO()
    file_count = 0
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(str(DOCS_DIR)):
            for fname in files:
                filepath = Path(root) / fname
                arcname = str(filepath.relative_to(DOCS_DIR))
                zf.write(str(filepath), arcname)
                file_count += 1

    if file_count == 0:
        return jsonify({"success": False, "error": t("no_files_to_export")}), 404

    buffer.seek(0)
    filename = f"gangdan_raw_files_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    print(f"[ExportRawFiles] Exported {file_count} files", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    return Response(
        buffer.getvalue(),
        mimetype='application/zip',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


@app.route('/api/import-raw-files', methods=['POST'])
def import_raw_files():
    """Import raw document files from a zip archive."""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file provided"}), 400

    file = request.files['file']
    if not file.filename or not file.filename.endswith('.zip'):
        return jsonify({"success": False, "error": "File must be a .zip archive"}), 400

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"[ImportRawFiles] Importing from: {file.filename}", file=sys.stderr)

    try:
        with zipfile.ZipFile(io.BytesIO(file.read()), 'r') as zf:
            # Security: prevent path traversal
            for name in zf.namelist():
                if '..' in name or name.startswith('/') or name.startswith('\\'):
                    return jsonify({"success": False, "error": f"Invalid path in archive: {name}"}), 400

            DOCS_DIR.mkdir(parents=True, exist_ok=True)
            zf.extractall(str(DOCS_DIR))

            # Update user_kbs manifest for any user_ directories found
            seen_user_dirs = set()
            for name in zf.namelist():
                parts = Path(name).parts
                if parts and parts[0].startswith('user_'):
                    seen_user_dirs.add(parts[0])

            existing_kbs = load_user_kbs()
            for internal_name in seen_user_dirs:
                if internal_name not in existing_kbs:
                    dir_path = DOCS_DIR / internal_name
                    file_count = len(list(dir_path.glob("*.md")) + list(dir_path.glob("*.txt")))
                    save_user_kb(internal_name, internal_name, file_count)

            total = len([n for n in zf.namelist() if not n.endswith('/')])
            print(f"[ImportRawFiles] Imported {total} files", file=sys.stderr)
            print(f"{'='*60}\n", file=sys.stderr)

            return jsonify({"success": True, "message": f"Imported {total} files"})
    except zipfile.BadZipFile:
        return jsonify({"success": False, "error": "Invalid zip file"}), 400
    except Exception as e:
        print(f"[ImportRawFiles] Error: {e}", file=sys.stderr)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/export-kb')
def export_kb():
    """Export knowledge base (ChromaDB collections) as a zip archive."""
    if not CHROMA or not CHROMA.is_available:
        return jsonify({"success": False, "error": "Vector DB not available"}), 500

    collections = CHROMA.list_collections()
    if not collections:
        return jsonify({"success": False, "error": t("no_kb_to_export")}), 404

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"[ExportKB] Exporting {len(collections)} collections", file=sys.stderr)

    buffer = io.BytesIO()
    exported = 0
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for coll_name in collections:
            try:
                data = CHROMA.get_documents(coll_name, limit=0, include=["documents", "metadatas", "embeddings"])

                raw_embeddings = data.get("embeddings") or []
                embeddings_list = []
                for emb in raw_embeddings:
                    if hasattr(emb, 'tolist'):
                        embeddings_list.append(emb.tolist())
                    elif isinstance(emb, list):
                        embeddings_list.append(emb)
                    else:
                        embeddings_list.append(list(emb))

                coll_data = {
                    "name": coll_name,
                    "ids": data.get("ids", []),
                    "documents": data.get("documents", []),
                    "metadatas": data.get("metadatas", []),
                    "embeddings": embeddings_list,
                }

                zf.writestr(
                    f"collections/{coll_name}.json",
                    json.dumps(coll_data, ensure_ascii=False)
                )
                exported += 1
                print(f"[ExportKB]   {coll_name}: {len(coll_data['ids'])} documents", file=sys.stderr)
            except Exception as e:
                print(f"[ExportKB]   Error exporting '{coll_name}': {e}", file=sys.stderr)

        # Include user_kbs.json manifest
        if USER_KBS_FILE.exists():
            zf.write(str(USER_KBS_FILE), "user_kbs.json")

    buffer.seek(0)
    filename = f"gangdan_kb_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    print(f"[ExportKB] Exported {exported} collections", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    return Response(
        buffer.getvalue(),
        mimetype='application/zip',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


@app.route('/api/import-kb', methods=['POST'])
def import_kb():
    """Import knowledge base from a zip archive."""
    if not CHROMA or not CHROMA.is_available:
        return jsonify({"success": False, "error": "Vector DB not available"}), 500

    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file provided"}), 400

    file = request.files['file']
    if not file.filename or not file.filename.endswith('.zip'):
        return jsonify({"success": False, "error": "File must be a .zip archive"}), 400

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"[ImportKB] Importing from: {file.filename}", file=sys.stderr)

    try:
        imported = 0
        with zipfile.ZipFile(io.BytesIO(file.read()), 'r') as zf:
            for name in zf.namelist():
                if name.startswith('collections/') and name.endswith('.json'):
                    coll_data = json.loads(zf.read(name).decode('utf-8'))
                    coll_name = coll_data.get('name', '')

                    if not coll_name:
                        continue

                    ids = coll_data.get('ids', [])
                    documents = coll_data.get('documents', [])
                    metadatas = coll_data.get('metadatas', [])
                    embeddings = coll_data.get('embeddings', [])

                    if not (ids and documents and embeddings):
                        print(f"[ImportKB]   Skipped '{coll_name}': missing data", file=sys.stderr)
                        continue

                    # Delete existing collection if present
                    try:
                        CHROMA.delete_collection(coll_name)
                    except Exception:
                        pass

                    # Recreate collection and add data in batches
                    batch_size = 5000
                    for start in range(0, len(ids), batch_size):
                        end = start + batch_size
                        CHROMA.add_documents(
                            coll_name,
                            documents[start:end],
                            embeddings[start:end],
                            metadatas[start:end],
                            ids[start:end],
                        )

                    imported += 1
                    print(f"[ImportKB]   {coll_name}: {len(ids)} documents restored", file=sys.stderr)

                elif name == 'user_kbs.json':
                    imported_kbs = json.loads(zf.read(name).decode('utf-8'))
                    existing_kbs = load_user_kbs()
                    existing_kbs.update(imported_kbs)
                    DATA_DIR.mkdir(parents=True, exist_ok=True)
                    USER_KBS_FILE.write_text(
                        json.dumps(existing_kbs, indent=2, ensure_ascii=False),
                        encoding="utf-8"
                    )
                    print(f"[ImportKB]   Restored user_kbs.json ({len(imported_kbs)} entries)", file=sys.stderr)

        print(f"[ImportKB] Imported {imported} collections", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)

        return jsonify({"success": True, "message": f"Imported {imported} collections"})
    except zipfile.BadZipFile:
        return jsonify({"success": False, "error": "Invalid zip file"}), 400
    except Exception as e:
        print(f"[ImportKB] Error: {e}", file=sys.stderr)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/terminal', methods=['POST'])
def terminal_command():
    """Execute terminal/shell commands."""
    data = request.json
    command = data.get('command', '')
    
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"[Terminal] Command: {command}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    
    if not command:
        return jsonify({"error": "No command provided"})
    
    # Security: block dangerous commands
    dangerous_patterns = [
        r'\brm\s+-rf\s+/', r'\bmkfs\b', r'\bdd\s+if=', r':(){', r'>\s*/dev/sd',
        r'\bshutdown\b', r'\breboot\b', r'\bhalt\b', r'\binit\s+0'
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, command, re.IGNORECASE):
            print(f"[Terminal] Blocked dangerous command pattern: {pattern}", file=sys.stderr)
            return jsonify({"error": "Command blocked for safety reasons", "stdout": "", "stderr": ""})
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(DATA_DIR)
        )
        
        print(f"[Terminal] Exit code: {result.returncode}", file=sys.stderr)
        if result.stdout:
            print(f"[Terminal] stdout: {len(result.stdout)} chars", file=sys.stderr)
        if result.stderr:
            print(f"[Terminal] stderr: {len(result.stderr)} chars", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)
        
        return jsonify({
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "error": None
        })
        
    except subprocess.TimeoutExpired:
        print(f"[Terminal] Timeout after 60s", file=sys.stderr)
        return jsonify({"error": "Command timed out (60s limit)", "stdout": "", "stderr": ""})
    except Exception as e:
        print(f"[Terminal] Error: {type(e).__name__}: {e}", file=sys.stderr)
        return jsonify({"error": str(e), "stdout": "", "stderr": ""})


# =============================================================================
# Main
# =============================================================================

if __name__ == '__main__':
    try:
        print("""
╔═══════════════════════════════════════════════════════════╗
║  🚀 纲担 / GangDan - Offline Dev Assistant                ║
║                                                           ║
║  Open in browser: http://127.0.0.1:5000                   ║
╚═══════════════════════════════════════════════════════════╝
        """)
    except UnicodeEncodeError:
        print("\n  GangDan - Offline Dev Assistant")
        print("  Open in browser: http://127.0.0.1:5000\n")
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
