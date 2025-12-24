# app/core/errors.py
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def error_payload(code: str, message: str, detail: Optional[Any] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"error": {"code": code, "message": message}}
    if detail is not None:
        payload["error"]["detail"] = detail
    return payload


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        if isinstance(exc.detail, dict):
            code = str(exc.detail.get("code", "HTTP_EXCEPTION"))
            message = str(exc.detail.get("message", "요청 처리 중 오류가 발생했습니다."))
            detail = exc.detail.get("detail")
            return JSONResponse(status_code=exc.status_code, content=error_payload(code, message, detail))

        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload("HTTP_EXCEPTION", str(exc.detail) if exc.detail else "요청 처리 중 오류가 발생했습니다."),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=error_payload("VALIDATION_ERROR", "요청 값이 올바르지 않습니다.", exc.errors()),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content=error_payload("INTERNAL_ERROR", "서버 오류가 발생했습니다."),
        )
