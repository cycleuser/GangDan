"""
Unified error handling for GangDan.

This module provides a consistent error handling framework with:
- Custom exception hierarchy
- Standardized error codes
- Error context tracking
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolResult:
    """
    Standardized result container for GangDan operations.

    Attributes:
        success: Whether the operation succeeded
        data: The result data (if successful)
        error: Error message (if failed)
        metadata: Additional context information
    """

    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        """Return True if operation was successful."""
        return self.success

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        result = {
            "success": self.success,
            "data": self.data if self.success else None,
            "error": self.error if not self.success else None,
        }
        if self.metadata:
            result["metadata"] = self.metadata
        return result


class GangDanError(Exception):
    """Base exception for all GangDan errors."""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.code = code or "UNKNOWN_ERROR"
        self.context = context or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API responses."""
        return {
            "error": self.code,
            "message": self.message,
            "context": self.context if self.context else None,
        }


class ConfigurationError(GangDanError):
    """Configuration-related errors."""

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="CONFIGURATION_ERROR", context=context)


class ValidationError(GangDanError):
    """Input validation errors."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        ctx = context or {}
        if field:
            ctx["field"] = field
        super().__init__(message, code="VALIDATION_ERROR", context=ctx)


class APIError(GangDanError):
    """External API errors (Ollama, OpenAI, etc.)."""

    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        status_code: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        ctx = context or {}
        if provider:
            ctx["provider"] = provider
        if status_code:
            ctx["status_code"] = status_code
        super().__init__(message, code="API_ERROR", context=ctx)


class DatabaseError(GangDanError):
    """Vector database errors."""

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="DATABASE_ERROR", context=context)


class FileError(GangDanError):
    """File I/O errors."""

    def __init__(
        self,
        message: str,
        path: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        ctx = context or {}
        if path:
            ctx["path"] = path
        super().__init__(message, code="FILE_ERROR", context=ctx)


class TimeoutError(GangDanError):
    """Operation timeout errors."""

    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        ctx = context or {}
        if operation:
            ctx["operation"] = operation
        super().__init__(message, code="TIMEOUT_ERROR", context=ctx)


class ModelError(GangDanError):
    """LLM model errors (not found, not loaded, etc.)."""

    def __init__(
        self,
        message: str,
        model_name: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        ctx = context or {}
        if model_name:
            ctx["model_name"] = model_name
        super().__init__(message, code="MODEL_ERROR", context=ctx)


@dataclass
class ErrorContext:
    """
    Contextual information for error reporting and debugging.

    Attributes:
        operation: The operation being performed
        component: The component/module where error occurred
        user_id: User identifier (if applicable)
        request_id: Request identifier for tracing
        timestamp: When the error occurred
        extra: Additional key-value pairs
    """

    operation: Optional[str] = None
    component: Optional[str] = None
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    timestamp: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        from datetime import datetime

        return {
            "operation": self.operation,
            "component": self.component,
            "user_id": self.user_id,
            "request_id": self.request_id,
            "timestamp": self.timestamp or datetime.now().isoformat(),
            "extra": self.extra,
        }


def create_error_response(
    error: GangDanError, context: Optional[ErrorContext] = None
) -> Dict[str, Any]:
    """
    Create a standardized error response for API endpoints.

    Args:
        error: The exception to convert
        context: Optional error context

    Returns:
        Dictionary suitable for JSON API response
    """
    response = {
        "success": False,
        "error": error.to_dict(),
    }
    if context:
        response["context"] = context.to_dict()
    return response
