from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class GridRange:
    """그리드 입력 검증 규칙(단일 소스, SSOT)."""
    min_size: int = 8
    max_size: int = 128


DEFAULT_GRID: Tuple[int, int] = (16, 16)

# UI 프리셋(기존 프론트/문서와 호환을 위해 유지)
GRID_PRESETS: Dict[str, Tuple[int, int]] = {
    "16x16": (16, 16),
    "32x32": (32, 32),
    "48x48": (48, 48),
}

_GRID_RE = re.compile(r"^(?P<w>\d+)(?:[x×✕\*](?P<h>\d+))?$")


def parse_grid_size(value: str | None, *, rng: GridRange = GridRange()) -> Tuple[int, int]:
    """그리드 크기 입력을 (w, h)로 파싱합니다.

    허용 포맷
    - "16x16" 같은 프리셋
    - "64x80" (x, ×, * 허용)
    - "64" (정사각형 단축 표기 -> 64x64)

    검증 규칙
    - 각 변: rng.min_size ~ rng.max_size

    실패 시 ValueError
    """
    if value is None:
        return DEFAULT_GRID

    s = str(value).strip().lower().replace(" ", "")
    if not s:
        return DEFAULT_GRID

    if s in GRID_PRESETS:
        return GRID_PRESETS[s]

    m = _GRID_RE.match(s)
    if not m:
        raise ValueError(f"Invalid grid format: {value}")

    w = int(m.group("w"))
    h = int(m.group("h")) if m.group("h") is not None else w

    if not (rng.min_size <= w <= rng.max_size) or not (rng.min_size <= h <= rng.max_size):
        raise ValueError(f"Grid out of range: {w}x{h} (allowed {rng.min_size}~{rng.max_size})")

    return (w, h)


def parse_grid_from_object(obj: object, *, rng: GridRange = GridRange()) -> Tuple[int, int] | None:
    """{"width": 64, "height": 80} 같은 객체에서 (w,h) 파싱.

    - 파싱 가능하면 (w,h)
    - 관련 키가 없으면 None
    - 범위/타입이 이상하면 ValueError
    """
    if not isinstance(obj, dict):
        return None

    if "width" not in obj and "height" not in obj:
        return None

    try:
        w = int(obj.get("width"))
        h = int(obj.get("height"))
    except Exception:
        raise ValueError("Grid width/height must be integers")

    if not (rng.min_size <= w <= rng.max_size) or not (rng.min_size <= h <= rng.max_size):
        raise ValueError(f"Grid out of range: {w}x{h} (allowed {rng.min_size}~{rng.max_size})")

    return (w, h)
