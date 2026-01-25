# app/routers/guide.py
from __future__ import annotations

import json
import logging
from typing import Any, List, Optional, Tuple

from fastapi import APIRouter, UploadFile, File, HTTPException, Form

from app.image_analysis import analyze_image_to_guide
from app.services.analysis_store import AnalysisStore
from app.services.step_generator import generate_steps_by_rows

from app.schemas.build import BuildStepsRequest, BuildStepsResponse
from app.schemas.guide import (
    GuideResponse,
    GuideSummary,
    GuideMeta,
    PaletteItem,
    GuideBrick,
    GuideStep,
    GuideSection,
    GuideBounds,
    GuideBuildStep,
    StepPartSummary,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/guide", tags=["guide"])

ALLOWED_GRID = {"16x16": (16, 16), "32x32": (32, 32), "48x48": (48, 48)}
ALLOWED_COLORS = {8, 16, 24}

ALLOWED_BRICK_TYPES = {
    "1x1", "1x2", "1x3", "1x4", "1x5",
    "2x2", "2x3", "2x4", "2x5",
}

DEFAULT_GRID = (16, 16)
DEFAULT_MAX_COLORS = 16

_analysis_store = AnalysisStore()


def parse_grid_size(grid_size: Optional[str]) -> Tuple[int, int]:
    if not grid_size:
        return DEFAULT_GRID

    key = grid_size.replace(" ", "").lower()
    if key not in ALLOWED_GRID:
        raise HTTPException(status_code=422, detail=f"Invalid grid_size: {grid_size}")

    return ALLOWED_GRID[key]


def _to_int_or_none(v: Any) -> Optional[int]:
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

    cleaned = [x for x in cleaned if x in ALLOWED_BRICK_TYPES]
    if not cleaned:
        return None

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

        if s.startswith("["):
            try:
                arr = json.loads(s)
                if isinstance(arr, list) and all(isinstance(x, str) for x in arr):
                    return _normalize_brick_types([x.strip() for x in arr])
            except Exception:
                pass

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
    brick_mode: Optional[str],
) -> tuple[int, int, Optional[int], Optional[List[str]]]:
    grid_w, grid_h = parse_grid_size(grid_size)

    raw_color = max_colors if max_colors is not None else color_limit
    colors = parse_max_colors(raw_color)

    bt_list = _parse_brick_types_value(brick_types) or _parse_brick_types_value(allowed_bricks)

    if not options_json:
        return grid_w, grid_h, colors, bt_list

    try:
        obj = json.loads(options_json)
    except Exception:
        raise HTTPException(status_code=400, detail="options JSON이 올바르지 않습니다.")

    if not isinstance(obj, dict):
        return grid_w, grid_h, colors, bt_list

    gs = obj.get("gridSize") or obj.get("grid_size")
    if isinstance(gs, str):
        key = gs.replace(" ", "").lower()
        if key in ALLOWED_GRID:
            grid_w, grid_h = ALLOWED_GRID[key]
        else:
            raise HTTPException(status_code=422, detail=f"Invalid gridSize in options: {gs}")

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

    mc = obj["maxColors"] if "maxColors" in obj else obj.get("max_colors")
    cl = obj["colorLimit"] if "colorLimit" in obj else obj.get("color_limit")
    mc_i = _to_int_or_none(mc)
    cl_i = _to_int_or_none(cl)

    if mc_i is not None:
        colors = parse_max_colors(mc_i)
    elif cl_i is not None:
        colors = parse_max_colors(cl_i)

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

    _ = brick_mode
    return grid_w, grid_h, colors, bt_list


def _pick(obj: Any, names: List[str]) -> Any:
    if obj is None:
        return None
    for n in names:
        if isinstance(obj, dict) and n in obj:
            return obj[n]
        if hasattr(obj, n):
            return getattr(obj, n)
    return None


def _hex_key(v: Any) -> str:
    s = str(v or "").strip().upper()
    if not s:
        return ""
    if not s.startswith("#"):
        s = f"#{s}"
    return s


