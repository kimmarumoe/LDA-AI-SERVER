from datetime import datetime, timezone
from io import BytesIO
from typing import Dict, Any, Tuple, List, Optional
import re

import numpy as np
from fastapi import UploadFile, HTTPException
from PIL import Image

from app.models.guide import (
    Brick,
    GuideSummary,
    GuideStep,
    PaletteItem,
    GuideMeta,
)


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"#{r:02X}{g:02X}{b:02X}"


def clamp_int(value: int, default: int, min_v: int, max_v: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        return default
    return max(min_v, min(max_v, value))


def clamp_optional_int(value: int | None, default: int, min_v: int, max_v: int) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool) and value <= 0:
        return None
    if isinstance(value, bool):
        return default
    if not isinstance(value, int):
        return default
    return max(min_v, min(max_v, value))


_BRICK_RE = re.compile(r"^(?P<w>\d+)x(?P<h>\d+)$")


def parse_brick_type_dims(brick_type: str) -> tuple[int, int]:
    """
    "2x3" 형태면 (2,3) 반환.
    그 외는 (1,1)로 간주.
    """
    if not brick_type:
        return (1, 1)

    s = str(brick_type).strip().lower()
    m = _BRICK_RE.match(s)
    if not m:
        return (1, 1)

    try:
        w = int(m.group("w"))
        h = int(m.group("h"))
    except Exception:
        return (1, 1)

    w = max(1, min(64, w))
    h = max(1, min(64, h))
    return (w, h)


def normalize_brick_types(brick_types: Optional[List[str]]) -> List[str]:
    """
    - 입력이 없으면 기본 ["1x1"]
    - 입력이 있으면 정리 + 항상 "1x1"을 fallback으로 포함(빈칸 방지)
    """
    if not brick_types:
        return ["1x1"]

    cleaned: List[str] = []
    seen = set()

    for x in brick_types:
        if not isinstance(x, str):
            continue
        s = x.strip().lower()
        if not s:
            continue
        w, h = parse_brick_type_dims(s)
        key = f"{w}x{h}"
        if key not in seen:
            cleaned.append(key)
            seen.add(key)

    if "1x1" not in seen:
        cleaned.append("1x1")

    return cleaned


def build_candidates(brick_types: List[str], allow_rotate: bool) -> List[tuple[str, int, int, int]]:
    """
    반환: (type_str, w, h, area) 리스트
    - 큰 면적 우선 정렬
    - allow_rotate면 (w,h)와 (h,w) 둘 다 후보로 추가(서로 다를 때만)
    """
    out: List[tuple[str, int, int, int]] = []
    seen = set()

    for t in brick_types:
        w, h = parse_brick_type_dims(t)
        key = (w, h)
        if key not in seen:
            out.append((f"{w}x{h}", w, h, w * h))
            seen.add(key)

        if allow_rotate and w != h:
            key2 = (h, w)
            if key2 not in seen:
                out.append((f"{h}x{w}", h, w, h * w))
                seen.add(key2)

    out.sort(key=lambda x: (x[3], x[1], x[2]), reverse=True)
    return out


def can_place(
    colors_grid: List[List[str]],
    occ: List[List[bool]],
    x: int,
    y: int,
    bw: int,
    bh: int,
    target_color: str,
) -> bool:
    h = len(colors_grid)
    w = len(colors_grid[0]) if h else 0

    if x + bw > w or y + bh > h:
        return False

    for yy in range(y, y + bh):
        row_c = colors_grid[yy]
        row_o = occ[yy]
        for xx in range(x, x + bw):
            if row_o[xx]:
                return False
            if row_c[xx] != target_color:
                return False

    return True


def place(
    occ: List[List[bool]],
    x: int,
    y: int,
    bw: int,
    bh: int,
) -> None:
    for yy in range(y, y + bh):
        for xx in range(x, x + bw):
            occ[yy][xx] = True


