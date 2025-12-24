# app/core/env.py
from __future__ import annotations

import os
from typing import List, Optional


def _csv(key: str, default: str = "") -> List[str]:
    raw = os.getenv(key, default).strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def app_env() -> str:
    # local | preview | prod
    return os.getenv("APP_ENV", "local").strip().lower()


def cors_allow_origins() -> List[str]:
    # 예: CORS_ALLOW_ORIGINS="http://localhost:5173,https://xxx.vercel.app"
    return _csv("CORS_ALLOW_ORIGINS")


def cors_allow_origin_regex() -> Optional[str]:
    # 예: CORS_ALLOW_ORIGIN_REGEX="^https://.*\.vercel\.app$"
    raw = os.getenv("CORS_ALLOW_ORIGIN_REGEX", "").strip()
    return raw or None
