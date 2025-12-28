# app/routers/guide.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from typing import Optional, Tuple
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

def parse_max_colors(max_colors: Optional[int]) -> int:
    if max_colors is None:
        return 16
    if max_colors not in ALLOWED_COLORS:
        raise HTTPException(status_code=422, detail=f"Invalid max_colors: {max_colors}")
    return max_colors

def merge_options(
    options_json: Optional[str],
    grid_size: Optional[str],
    max_colors: Optional[int],
) -> tuple[int, int, int]:
    # 1) 기본: Form 필드 기준
    grid_w, grid_h = parse_grid_size(grid_size)
    colors = parse_max_colors(max_colors)

    # 2) options(JSON) 호환 처리
    if options_json:
        try:
            obj = json.loads(options_json)
        except Exception:
            obj = None

        if isinstance(obj, dict):
            # 프론트 최신: { gridSize, maxColors }
            gs = obj.get("gridSize")
            mc = obj.get("maxColors")

            if isinstance(gs, str):
                key = gs.replace(" ", "").lower()
                if key in ALLOWED_GRID:
                    grid_w, grid_h = ALLOWED_GRID[key]

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
                    grid_w, grid_h = (w, h)

    return grid_w, grid_h, colors


@router.post("/analyze", response_model=GuideResponse)
async def analyze_guide(
    image: UploadFile = File(...),
    options: Optional[str] = Form(None),
    grid_size: Optional[str] = Form(None),
    max_colors: Optional[int] = Form(None),
) -> GuideResponse:
    if not image:
        raise HTTPException(status_code=400, detail="이미지 파일이 필요합니다.")

    grid_w, grid_h, colors = merge_options(options, grid_size, max_colors)

    # 분석 함수가 이 파라미터를 받아서 실제로 써야 결과가 바뀜
    return await analyze_image_to_guide(image, grid_w=grid_w, grid_h=grid_h, max_colors=colors)
