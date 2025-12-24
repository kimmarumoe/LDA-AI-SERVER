# app/main.py
from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.core.env import app_env, cors_allow_origins, cors_allow_origin_regex
from app.core.errors import register_exception_handlers
from app.routers.guide import router as guide_router  # ✅ 라우터 연결

app = FastAPI()

# ✅ 에러 표준화(한 곳에서만 등록)
register_exception_handlers(app)

# ===== CORS (환경별 분리) =====
ENV = app_env()
origins = cors_allow_origins()
origin_regex = cors_allow_origin_regex()

# ✅ prod는 regex 금지(명확한 분리)
if ENV == "prod":
    origin_regex = None

# ✅ local 기본값(편의)
if ENV == "local" and not origins:
    origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

# ✅ preview/prod에서 CORS 비어있으면 조용히 망가지는 거 방지(선택)
if ENV in ("preview", "prod") and (not origins) and (not origin_regex):
    raise RuntimeError(
        "CORS 설정이 비어있습니다. CORS_ALLOW_ORIGINS 또는 CORS_ALLOW_ORIGIN_REGEX를 설정하세요."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "ok", "env": ENV}

# ✅ 엔드포인트는 라우터에서만 관리 (중복/충돌 방지)
app.include_router(guide_router)