async def analyze_image_to_guide(
    image: UploadFile,
    grid_w: int = 16,
    grid_h: int = 16,
    max_colors: int | None = 16,
    brick_types: Optional[List[str]] = None,
    allow_rotate: bool = True,
) -> Dict[str, Any]:
    """
    타일링(패킹) 버전:
    - 셀 색상이 동일한 영역에서 큰 브릭부터 배치
    - 남는 칸은 1x1로 메움(항상 fallback 포함)
    - allow_rotate=True면 1x3 <-> 3x1 자동 배치 가능
    """

    grid_w = clamp_int(grid_w, 16, 8, 128)
    grid_h = clamp_int(grid_h, 16, 8, 128)
    max_colors = clamp_optional_int(max_colors, 16, 2, 256)

    bt = normalize_brick_types(brick_types)
    candidates = build_candidates(bt, allow_rotate)

    # 1) 업로드 파일 -> PIL 이미지
    try:
        file_bytes = await image.read()
        pil = Image.open(BytesIO(file_bytes)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="이미지 파일을 읽을 수 없습니다.")

    # 2) grid_w x grid_h 리사이즈
    resized = pil.resize((grid_w, grid_h), Image.NEAREST)

    # 3) 색상 수 제한
    if max_colors is not None and max_colors < 256:
        try:
            method = getattr(Image, "MEDIANCUT", 0)
            resized = resized.quantize(colors=max_colors, method=method).convert("RGB")
        except Exception:
            resized = resized.convert("RGB")

    img_np = np.array(resized)  # (H, W, 3)
    h, w = img_np.shape[:2]

    # 색상 그리드(hex) 구성
    colors_grid: List[List[str]] = []
    for y in range(h):
        row: List[str] = []
        for x in range(w):
            r, g, b = img_np[y, x]
            row.append(rgb_to_hex((int(r), int(g), int(b))))
        colors_grid.append(row)

    occ: List[List[bool]] = [[False] * w for _ in range(h)]

    bricks: List[Brick] = []
    palette_counter: Dict[str, Dict[str, Any]] = {}
    inventory_counter: Dict[tuple[str, str], int] = {}

    # 4) 타일링(그리디): 좌상단부터 훑으면서 큰 브릭부터 시도
    for y in range(h):
        gid = y + 1  # 시작 y 기준으로 행 그룹
        for x in range(w):
            if occ[y][x]:
                continue

            target_color = colors_grid[y][x]
            placed_any = False

            for type_str, bw, bh, _area in candidates:
                if can_place(colors_grid, occ, x, y, bw, bh, target_color):
                    place(occ, x, y, bw, bh)

                    bricks.append(
                        Brick(
                            x=x,
                            y=y,
                            z=0,
                            color=target_color,
                            type=type_str,
                            groupId=gid,
                        )
                    )

                    # 팔레트/인벤토리: "브릭 개수" 기준으로 집계
                    bucket = palette_counter.setdefault(
                        target_color,
                        {"name": target_color, "count": 0, "types": set()},
                    )
                    bucket["count"] += 1
                    bucket["types"].add(type_str)

                    inventory_counter[(type_str, target_color)] = (
                        inventory_counter.get((type_str, target_color), 0) + 1
                    )

                    placed_any = True
                    break

            if not placed_any:
                # candidates에 항상 1x1이 포함되므로 보통 여기로 오지 않음
                place(occ, x, y, 1, 1)
                bricks.append(
                    Brick(
                        x=x,
                        y=y,
                        z=0,
                        color=target_color,
                        type="1x1",
                        groupId=gid,
                    )
                )
                bucket = palette_counter.setdefault(
                    target_color,
                    {"name": target_color, "count": 0, "types": set()},
                )
                bucket["count"] += 1
                bucket["types"].add("1x1")
                inventory_counter[("1x1", target_color)] = inventory_counter.get(("1x1", target_color), 0) + 1

    # 5) steps: 행 단위(시작 y 기준)로 묶기
    bricks_by_row: List[List[Brick]] = [[] for _ in range(h)]
    for b in bricks:
        if 0 <= b.y < h:
            bricks_by_row[b.y].append(b)

    steps: List[GuideStep] = []
    for y in range(h):
        steps.append(
            GuideStep(
                id=y + 1,
                title=f"{y + 1}행 배치",
                description="왼쪽에서 오른쪽 순서로 배치합니다.",
                bricks=bricks_by_row[y],
            )
        )

    # 6) palette 리스트
    palette = [
        PaletteItem(
            color=hex_code,
            name=data["name"],
            count=data["count"],
            types=sorted(list(data["types"])),
        )
        for hex_code, data in sorted(
            palette_counter.items(),
            key=lambda item: item[1]["count"],
            reverse=True,
        )
    ]

    # 7) inventory 리스트
    inventory: List[Dict[str, Any]] = []
    for (type_str, hex_code), count in sorted(
        inventory_counter.items(),
        key=lambda item: item[1],
        reverse=True,
    ):
        bw, bh = parse_brick_type_dims(type_str)
        inventory.append(
            {
                "type": f"plate_{bw}x{bh}",
                "width": bw,
                "height": bh,
                "hex": hex_code,
                "color": hex_code,
                "count": count,
            }
        )

    # 8) summary / meta / tips
    total_bricks = len(bricks)          # 타일링 결과 브릭 개수 (이제 w*h 고정 아님)
    unique_colors = len(palette)        # 유니크 색상 수

    if w * h <= 128:
        difficulty = "초급"
        estimated_time = "30~45분"
    elif w * h <= 256:
        difficulty = "중급"
        estimated_time = "45~90분"
    else:
        difficulty = "고급"
        estimated_time = "90분 이상"

    summary = GuideSummary(
        totalBricks=total_bricks,
        uniqueTypes=unique_colors,
        difficulty=difficulty,
        estimatedTime=estimated_time,
    )

    meta = GuideMeta(
        width=w,
        height=h,
        createdAt=datetime.now(timezone.utc),
        source="ai",
    )

    tips = [
        "큰 브릭부터 배치하고 남는 칸은 1x1로 메우는 방식입니다.",
        "회전 허용 시 1x3은 3x1로 자동 배치될 수 있습니다.",
        "색이 완전히 같은 영역에서만 큰 브릭이 들어갑니다.",
    ]

    return {
        "summary": summary,
        "bricks": bricks,
        "groups": steps,
        "steps": steps,
        "palette": palette,
        "tips": tips,
        "meta": meta,
        "inventory": inventory,
    }
