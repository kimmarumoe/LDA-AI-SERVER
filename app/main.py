# app/main.py
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from app.core.env import app_env, cors_allow_origins, cors_allow_origin_regex
from app.core.errors import error_payload, register_exception_handlers
from app.routers.guide import router as guide_router

app = FastAPI()
register_exception_handlers(app)

ENV = (app_env() or "local").lower()

origins = cors_allow_origins() or []
if isinstance(origins, str):
    origins = [o.strip() for o in origins.split(",") if o.strip()]

origin_regex = cors_allow_origin_regex()

# local 기본값
if ENV == "local" and not origins and not origin_regex:
    origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

# prod 기본값: vercel preview/배포 도메인 대응
if ENV == "prod" and not origin_regex:
    origin_regex = r"^https://.*\.vercel\.app$"

print(f"[BOOT] ENV={ENV} origins={origins} origin_regex={origin_regex}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(
            code="HTTP_EXCEPTION",
            message=str(exc.detail) if exc.detail else "요청 처리 중 오류가 발생했습니다.",
        ),
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=error_payload(
            code="VALIDATION_ERROR",
            message="요청 값이 올바르지 않습니다.",
            detail=exc.errors(),
        ),
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content=error_payload(
            code="INTERNAL_ERROR",
            message="서버 오류가 발생했습니다.",
        ),
    )

@app.get("/health")
async def health_check():
    return {"status": "ok"}

app.include_router(guide_router)
