# ai-server/app/services/analysis_store.py
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict

import logging
logger = logging.getLogger(__name__)


@dataclass
class AnalysisRecord:
    payload: Dict[str, Any]
    expires_at: float


class AnalysisStore:
    def __init__(self) -> None:
        self._store: Dict[str, AnalysisRecord] = {}

    def put(self, payload: Dict[str, Any], ttl_seconds: int = 60 * 30) -> str:
        self._cleanup()
        analysis_id = uuid.uuid4().hex
        ttl = max(60, int(ttl_seconds))
        self._store[analysis_id] = AnalysisRecord(payload=payload, expires_at=time.time() + ttl)

        logger.info("[STORE] put id=%s size=%d ttl=%ds", analysis_id, len(self._store), ttl)
        return analysis_id

    def get(self, analysis_id: str) -> Dict[str, Any]:
        self._cleanup()
        logger.info("[STORE] get id=%s size=%d", analysis_id, len(self._store))

        rec = self._store.get(analysis_id)
        if not rec:
            raise KeyError(analysis_id)
        if rec.expires_at < time.time():
            self._store.pop(analysis_id, None)
            raise KeyError(analysis_id)
        return rec.payload

    def _cleanup(self) -> None:
        now = time.time()
        expired_keys = [k for k, v in self._store.items() if v.expires_at < now]
        for k in expired_keys:
            self._store.pop(k, None)
