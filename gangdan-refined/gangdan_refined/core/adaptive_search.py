"""AI auto-control for adaptive search and parameter tuning."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from gangdan_refined.core.config import CONFIG, detect_language
from gangdan_refined.core.llm_client import BaseLLMClient


class AdaptiveSearchController:
    """AI-driven auto-control for search parameters and error recovery.

    Automatically adjusts chunk size, top-k, model selection,
    language detection, and error recovery.
    """

    def __init__(self, client: Optional[BaseLLMClient] = None):
        self.client = client
        self._error_count = 0
        self._max_retries = 3

    def auto_chunk_size(self, text_length: int) -> int:
        """Dynamically adjust chunk size based on text length.

        Parameters
        ----------
        text_length : int
            Length of the text to be chunked.

        Returns
        -------
        int
            Optimal chunk size.
        """
        if not CONFIG.auto_chunk_size:
            return CONFIG.chunk_size
        if text_length < 2000:
            return 500
        elif text_length < 10000:
            return 1000
        elif text_length < 50000:
            return 1500
        return 2000

    def auto_top_k(self, query_length: int, collection_size: int) -> int:
        """Dynamically adjust top-k based on query and collection size.

        Parameters
        ----------
        query_length : int
            Length of the search query.
        collection_size : int
            Number of documents in the collection.

        Returns
        -------
        int
            Optimal top-k value.
        """
        if not CONFIG.auto_top_k:
            return CONFIG.top_k
        base_k = CONFIG.top_k
        if query_length < 10:
            base_k = max(base_k, 7)
        if collection_size > 1000:
            base_k = min(base_k + 2, 15)
        elif collection_size < 50:
            base_k = min(base_k, 5)
        return base_k

    def auto_select_model(self, task: str, available_models: List[str]) -> str:
        """Select the best model for a given task.

        Parameters
        ----------
        task : str
            Task type: 'chat', 'embedding', 'translation', 'research'.
        available_models : List[str]
            List of available model names.

        Returns
        -------
        str
            Selected model name.
        """
        if not CONFIG.auto_model_selection or not available_models:
            if task == "embedding":
                return CONFIG.embedding_model or available_models[0]
            return CONFIG.chat_model or available_models[0]

        task_patterns = {
            "embedding": ["embed", "bge", "nomic", "minilm"],
            "chat": [],
            "translation": [],
            "research": [],
        }
        patterns = task_patterns.get(task, [])
        if patterns:
            for model in available_models:
                if any(p in model.lower() for p in patterns):
                    return model
        return available_models[0]

    def detect_query_language(self, query: str) -> str:
        """Detect the language of a query.

        Parameters
        ----------
        query : str
            User query text.

        Returns
        -------
        str
            Detected language code.
        """
        if not CONFIG.auto_language_detect:
            return CONFIG.language
        return detect_language(query)

    def should_translate_query(self, query: str, kb_languages: List[str]) -> Tuple[bool, str]:
        """Determine if query should be translated for KB search.

        Parameters
        ----------
        query : str
            User query.
        kb_languages : List[str]
            Languages present in the knowledge base.

        Returns
        -------
        Tuple[bool, str]
            (should_translate, target_language).
        """
        if not kb_languages:
            return False, ""
        query_lang = self.detect_query_language(query)
        if query_lang in kb_languages:
            return False, ""
        primary_kb_lang = kb_languages[0] if kb_languages else "en"
        return True, primary_kb_lang

    def handle_error(self, error: Exception, context: str = "") -> Dict:
        """Handle errors with automatic recovery strategies.

        Parameters
        ----------
        error : Exception
            The caught exception.
        context : str
            Context where the error occurred.

        Returns
        -------
        Dict
            Recovery action recommendation.
        """
        self._error_count += 1
        error_msg = str(error).lower()
        action = {"retry": False, "fallback": False, "message": str(error)}

        if not CONFIG.auto_error_recovery:
            return action

        if "dimension" in error_msg:
            action["message"] = "Dimension mismatch detected. Please re-index the collection."
            action["fallback"] = True
        elif "timeout" in error_msg or "connection" in error_msg:
            action["retry"] = self._error_count <= self._max_retries
            action["message"] = f"Connection error. Retrying ({self._error_count}/{self._max_retries})..."
        elif "rate" in error_msg or "429" in error_msg:
            action["retry"] = True
            action["message"] = "Rate limited. Waiting before retry..."
        elif self._error_count <= self._max_retries:
            action["retry"] = True
            action["message"] = f"Error occurred. Retrying ({self._error_count}/{self._max_retries})..."

        if self._error_count > self._max_retries:
            action["message"] = "Max retries exceeded. Please check configuration."
            action["retry"] = False

        return action

    def reset_error_count(self):
        """Reset the error counter after successful operation."""
        self._error_count = 0

    def get_status(self) -> Dict:
        """Get current auto-control status."""
        return {
            "auto_chunk_size": CONFIG.auto_chunk_size,
            "auto_top_k": CONFIG.auto_top_k,
            "auto_model_selection": CONFIG.auto_model_selection,
            "auto_language_detect": CONFIG.auto_language_detect,
            "auto_error_recovery": CONFIG.auto_error_recovery,
            "error_count": self._error_count,
            "max_retries": self._max_retries,
        }


adaptive_controller = AdaptiveSearchController()
