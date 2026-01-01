from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from typing import Optional, Tuple, List
import json

from app.models.guide import GuideResponse
from app.image_analysis import analyze_image_to_guide

router = APIRouter(prefix="/api/guide", tags=["guide"])

ALLOWED_GRID = {"16x16": (16, 16), "32x32": (32, 32), "48x48": (48, 48)}
ALLOWED_COLORS = {8, 16, 24}


def parse_grid_size(grid_size: Optional[str]) -> Tuple[int, int]:
    if not grid_size:
        return (16, 16)

    key = grid_size.replace(" ", "").lower()
    if key not in ALLOWED_GRID:
        raise HTTPException(status_code=422, detail=f"Invalid grid_size: {grid_size}")

    return ALLOWED_GRID[key]


def parse_max_colors(max_colors: Optional[int]) -> Optional[int]:
    """
    - None(미전송): 기본 16
    - 0 이하: 제한 없음(None)
    - 8/16/24: 허용
    """
    if max_colors is None:
        return 16

    if max_colors <= 0:
        return None

    if max_colors not in ALLOWED_COLORS:
        raise HTTPException(status_code=422, detail=f"Invalid max_colors: {max_colors}")

    return max_colors


def parse_allow_rotate(v: object) -> bool:
    """
    - 미전송: 기본 True
    - bool: 그대로
    - str: "true/false/1/0/yes/no" 등 파싱
    """
    if v is None:
        return True

    if isinstance(v, bool):
        return v

    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("1", "true", "yes", "y", "on"):
            return True
        if s in ("0", "false", "no", "n", "off"):
            return False

    return True


def _parse_brick_types_value(v: object) -> Optional[List[str]]:
    """
    허용 입력:
    - ["2x3", "1x2"] 같은 list[str]
    - "2x3" 같은 단일 string
    - '["2x3","1x2"]' 같은 JSON string
    - "2x3,1x2" 같은 콤마 구분 string
    """
    if v is None:
        return None

    if isinstance(v, list):
        if all(isinstance(x, str) for x in v):
            bt = [x.strip() for x in v if x.strip()]
            return bt or None
        return None

    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None

        if s.startswith("["):
            try:
                arr = json.loads(s)
                if isinstance(arr, list) and all(isinstance(x, str) for x in arr):
                    bt = [x.strip() for x in arr if x.strip()]
                    return bt or None
            except Exception:
                pass

        parts = [p.strip() for p in s.split(",") if p.strip()]
        return parts or None

    return None


def merge_options(
    options_json: Optional[str],
    grid_size: Optional[str],
    max_colors: Optional[int],
    brick_types: Optional[str],
    allow_rotate: Optional[str],
) -> tuple[int, int, Optional[int], Optional[List[str]], bool]:
    # 1) 기본: 개별 Form 필드 기준
    grid_w, grid_h = parse_grid_size(grid_size)
    colors = parse_max_colors(max_colors)
    bt_list = _parse_brick_types_value(brick_types)
    rotate = parse_allow_rotate(allow_rotate)

    # 2) options(JSON) 호환 처리
    if not options_json:
        return grid_w, grid_h, colors, bt_list, rotate

    try:
        obj = json.loads(options_json)
    except Exception:
        raise HTTPException(status_code=400, detail="options JSON이 올바르지 않습니다.")

    if not isinstance(obj, dict):
        return grid_w, grid_h, colors, bt_list, rotate

    # 최신: { gridSize, maxColors, allowRotate }
    gs = obj.get("gridSize") or obj.get("grid_size")
    mc = obj.get("maxColors") or obj.get("max_colors")
    ar = obj.get("allowRotate") or obj.get("allow_rotate") or obj.get("rotate")

    if isinstance(gs, str):
        key = gs.replace(" ", "").lower()
        if key in ALLOWED_GRID:
            grid_w, grid_h = ALLOWED_GRID[key]
        else:
            raise HTTPException(status_code=422, detail=f"Invalid gridSize in options: {gs}")

    if isinstance(mc, int):
        colors = parse_max_colors(mc)

    # 과거/혼용: colorLimit
    cl = obj.get("colorLimit")
    if isinstance(cl, int):
        colors = parse_max_colors(cl)

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

    # brick types: brick_types / brickTypes / brickType 모두 허용
    bt = obj.get("brick_types") or obj.get("brickTypes") or obj.get("brickType")
    parsed_bt = _parse_brick_types_value(bt)
    if parsed_bt:
        bt_list = parsed_bt

    rotate = parse_allow_rotate(ar) if ar is not None else rotate

    return grid_w, grid_h, colors, bt_list, rotate


@router.post("/analyze", response_model=GuideResponse)
async def analyze_guide(
    image: UploadFile = File(...),
    options: Optional[str] = Form(None),
    grid_size: Optional[str] = Form(None),
    max_colors: Optional[int] = Form(None),
    brick_types: Optional[str] = Form(None),
    allow_rotate: Optional[str] = Form(None),
) -> GuideResponse:
    if not image:
        raise HTTPException(status_code=400, detail="이미지 파일이 필요합니다.")

    grid_w, grid_h, colors, bt_list, rotate = merge_options(
        options, grid_size, max_colors, brick_types, allow_rotate
    )

    return await analyze_image_to_guide(
        image=image,
        grid_w=grid_w,
        grid_h=grid_h,
        max_colors=colors,       # None이면 제한 없음
        brick_types=bt_list,     # None이면 기본 1x1로 타일링
        allow_rotate=rotate,     # True면 1x3 <-> 3x1 자동 배치 가능
    )
