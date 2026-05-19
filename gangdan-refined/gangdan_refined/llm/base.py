"""Base LLM client interface for GangDan Refined.

Defines the abstract interface that all LLM providers must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator, List, Optional


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients.

    All LLM providers must implement:
    - chat(): Non-streaming chat completion
    - chat_stream(): Streaming chat completion
    - embed(): Text embedding
    - get_models(): List available models
    """

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """Send a chat completion request.

        Parameters
        ----------
        messages : List[Dict[str, str]]
            Conversation messages with 'role' and 'content' keys.
        model : str, optional
            Model name to use.
        temperature : float
            Sampling temperature.
        max_tokens : int
            Maximum tokens in response.

        Returns
        -------
        str
            The assistant's response text.
        """
        ...

    @abstractmethod
    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> Iterator[str]:
        """Send a streaming chat completion request.

        Yields response tokens as they arrive.
        """
        ...

    @abstractmethod
    def embed(
        self,
        text: str | List[str],
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """Generate embeddings for text.

        Parameters
        ----------
        text : str or List[str]
            Text or list of texts to embed.
        model : str, optional
            Embedding model name.

        Returns
        -------
        Any
            Embedding vector(s).
        """
        ...

    @abstractmethod
    def get_models(self) -> List[str]:
        """List available models.

        Returns
        -------
        List[str]
            Available model names.
        """
        ...

    def translate(
        self,
        text: str,
        target_language: str = "en",
        source_language: str = "auto",
        model: Optional[str] = None,
    ) -> str:
        """Translate text between languages.

        Default implementation uses chat completion with translation prompt.
        Subclasses can override for specialized translation endpoints.
        """
        from ..core.config import detect_language
        if source_language == "auto":
            source_language = detect_language(text)

        lang_map = {
            "zh": "Chinese", "en": "English", "ja": "Japanese",
            "ko": "Korean", "fr": "French", "de": "German",
            "es": "Spanish", "pt": "Portuguese", "ru": "Russian",
            "it": "Italian", "ar": "Arabic",
        }
        src_lang = lang_map.get(source_language, source_language)
        tgt_lang = lang_map.get(target_language, target_language)

        messages = [
            {"role": "system", "content": f"You are a professional translator. Translate the following text from {src_lang} to {tgt_lang}. Only output the translation, nothing else."},
            {"role": "user", "content": text},
        ]
        return self.chat(messages, model=model, temperature=0.3)