"""First-run setup wizard for GangDan Refined.

Provides interactive configuration for both CLI and Web interfaces.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import CONFIG, CONFIG_FILE, DATA_DIR, load_config, save_config
from .constants import OLLAMA_DEFAULT_URL
from .i18n import t
from ..llm.factory import create_client
from ..llm.models import PROVIDER_CONFIGS


def is_first_run() -> bool:
    """Check if this is the first run (no config file exists)."""
    return not CONFIG_FILE.exists()


def check_ollama_connection(base_url: str = OLLAMA_DEFAULT_URL, timeout: int = 5) -> Tuple[bool, str]:
    """Test connection to Ollama service.

    Parameters
    ----------
    base_url : str
        Ollama service URL.
    timeout : int
        Connection timeout in seconds.

    Returns
    -------
    Tuple[bool, str]
        (success, message)
    """
    try:
        import urllib.request
        import urllib.error

        url = f"{base_url}/api/tags"
        req = urllib.request.Request(url, method="GET")
        response = urllib.request.urlopen(req, timeout=timeout)
        data = json.loads(response.read().decode("utf-8"))
        models = data.get("models", [])
        model_count = len(models)

        if model_count > 0:
            model_names = [m.get("name", "unknown") for m in models[:5]]
            msg = f"Connected! Found {model_count} models: {', '.join(model_names)}"
            translated = t("wizard.ollama_connected_models")
            return True, translated if translated != "wizard.ollama_connected_models" else msg
        else:
            msg = "Connected! No models found. Run 'ollama pull qwen2.5:7b' first."
            translated = t("wizard.ollama_connected_no_models")
            return True, translated if translated != "wizard.ollama_connected_no_models" else msg
    except Exception as e:
        msg = f"Connection failed: {str(e)}"
        translated = t("wizard.ollama_connection_failed")
        return False, translated if translated != "wizard.ollama_connection_failed" else msg


def check_provider_connection(provider: str, api_key: str, base_url: str = "") -> Tuple[bool, str]:
    """Test connection to an LLM provider.

    Parameters
    ----------
    provider : str
        Provider name.
    api_key : str
        API key.
    base_url : str
        Custom base URL.

    Returns
    -------
    Tuple[bool, str]
        (success, message)
    """
    try:
        client = create_client(provider, api_key, base_url)
        response = client.chat(
            messages=[{"role": "user", "content": "Hi"}],
            model="test",
            temperature=0.0,
            max_tokens=10,
        )
        if response.get("success"):
            translated = t("wizard.provider_test_success")
            return True, translated if translated != "wizard.provider_test_success" else "Connection successful!"
        else:
            return False, response.get("error", "Unknown error")
    except Exception as e:
        return False, str(e)


def get_ollama_models(base_url: str = OLLAMA_DEFAULT_URL) -> List[str]:
    """Get list of available Ollama models.

    Parameters
    ----------
    base_url : str
        Ollama service URL.

    Returns
    -------
    List[str]
        List of model names.
    """
    try:
        import urllib.request
        import urllib.error

        url = f"{base_url}/api/tags"
        req = urllib.request.Request(url, method="GET")
        response = urllib.request.urlopen(req, timeout=5)
        data = json.loads(response.read().decode("utf-8"))
        return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        return []


def get_provider_models(provider: str, api_key: str, base_url: str = "") -> List[str]:
    """Get list of available models from a provider.

    Parameters
    ----------
    provider : str
        Provider name.
    api_key : str
        API key.
    base_url : str
        Custom base URL.

    Returns
    -------
    List[str]
        List of model names.
    """
    config = PROVIDER_CONFIGS.get(provider)
    if config and config.models:
        return config.models

    try:
        client = create_client(provider, api_key, base_url)
        if hasattr(client, "list_models"):
            return client.list_models()
    except Exception:
        pass

    return config.default_chat_models if config else []


def run_cli_wizard() -> bool:
    """Run interactive CLI setup wizard.

    Returns
    -------
    bool
        True if setup completed successfully, False if cancelled.
    """
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.prompt import Prompt, Confirm
        from rich.table import Table

        console = Console()

        console.print(Panel(
            t("wizard.welcome_title") or "🎉 Welcome to GangDan Refined!",
            subtitle=t("wizard.welcome_subtitle") or "Let's configure your AI assistant",
            style="bold blue",
        ))

        # Step 1: Language selection
        console.print(f"\n[bold]{t('wizard.select_language') or 'Select your language:'}[/bold]")
        console.print("  1. 中文 (Chinese)")
        console.print("  2. English")
        lang_choice = Prompt.ask(
            t("wizard.language_choice") or "Choose [1-2]",
            choices=["1", "2"],
            default="1",
        )
        CONFIG.ui.language = "zh" if lang_choice == "1" else "en"

        # Step 2: Choose LLM provider
        console.print(f"\n[bold]{t('wizard.select_provider') or 'Choose your LLM provider:'}[/bold]")
        providers = list(PROVIDER_CONFIGS.values())
        for i, provider in enumerate(providers, 1):
            key_status = t("wizard.needs_key") or "Needs API Key" if provider.requires_key else t("wizard.free") or "Free"
            console.print(f"  {i}. {provider.display_name} ({key_status})")

        provider_choice = int(Prompt.ask(
            t("wizard.provider_choice") or "Choose provider [1-9]",
            choices=[str(i) for i in range(1, len(providers) + 1)],
            default="1",
        ))
        selected_provider = providers[provider_choice - 1]

        # Step 3: Configure provider
        if selected_provider.name == "ollama":
            console.print(f"\n[bold]{t('wizard.configuring_ollama') or 'Configuring Ollama...'}[/bold]")
            ollama_url = Prompt.ask(
                t("wizard.ollama_url_prompt") or "Ollama URL",
                default=OLLAMA_DEFAULT_URL,
            )
            CONFIG.llm.ollama_url = ollama_url

            # Test connection
            console.print(t("wizard.testing_connection") or "Testing connection...")
            success, message = check_ollama_connection(ollama_url)
            if success:
                console.print(f"[green]✓ {message}[/green]")
            else:
                console.print(f"[red]✗ {message}[/red]")
                if not Confirm.ask(t("wizard.continue_anyway") or "Continue anyway?", default=False):
                    return False

            # Get available models
            models = get_ollama_models(ollama_url)
            if models:
                console.print(f"\n[bold]{t('wizard.available_models') or 'Available models:'}[/bold]")
                for i, model in enumerate(models, 1):
                    console.print(f"  {i}. {model}")
                model_choice = int(Prompt.ask(
                    t("wizard.select_model") or "Select model",
                    choices=[str(i) for i in range(1, len(models) + 1)],
                    default="1",
                ))
                CONFIG.llm.chat_model = models[model_choice - 1]
            else:
                console.print(f"[yellow]{t('wizard.no_models_found') or 'No models found. Using default.'}[/yellow]")
                CONFIG.llm.chat_model = "qwen2.5:7b"

            CONFIG.llm.chat_provider = "ollama"
            CONFIG.llm.embedding_model = "nomic-embed-text"

        else:
            console.print(f"\n[bold]{t('wizard.configuring_provider') or 'Configuring {provider}...'}[/bold]")
            api_key = Prompt.ask(
                t("wizard.api_key_prompt") or "API Key",
                password=True,
            )
            CONFIG.llm.chat_provider = selected_provider.name
            CONFIG.llm.chat_api_key = api_key
            CONFIG.llm.provider_keys[selected_provider.name] = api_key

            base_url = Prompt.ask(
                t("wizard.base_url_prompt") or "Base URL",
                default=selected_provider.base_url,
            )
            CONFIG.llm.chat_api_base_url = base_url
            CONFIG.llm.provider_base_urls[selected_provider.name] = base_url

            # Test connection
            console.print(t("wizard.testing_connection") or "Testing connection...")
            success, message = check_provider_connection(
                selected_provider.name, api_key, base_url
            )
            if success:
                console.print(f"[green]✓ {message}[/green]")
            else:
                console.print(f"[red]✗ {message}[/red]")
                if not Confirm.ask(t("wizard.continue_anyway") or "Continue anyway?", default=False):
                    return False

            # Get models
            models = get_provider_models(selected_provider.name, api_key, base_url)
            if models:
                console.print(f"\n[bold]{t('wizard.available_models') or 'Available models:'}[/bold]")
                for i, model in enumerate(models[:10], 1):
                    console.print(f"  {i}. {model}")
                model_choice = int(Prompt.ask(
                    t("wizard.select_model") or "Select model",
                    choices=[str(i) for i in range(1, min(len(models), 10) + 1)],
                    default="1",
                ))
                CONFIG.llm.chat_model = models[model_choice - 1]
            else:
                CONFIG.llm.chat_model = selected_provider.default_model or "gpt-4o"

            # Embedding model (always Ollama)
            console.print(f"\n[bold]{t('wizard.embedding_setup') or 'Embedding Model Setup'}[/bold]")
            console.print(t("wizard.embedding_note") or "Embeddings require Ollama. Configure Ollama for embeddings?")
            if Confirm.ask(t("wizard.configure_ollama_for_embed") or "Configure Ollama for embeddings?", default=True):
                ollama_url = Prompt.ask(
                    t("wizard.ollama_url_prompt") or "Ollama URL",
                    default=OLLAMA_DEFAULT_URL,
                )
                CONFIG.llm.ollama_url = ollama_url
                CONFIG.llm.embedding_model = "nomic-embed-text"

        # Step 4: Save configuration
        console.print(f"\n[bold]{t('wizard.saving_config') or 'Saving configuration...'}[/bold]")
        save_config()

        console.print(Panel(
            t("wizard.setup_complete") or "✓ Setup complete! You're ready to use GangDan Refined.",
            style="bold green",
        ))

        return True

    except KeyboardInterrupt:
        console.print(f"\n[yellow]{t('wizard.setup_cancelled') or 'Setup cancelled.'}[/yellow]")
        return False
    except ImportError:
        # Fallback for environments without Rich
        return run_simple_cli_wizard()


def run_simple_cli_wizard() -> bool:
    """Simple CLI wizard without Rich dependency.

    Returns
    -------
    bool
        True if setup completed successfully.
    """
    print("\n" + "=" * 60)
    print("Welcome to GangDan Refined Setup!")
    print("=" * 60)

    # Language
    print("\nSelect language:")
    print("  1. 中文")
    print("  2. English")
    lang = input("Choose [1-2, default=1]: ").strip() or "1"
    CONFIG.ui.language = "zh" if lang == "1" else "en"

    # Provider
    print("\nChoose LLM provider:")
    providers = list(PROVIDER_CONFIGS.values())
    for i, p in enumerate(providers, 1):
        key = "Needs API Key" if p.requires_key else "Free"
        print(f"  {i}. {p.display_name} ({key})")

    choice = input("Choose [1-9, default=1]: ").strip() or "1"
    selected = providers[int(choice) - 1]

    if selected.name == "ollama":
        url = input(f"Ollama URL [{OLLAMA_DEFAULT_URL}]: ").strip() or OLLAMA_DEFAULT_URL
        CONFIG.llm.ollama_url = url
        CONFIG.llm.chat_provider = "ollama"
        CONFIG.llm.chat_model = "qwen2.5:7b"
        CONFIG.llm.embedding_model = "nomic-embed-text"

        print("Testing connection...")
        success, msg = check_ollama_connection(url)
        print(f"  {'✓' if success else '✗'} {msg}")
    else:
        api_key = input("API Key: ").strip()
        CONFIG.llm.chat_provider = selected.name
        CONFIG.llm.chat_api_key = api_key
        CONFIG.llm.provider_keys[selected.name] = api_key
        CONFIG.llm.chat_model = selected.default_model or "gpt-4o"

        print("Testing connection...")
        success, msg = check_provider_connection(selected.name, api_key)
        print(f"  {'✓' if success else '✗'} {msg}")

    # Save
    print("\nSaving configuration...")
    save_config()
    print("✓ Setup complete!")

    return True


def get_setup_status() -> Dict[str, Any]:
    """Get current setup status for Web UI.

    Returns
    -------
    Dict[str, Any]
        Setup status including configuration state.
    """
    load_config()

    status = {
        "is_configured": CONFIG_FILE.exists(),
        "language": CONFIG.ui.language,
        "chat_provider": CONFIG.llm.chat_provider,
        "chat_model": CONFIG.llm.chat_model,
        "ollama_url": CONFIG.llm.ollama_url,
        "has_api_key": bool(CONFIG.llm.chat_api_key or CONFIG.llm.provider_keys.get(CONFIG.llm.chat_provider)),
    }

    if CONFIG.llm.chat_provider == "ollama":
        success, message = check_ollama_connection(CONFIG.llm.ollama_url)
        status["ollama_connected"] = success
        status["ollama_message"] = message
        status["ollama_models"] = get_ollama_models(CONFIG.llm.ollama_url)
    else:
        status["ollama_connected"] = False
        status["ollama_message"] = ""
        status["ollama_models"] = []

    return status


def save_setup_config(config_data: Dict[str, Any]) -> Tuple[bool, str]:
    """Save configuration from Web setup wizard.

    Parameters
    ----------
    config_data : Dict[str, Any]
        Configuration data from Web form.

    Returns
    -------
    Tuple[bool, str]
        (success, message)
    """
    try:
        # Language
        if "language" in config_data:
            CONFIG.ui.language = config_data["language"]

        # Provider
        provider = config_data.get("chat_provider", "ollama")
        CONFIG.llm.chat_provider = provider

        if provider == "ollama":
            ollama_url = config_data.get("ollama_url", OLLAMA_DEFAULT_URL)
            CONFIG.llm.ollama_url = ollama_url
            CONFIG.llm.chat_model = config_data.get("chat_model", "qwen2.5:7b")
            CONFIG.llm.embedding_model = config_data.get("embedding_model", "nomic-embed-text")

            # Test connection
            success, message = check_ollama_connection(ollama_url)
            if not success:
                return False, message

        else:
            api_key = config_data.get("api_key", "")
            base_url = config_data.get("base_url", "")
            chat_model = config_data.get("chat_model", "")

            if not api_key:
                return False, "API Key is required"

            CONFIG.llm.chat_api_key = api_key
            CONFIG.llm.provider_keys[provider] = api_key
            CONFIG.llm.chat_api_base_url = base_url
            CONFIG.llm.provider_base_urls[provider] = base_url
            CONFIG.llm.chat_model = chat_model

            # Test connection
            success, message = check_provider_connection(provider, api_key, base_url)
            if not success:
                return False, message

        # Save
        save_config()
        return True, "Configuration saved successfully"

    except Exception as e:
        return False, f"Error saving configuration: {str(e)}"
