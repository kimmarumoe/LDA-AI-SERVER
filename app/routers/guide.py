# app/routers/guide.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from typing import Optional, Tuple, List, Any
import json

from app.models.guide import GuideResponse
from app.image_analysis import analyze_image_to_guide

router = APIRouter(prefix="/api/guide", tags=["guide"])

ALLOWED_GRID = {"16x16": (16, 16), "32x32": (32, 32), "48x48": (48, 48)}
ALLOWED_COLORS = {8, 16, 24}

# 프론트 BRICK_TYPES와 맞추는 게 안전 (H-3)
ALLOWED_BRICK_TYPES = {
    "1x1", "1x2", "1x3", "1x4", "1x5",
    "2x2", "2x3", "2x4", "2x5",
}

DEFAULT_GRID = (16, 16)
DEFAULT_MAX_COLORS = 16


def parse_grid_size(grid_size: Optional[str]) -> Tuple[int, int]:
    if not grid_size:
        return DEFAULT_GRID

    key = grid_size.replace(" ", "").lower()
    if key not in ALLOWED_GRID:
        raise HTTPException(status_code=422, detail=f"Invalid grid_size: {grid_size}")

    return ALLOWED_GRID[key]


def _to_int_or_none(v: Any) -> Optional[int]:
    """options(JSON)에서 숫자가 str/float로 와도 안전하게 int로 변환"""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return int(float(s))
        except Exception:
            return None
    return None


def parse_max_colors(max_colors: Optional[int]) -> Optional[int]:
    """
    정책:
    - None(미전송): 기본 16
    - 0 이하: 제한 없음(None)
    - 8/16/24: 허용
    """
    if max_colors is None:
        return DEFAULT_MAX_COLORS

    if max_colors <= 0:
        return None

    if max_colors not in ALLOWED_COLORS:
        raise HTTPException(status_code=422, detail=f"Invalid max_colors: {max_colors}")

    return max_colors


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out


def _normalize_brick_types(bt: Optional[List[str]]) -> Optional[List[str]]:
    if not bt:
        return None

    cleaned = [x.strip() for x in bt if isinstance(x, str) and x.strip()]
    cleaned = _dedupe_preserve_order(cleaned)

    # 서버 기준 허용 타입만 남김
    cleaned = [x for x in cleaned if x in ALLOWED_BRICK_TYPES]
    if not cleaned:
        return None

    # 1x1은 항상 포함
    if "1x1" not in cleaned:
        cleaned = ["1x1"] + cleaned

    return cleaned


def _parse_brick_types_value(v: object) -> Optional[List[str]]:
    """
    허용 입력:
    - ["2x5", "1x2"] 같은 list[str]
    - "2x5" 같은 단일 string
    - '["2x5","1x2"]' 같은 JSON string
    - "2x5,1x2" 같은 콤마 구분 string
    """
    if v is None:
        return None

    if isinstance(v, list):
        if all(isinstance(x, str) for x in v):
            return _normalize_brick_types([x.strip() for x in v])
        return None

    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None

        # JSON 배열 문자열
        if s.startswith("["):
            try:
                arr = json.loads(s)
                if isinstance(arr, list) and all(isinstance(x, str) for x in arr):
                    return _normalize_brick_types([x.strip() for x in arr])
            except Exception:
                pass

        # 단일 값 또는 콤마 구분
        parts = [p.strip() for p in s.split(",") if p.strip()]
        return _normalize_brick_types(parts)

    return None