def _build_color_name_map(palette_like: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(palette_like, list):
        return out

    for p in palette_like:
        hx = _hex_key(_pick(p, ["hex", "color"]))
        if not hx:
            continue
        name = _pick(p, ["name", "colorName", "label"])
        name_str = str(name).strip() if isinstance(name, str) else ""
        out[hx] = name_str or hx

    return out


def _display_color_name(hex_str: str, name_map: Optional[dict[str, str]]) -> str:
    hx = _hex_key(hex_str) or str(hex_str)
    if not name_map:
        return hx
    return name_map.get(hx, hx)


def _normalize_type(t: Any) -> str:
    s = str(t or "").strip().lower()
    if s in ("", "plate", "tile", "plate_1x1", "tile_1x1", "1x1"):
        return "1x1"
    return s


def _brick_dims(brick_type: str) -> tuple[int, int]:
    try:
        w, h = str(brick_type).lower().split("x")
        return (max(1, int(w)), max(1, int(h)))
    except Exception:
        return (1, 1)


def _to_schema_brick(
    raw: Any,
    section_id: Optional[str] = None,
    color_name_map: Optional[dict[str, str]] = None,
) -> GuideBrick:
    x = int(_pick(raw, ["x"]) or 0)
    y = int(_pick(raw, ["y"]) or 0)
    z = int(_pick(raw, ["z"]) or 0)

    color_hex = _hex_key(_pick(raw, ["color", "hex"]) or "#000000")
    t = _normalize_type(_pick(raw, ["type"]))
    w, h = _brick_dims(t)

    return GuideBrick(
        id=f"{x},{y}:{t}",
        sectionId=section_id,
        x=x,
        y=y,
        z=z,
        # ✅ color = 표시용(레고 색상명), hex = 렌더링용(HEX)
        color=_display_color_name(color_hex, color_name_map),
        hex=color_hex,
        type=t,
        width=w,
        height=h,
        quantity=1,
    )


def _to_schema_meta(meta: Any, width: int, height: int, source: str = "ai") -> GuideMeta:
    created_at = _pick(meta, ["createdAt", "created_at"])
    if hasattr(created_at, "isoformat"):
        created_at_str = created_at.isoformat()
    else:
        created_at_str = str(created_at) if created_at else ""

    return GuideMeta(
        width=int(_pick(meta, ["width"]) or width),
        height=int(_pick(meta, ["height"]) or height),
        createdAt=created_at_str,
        source=source,
        gridSize=f"{width}x{height}",
    )


def _make_sections(width: int, height: int, mode: str, rows_per_section: int) -> list[GuideSection]:
    if mode == "single":
        return [
            GuideSection(
                id="S1",
                name="전체",
                bounds=GuideBounds(x=0, y=0, w=width, h=height),
            )
        ]

    if mode == "quadrants":
        mx, my = width // 2, height // 2
        quads = [
            ("S1", "좌상", 0, 0, mx, my),
            ("S2", "우상", mx, 0, width - mx, my),
            ("S3", "좌하", 0, my, mx, height - my),
            ("S4", "우하", mx, my, width - mx, height - my),
        ]
        out: list[GuideSection] = []
        for sid, name, x, y, w, h in quads:
            if w > 0 and h > 0:
                out.append(
                    GuideSection(
                        id=sid,
                        name=f"{name} 섹션",
                        bounds=GuideBounds(x=x, y=y, w=w, h=h),
                    )
                )
        return out

    out: list[GuideSection] = []
    rows_per_section = max(1, int(rows_per_section))
    y = 0
    idx = 1
    while y < height:
        h = min(rows_per_section, height - y)
        sid = f"S{idx}"
        out.append(
            GuideSection(
                id=sid,
                name=f"{idx}섹션 ({y + 1}~{y + h}행)",
                bounds=GuideBounds(x=0, y=y, w=width, h=h),
            )
        )
        idx += 1
        y += rows_per_section
    return out


def _in_bounds(b: GuideBrick, bounds: GuideBounds) -> bool:
    return (bounds.x <= b.x < bounds.x + bounds.w) and (bounds.y <= b.y < bounds.y + bounds.h)


def _parts_summary(
    bricks: list[GuideBrick],
    color_name_map: Optional[dict[str, str]] = None,
) -> list[StepPartSummary]:
    counter: dict[tuple[str, str], int] = {}
    for b in bricks:
        hx = _hex_key(b.hex)
        k = (b.type, hx)
        counter[k] = counter.get(k, 0) + 1

    out: list[StepPartSummary] = []
    for (t, hx), n in sorted(counter.items(), key=lambda x: (-x[1], x[0][0], x[0][1])):
        out.append(
            StepPartSummary(
                type=t,
                hex=hx,
                color=_display_color_name(hx, color_name_map),
                count=n,
            )
        )
    return out


@router.post("/analyze", response_model=GuideResponse)
async def analyze_guide(
    image: UploadFile = File(...),
    options: Optional[str] = Form(None),
    grid_size: Optional[str] = Form(None),
    max_colors: Optional[int] = Form(None),
    color_limit: Optional[int] = Form(None),
    brick_mode: Optional[str] = Form(None),
    brick_types: Optional[str] = Form(None),
    allowed_bricks: Optional[str] = Form(None),
) -> GuideResponse:
    if not image:
        raise HTTPException(status_code=400, detail="이미지 파일이 필요합니다.")

    grid_w, grid_h, colors, bt_list = merge_options(
        options_json=options,
        grid_size=grid_size,
        max_colors=max_colors,
        color_limit=color_limit,
        brick_types=brick_types,
        allowed_bricks=allowed_bricks,
        brick_mode=brick_mode,
    )

    logger.info("analyze merged grid=%sx%s colors=%s brickTypes=%s", grid_w, grid_h, colors, bt_list)

    raw = await analyze_image_to_guide(
        image=image,
        grid_w=grid_w,
        grid_h=grid_h,
        max_colors=colors,
        brick_types=None,  # STEP1은 1x1 기반 고정
    )

    meta_raw = _pick(raw, ["meta"])
    summary_raw = _pick(raw, ["summary"])
    palette_raw = _pick(raw, ["palette"]) or []
    bricks_raw = _pick(raw, ["bricks"]) or []
    groups_raw = _pick(raw, ["groups"]) or []

    width = int(_pick(meta_raw, ["width"]) or grid_w)
    height = int(_pick(meta_raw, ["height"]) or grid_h)

    summary = GuideSummary(
        totalBricks=int(_pick(summary_raw, ["totalBricks"]) or len(bricks_raw)),
        uniqueTypes=int(_pick(summary_raw, ["uniqueTypes"]) or len(palette_raw)),
        difficulty=str(_pick(summary_raw, ["difficulty"]) or "초급"),
        estimatedTime=str(_pick(summary_raw, ["estimatedTime"]) or ""),
    )

    palette: list[PaletteItem] = []
    for p in palette_raw:
        c = str(_pick(p, ["hex", "color"]) or "#000000")
        palette.append(
            PaletteItem(
                color=c,
                hex=c,
                name=_pick(p, ["name"]),
                count=int(_pick(p, ["count"]) or 0),
                types=list(_pick(p, ["types"]) or []),
            )
        )

    # ✅ palette 기반 HEX->이름 맵
    color_name_map = _build_color_name_map(palette)

    bricks: list[GuideBrick] = []
    for b in bricks_raw:
        bricks.append(_to_schema_brick(b, color_name_map=color_name_map))

    groups: list[GuideStep] = []
    for g in groups_raw:
        gid = int(_pick(g, ["id"]) or 0)
        title = str(_pick(g, ["title"]) or "")
        desc = _pick(g, ["description"])
        g_bricks_raw = _pick(g, ["bricks"]) or []
        g_bricks = [_to_schema_brick(x, color_name_map=color_name_map) for x in g_bricks_raw]
        groups.append(GuideStep(id=gid, title=title, description=desc, bricks=g_bricks))

    meta = _to_schema_meta(meta_raw, width=width, height=height, source="ai")
    meta.colorLimit = colors if isinstance(colors, int) else None
    meta.brickMode = brick_mode
    meta.sectionMode = None
    meta.optimized = False

    # ✅ STEP2용 저장(항상 HEX로 저장)
    analysis_id = _analysis_store.put(
        {
            "width": width,
            "height": height,
            "bricks": [
                {
                    "x": b.x,
                    "y": b.y,
                    "z": b.z,
                    "color": b.hex,   # ✅ 저장은 HEX
                    "type": "1x1",
                }
                for b in bricks
            ],
            "options": {
                "gridSize": f"{width}x{height}",
                "colorLimit": colors,
                "brickTypes": bt_list or [],
            },
            "palette": [
                {"hex": p.hex, "color": p.color, "name": p.name, "count": p.count, "types": p.types}
                for p in palette
            ],
        }
    )

    return GuideResponse(
        schemaVersion=1,
        analysisId=analysis_id,
        summary=summary,
        groups=groups,
        bricks=bricks,
        palette=palette,
        tips=list(_pick(raw, ["tips"]) or []),
        meta=meta,
        sections=[],
        steps=[],
    )


@router.post("/steps", response_model=BuildStepsResponse)
async def build_steps(req: BuildStepsRequest) -> BuildStepsResponse:
    try:
        record = _analysis_store.get(req.analysisId)
    except KeyError:
        raise HTTPException(
            status_code=410,
            detail={
                "code": "ANALYSIS_EXPIRED",
                "message": "analysisId가 만료/유실되었습니다. STEP1(분석)을 다시 진행해 주세요.",
            },
        )

    width = int(record.get("width", 16))
    height = int(record.get("height", 16))
    raw_bricks = list(record.get("bricks", []))

    # ✅ record.palette 기반 HEX->이름 맵
    color_name_map = _build_color_name_map(record.get("palette", []))

    all_bricks: list[GuideBrick] = [
        _to_schema_brick(b, color_name_map=color_name_map)
        for b in raw_bricks
    ]

    sections = _make_sections(width, height, req.sectionMode, req.rowsPerSection)

    steps_out: list[GuideBuildStep] = []
    step_index = 1

    for sec in sections:
        sec_bricks = [b for b in all_bricks if _in_bounds(b, sec.bounds)]
        if not sec_bricks:
            continue

        placements = [
            {
                "x": b.x,
                "y": b.y,
                "w": b.width,
                "h": b.height,
                "color": b.hex,  # ✅ 생성기는 HEX로만
                "type": b.type,
            }
            for b in sec_bricks
        ]

        raw_steps = generate_steps_by_rows(
            placements=placements,
            rows_per_step=req.rowsPerStep,
            max_placements_per_step=req.maxPlacementsPerStep,
        )

        for s in raw_steps:
            delta: list[GuideBrick] = []
            for p in s.get("placements", []):
                t = _normalize_type(p.get("type"))
                bw, bh = _brick_dims(t)

                hx = _hex_key(p.get("color", "#000000"))
                x = int(p.get("x", 0))
                y = int(p.get("y", 0))

                delta.append(
                    GuideBrick(
                        id=f"{x},{y}:{t}",
                        sectionId=sec.id,
                        x=x,
                        y=y,
                        z=0,
                        color=_display_color_name(hx, color_name_map),  # ✅ 이름
                        hex=hx,                                        # ✅ HEX
                        type=t,
                        width=bw,
                        height=bh,
                        quantity=1,
                    )
                )

            steps_out.append(
                GuideBuildStep(
                    id=f"{sec.id}-STEP-{step_index}",
                    sectionId=sec.id,
                    index=step_index,
                    title=f"{sec.name} · {step_index}단계",
                    description=str(s.get("description") or ""),
                    bricks=delta,
                    partsSummary=_parts_summary(delta, color_name_map),
                )
            )
            step_index += 1

    return BuildStepsResponse(
        analysisId=req.analysisId,
        sections=sections,
        steps=steps_out,
        bricks=all_bricks,
        meta={
            "width": width,
            "height": height,
            "sectionMode": req.sectionMode,
            "rowsPerSection": req.rowsPerSection,
            "rowsPerStep": req.rowsPerStep,
            "maxPlacementsPerStep": req.maxPlacementsPerStep,
            "optimize": bool(req.optimize),
        },
    )
