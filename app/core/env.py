# app/core/env.py
from __future__ import annotations

import os
from dotenv import load_dotenv

# .env는 로컬 개발 편의용, 배포 환경 변수 덮어쓰지 않게
load_dotenv(override=False)

def app_env() -> str:
    return (os.getenv("ENV") or os.getenv("APP_ENV") or "local").strip().lower()

def cors_allow_origins():
    v = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
    return v

def cors_allow_origin_regex():
    v = os.getenv("CORS_ALLOW_ORIGIN_REGEX", "").strip()
    return v or None
