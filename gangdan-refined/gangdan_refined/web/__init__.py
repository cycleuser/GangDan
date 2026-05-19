"""Web interface for GangDan Refined.

Provides Flask web application with thin route blueprints.
All business logic is in domain modules; routes only handle
HTTP request/response formatting.
"""

from .app import create_app

__all__ = ["create_app"]