def merge_options(
    options_json: Optional[str],
    grid_size: Optional[str],
    max_colors: Optional[int],
    color_limit: Optional[int],
    brick_types: Optional[str],
    allowed_bricks: Optional[str],
    brick_mode: Optional[str],  # 현재는 호환용(분석 로직에 필요하면 이후 확장)
) -> tuple[int, int, Optional[int], Optional[List[str]]]:
    # 1) 기본: 개별 Form 필드 기준
    grid_w, grid_h = parse_grid_size(grid_size)

    # color_limit / max_colors 둘 다 들어올 수 있으니 우선순위 적용
    # (둘 다 있으면 max_colors 우선, 없으면 color_limit, 둘 다 없으면 기본 16)
    raw_color = max_colors if max_colors is not None else color_limit
    colors = parse_max_colors(raw_color)

    # brick_types / allowed_bricks 둘 다 받을 수 있음
    bt_list = _parse_brick_types_value(brick_types) or _parse_brick_types_value(allowed_bricks)

    # 2) options(JSON) 호환 처리
    if not options_json:
        return grid_w, grid_h, colors, bt_list

    try:
        obj = json.loads(options_json)
    except Exception:
        raise HTTPException(status_code=400, detail="options JSON이 올바르지 않습니다.")

    if not isinstance(obj, dict):
        return grid_w, grid_h, colors, bt_list

    # grid: 최신/혼용 키 모두 허용
    gs = obj.get("gridSize") or obj.get("grid_size")
    if isinstance(gs, str):
        key = gs.replace(" ", "").lower()
        if key in ALLOWED_GRID:
            grid_w, grid_h = ALLOWED_GRID[key]
        else:
            raise HTTPException(status_code=422, detail=f"Invalid gridSize in options: {gs}")

    # 과거 구조: grid:{width,height}
    g = obj.get("grid")
    if isinstance(g, dict):
        w = g.get("width")
        h = g.get("height")
        if isinstance(w, int) and isinstance(h, int):
            key = f"{w}x{h}".lower()
            if key in ALLOWED_GRID:
                grid_w, grid_h = ALLOWED_GRID[key]
            else:
                raise HTTPException(status_code=422, detail=f"Invalid grid in options: {w}x{h}")

    # colors: 최신/혼용 키 모두 허용 (문자열 숫자도 방어)
    mc = obj.get("maxColors") or obj.get("max_colors")
    cl = obj.get("colorLimit") or obj.get("color_limit")
    mc_i = _to_int_or_none(mc)
    cl_i = _to_int_or_none(cl)

    if mc_i is not None:
        colors = parse_max_colors(mc_i)
    elif cl_i is not None:
        colors = parse_max_colors(cl_i)

    # bricks: allowed_bricks / brick_types / brickTypes 등 모두 허용
    bt = (
        obj.get("allowed_bricks")
        or obj.get("allowedBricks")
        or obj.get("brick_types")
        or obj.get("brickTypes")
        or obj.get("brickType")
    )
    parsed_bt = _parse_brick_types_value(bt)
    if parsed_bt:
        bt_list = parsed_bt

    # brick_mode는 현재 analyze_image_to_guide가 받지 않아서 여기선 호환용으로만 유지
    _ = brick_mode

    return grid_w, grid_h, colors, bt_list


def _pick(obj: Any, names: List[str]) -> Any:
    """dict / pydantic model / 일반 객체 모두에서 first-hit 값을 꺼내는 헬퍼"""
    if obj is None:
        return None
    for n in names:
        if isinstance(obj, dict) and n in obj:
            return obj[n]
        if hasattr(obj, n):
            return getattr(obj, n)
    return None


@router.post("/analyze", response_model=GuideResponse)
async def analyze_guide(
    image: UploadFile = File(...),
    options: Optional[str] = Form(None),
    grid_size: Optional[str] = Form(None),
    max_colors: Optional[int] = Form(None),

    # 프론트가 보내는 호환 필드들(지금 Network에 이미 찍히는 값들)
    color_limit: Optional[int] = Form(None),
    brick_mode: Optional[str] = Form(None),
    brick_types: Optional[str] = Form(None),
    allowed_bricks: Optional[str] = Form(None),
) -> GuideResponse:
    if not image:
        raise HTTPException(status_code=400, detail="이미지 파일이 필요합니다.")

    # (1) merged 값 계산
    grid_w, grid_h, colors, bt_list = merge_options(
        options_json=options,
        grid_size=grid_size,
        max_colors=max_colors,
        color_limit=color_limit,
        brick_types=brick_types,
        allowed_bricks=allowed_bricks,
        brick_mode=brick_mode,
    )

    # (2) 요청 값/병합 값 로그
    print(
        "[raw]",
        "grid_size=", grid_size,
        "max_colors=", max_colors,
        "color_limit=", color_limit,
        "brick_mode=", brick_mode,
        "brick_types=", brick_types,
        "allowed_bricks=", allowed_bricks,
    )
    print("[merged] use grid:", grid_w, grid_h, "colors:", colors, "bt_list:", bt_list)

    # (3) result 먼저 만든 다음, 실제 결과(meta/summary) 로그
    result = await analyze_image_to_guide(
        image=image,
        grid_w=grid_w,
        grid_h=grid_h,
        max_colors=colors,       # None이면 제한 없음
        brick_types=bt_list,     # None이면 기본 정책(image_analysis) 사용
    )

    meta = _pick(result, ["meta"])
    summary = _pick(result, ["summary"])

    gw = _pick(meta, ["gridWidth", "grid_width", "width", "w"])
    gh = _pick(meta, ["gridHeight", "grid_height", "height", "h"])
    tb = _pick(summary, ["totalBricks", "total_bricks", "total"])

    if gw is not None and gh is not None:
        print("[result.meta] grid:", gw, gh)
    if tb is not None:
        print("[result.summary] totalBricks:", tb)

    return result
