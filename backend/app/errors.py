"""JSON error handling. Every error response looks like {"error": {"code", "message", "details"?}}."""
from __future__ import annotations

import logging
from typing import Any

from flask import Flask, jsonify
from pydantic import ValidationError
from psycopg import OperationalError
from psycopg_pool import PoolTimeout
from werkzeug.exceptions import HTTPException
from .db import DatabaseNotConfigured

log = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def bad_request(message: str, details: Any = None) -> ApiError:
    return ApiError(400, "bad_request", message, details)


def not_found(message: str = "Not found") -> ApiError:
    return ApiError(404, "not_found", message)


def unauthorized(message: str = "Missing or invalid bearer token") -> ApiError:
    return ApiError(401, "unauthorized", message)


def _body(code: str, message: str, details: Any = None) -> dict:
    err: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    return {"error": err}


def register_error_handlers(app: Flask) -> None:
    def _database_unavailable(e: Exception):
        # Keep connection details and credentials out of the public response.
        log.warning('Database unavailable (%s)', type(e).__name__)
        return jsonify(_body('database_unavailable', 'The backend cannot connect to its database.')), 503

    for error_type in (DatabaseNotConfigured, PoolTimeout, OperationalError):
        app.register_error_handler(error_type, _database_unavailable)

    @app.errorhandler(ApiError)
    def _api_error(e: ApiError):
        return jsonify(_body(e.code, e.message, e.details)), e.status

    @app.errorhandler(ValidationError)
    def _validation_error(e: ValidationError):
        details = [
            {"loc": list(err.get("loc", ())), "msg": err.get("msg"), "type": err.get("type")}
            for err in e.errors()
        ]
        return jsonify(_body("validation_error", "Invalid request", details)), 400

    @app.errorhandler(HTTPException)
    def _http_error(e: HTTPException):
        code = (e.name or "error").lower().replace(" ", "_")
        return jsonify(_body(code, e.description or e.name)), e.code or 500

    @app.errorhandler(Exception)
    def _unhandled(e: Exception):
        log.exception("Unhandled error")
        return jsonify(_body("internal_error", "Internal server error")), 500
