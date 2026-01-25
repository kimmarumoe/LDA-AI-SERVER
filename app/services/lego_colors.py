# app/services/lego_colors.py
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional, Dict, List, Tuple

# ------------------------------------------------------------
# Data model
# ------------------------------------------------------------

@dataclass(frozen=True)
class LegoColor:
    id: str
    name_en: str
    hex: str
    rgb: Tuple[int, int, int]


def _norm_hex(hex_str: str) -> str:
    s = (hex_str or "").strip().upper()
    if not s:
        return ""
    if not s.startswith("#"):
        s = f"#{s}"
    # "#RRGGBB"만 허용
    if len(s) != 7:
        return ""
    return s


def _hex_to_rgb(hex_str: str) -> Optional[Tuple[int, int, int]]:
    h = _norm_hex(hex_str)
    if not h:
        return None
    try:
        r = int(h[1:3], 16)
        g = int(h[3:5], 16)
        b = int(h[5:7], 16)
        return (r, g, b)
    except Exception:
        return None


def _dist2(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


# ------------------------------------------------------------
# CSV loading (Rebrickable colors.csv)
# - columns usually include: id, name, rgb, ...
# - rgb is like "F4F4F4" (without #)
# ------------------------------------------------------------

def _default_csv_path() -> Path:
    # app/services/lego_colors.py -> parents[1] == app/
    app_dir = Path(__file__).resolve().parents[1]
    return app_dir / "data" / "colors.csv"


@lru_cache(maxsize=1)
def _load_colors() -> Tuple[List[LegoColor], Dict[str, LegoColor]]:
    # env override 가능 (배포/도커에서 유용)
    env_path = os.getenv("LEGO_COLORS_CSV_PATH")
    csv_path = Path(env_path).expanduser().resolve() if env_path else _default_csv_path()

    if not csv_path.exists():
        # 못 찾으면 빈 리스트로 (상위에서 hex fallback)
        return ([], {})

    colors: List[LegoColor] = []
    by_hex: Dict[str, LegoColor] = {}

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Rebrickable colors.csv: id, name, rgb, is_trans, ...
            cid = str(row.get("id", "")).strip()
            name = str(row.get("name", "")).strip()
            rgb_raw = str(row.get("rgb", "")).strip().upper()

            hx = _norm_hex(rgb_raw) if rgb_raw.startswith("#") else _norm_hex(f"#{rgb_raw}")
            rgb = _hex_to_rgb(hx)

            if not cid or not name or not hx or rgb is None:
                continue

            c = LegoColor(id=cid, name_en=name, hex=hx, rgb=rgb)
            colors.append(c)

            # exact 매칭 우선
            if hx not in by_hex:
                by_hex[hx] = c

    return (colors, by_hex)


# ------------------------------------------------------------
# Korean label (optional)
# - 전부 완벽 번역은 양이 많으니:
#   1) 자주 나오는 색만 오버라이드
#   2) 나머지는 영문 유지
# ------------------------------------------------------------

_KO_OVERRIDES: Dict[str, str] = {
    "Black": "검정",
    "White": "흰색",
    "Red": "빨강",
    "Blue": "파랑",
    "Yellow": "노랑",
    "Green": "초록",
    "Dark Bluish Gray": "진한 회색(블루 계열)",
    "Light Bluish Gray": "연한 회색(블루 계열)",
    "Dark Gray": "진회색",
    "Light Gray": "연회색",
    "Tan": "탄(베이지)",
    "Reddish Brown": "적갈색",
    "Brown": "갈색",
    "Dark Brown": "진갈색",
    "Orange": "주황",
    "Pink": "분홍",
    "Purple": "보라",
}


def _to_korean(name_en: str) -> str:
    s = (name_en or "").strip()
    if not s:
        return ""
    return _KO_OVERRIDES.get(s, s)  # 없으면 영문 그대로


# ------------------------------------------------------------
# Public API
# ------------------------------------------------------------

def resolve_lego_color_name(hex_color: str, *, lang: str = "en") -> str:
    """
    입력 HEX(이미지 픽셀) -> 가장 가까운 LEGO 컬러명 반환
    - lang="en": 영문
    - lang="ko": 일부는 한글 오버라이드, 나머지는 영문 유지
    """
    hx = _norm_hex(hex_color)
    if not hx:
        return str(hex_color)

    colors, by_hex = _load_colors()
    if not colors:
        return hx  # csv 못 읽으면 폴백

    # 1) exact match
    exact = by_hex.get(hx)
    if exact:
        return _to_korean(exact.name_en) if lang == "ko" else exact.name_en

    # 2) nearest match
    rgb = _hex_to_rgb(hx)
    if rgb is None:
        return hx

    best = None
    best_d = 10**18
    for c in colors:
        d = _dist2(rgb, c.rgb)
        if d < best_d:
            best = c
            best_d = d

    if not best:
        return hx

    return _to_korean(best.name_en) if lang == "ko" else best.name_en
