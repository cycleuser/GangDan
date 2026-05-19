"""Tests for core.errors module."""

from gangdan_refined.core.errors import (
    GangDanError,
    ConfigurationError,
    ValidationError,
    APIError,
    DatabaseError,
    FileError,
    TimeoutError,
    ModelError,
    ToolResult,
    ErrorContext,
    create_error_response,
)


class TestToolResult:
    def test_success(self):
        result = ToolResult(success=True, data="hello")
        assert result.success is True
        assert result.data == "hello"
        assert bool(result) is True

    def test_failure(self):
        result = ToolResult(success=False, error="something failed")
        assert result.success is False
        assert result.error == "something failed"
        assert bool(result) is False

    def test_to_dict(self):
        result = ToolResult(success=True, data={"key": "value"}, metadata={"meta": 1})
        d = result.to_dict()
        assert d["success"] is True
        assert d["data"] == {"key": "value"}
        assert d["metadata"] == {"meta": 1}

    def test_to_dict_failure(self):
        result = ToolResult(success=False, error="fail")
        d = result.to_dict()
        assert d["success"] is False
        assert d["data"] is None
        assert d["error"] == "fail"


class TestExceptionHierarchy:
    def test_base_error(self):
        err = GangDanError("test error")
        assert str(err) == "test error"
        assert err.code == "UNKNOWN_ERROR"

    def test_configuration_error(self):
        err = ConfigurationError("bad config")
        assert err.code == "CONFIGURATION_ERROR"

    def test_validation_error(self):
        err = ValidationError("invalid input", field="email")
        assert err.code == "VALIDATION_ERROR"
        assert err.context["field"] == "email"

    def test_api_error(self):
        err = APIError("api failed", provider="ollama", status_code=500)
        assert err.code == "API_ERROR"
        assert err.context["provider"] == "ollama"

    def test_database_error(self):
        err = DatabaseError("chroma fail")
        assert err.code == "DATABASE_ERROR"

    def test_file_error(self):
        err = FileError("not found", path="/tmp/test")
        assert err.code == "FILE_ERROR"
        assert err.context["path"] == "/tmp/test"

    def test_timeout_error(self):
        err = TimeoutError("timed out", operation="embed")
        assert err.code == "TIMEOUT_ERROR"

    def test_model_error(self):
        err = ModelError("not found", model_name="llama2")
        assert err.code == "MODEL_ERROR"
        assert err.context["model_name"] == "llama2"


class TestErrorContext:
    def test_to_dict(self):
        ctx = ErrorContext(operation="chat", component="llm")
        d = ctx.to_dict()
        assert d["operation"] == "chat"
        assert d["component"] == "llm"
        assert d["timestamp"] is not None


class TestCreateErrorResponse:
    def test_error_response(self):
        err = APIError("connection failed", provider="ollama")
        ctx = ErrorContext(operation="chat", component="ollama")
        response = create_error_response(err, ctx)
        assert response["success"] is False
        assert response["error"]["error"] == "API_ERROR"
        assert response["context"]["operation"] == "chat"

    def test_error_response_no_context(self):
        err = DatabaseError("chroma fail")
        response = create_error_response(err)
        assert response["success"] is False
        assert "context" not in response