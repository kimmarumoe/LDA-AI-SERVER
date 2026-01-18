# app/image_analysis.py
from datetime import datetime, timezone
from io import BytesIO
from typing import Dict, Any, Tuple, List, Optional
import re

import numpy as np
from fastapi import UploadFile, HTTPException
from PIL import Image

from .models.guide import (
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
    # None은 "제한 없음"
    if value is None:
        return None

    # 0 이하면 "제한 없음"
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
    "2x5" 형태면 (2,5) 반환.
    그 외는 (1,1)로 간주.
    """
    if not brick_type:
        return (1, 1)

    s = str(brick_type).strip().lower()

    # "plate_2x5" 같은 형태도 허용하고 싶으면 여기서 확장 가능
    m = _BRICK_RE.match(s)
    if not m:
        return (1, 1)

    try:
        w = int(m.group("w"))
        h = int(m.group("h"))
    except Exception:
        return (1, 1)

    # 안전 범위
    w = max(1, min(64, w))
    h = max(1, min(64, h))
    return (w, h)


def select_brick_type(brick_types: Optional[List[str]]) -> str:
    """
    brick_types가 여러 개면, 가장 면적이 큰 타입을 우선 선택.
    예: ["1x1","1x2","2x3"] -> "2x3"
    """
    if not brick_types:
        return "plate"

    cleaned = [str(x).strip() for x in brick_types if isinstance(x, str) and str(x).strip()]
    if not cleaned:
        return "plate"

    # 숫자형 "WxH"가 섞여 있으면 가장 큰 면적을 선택
    best = cleaned[0]
    best_area = 1

    for t in cleaned:
        w, h = parse_brick_type_dims(t)
        area = w * h
        if area > best_area:
            best = t
            best_area = area

    return best


async def analyze_image_to_guide(
    image: UploadFile,
    grid_w: int = 16,
    grid_h: int = 16,
    max_colors: int | None = 16,
    brick_types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    업로드된 이미지를 grid_w x grid_h 모자이크로 변환하고,
    행(row) 단위로 조립 가이드(groups/steps)를 생성합니다.

    주의:
    - 현재는 픽셀 1개당 Brick 1개 생성(1x1 방식)이라 totalBricks는 grid 크기에 고정됩니다.
    - brick_types는 Brick.type 값/인벤토리 표기에 반영됩니다.
      (큰 브릭으로 묶어서 개수를 줄이는 타일링 로직은 별도 구현이 필요)
    """

    # grid는 항상 범위 제한
    grid_w = clamp_int(grid_w, 16, 8, 128)
    grid_h = clamp_int(grid_h, 16, 8, 128)

    # max_colors는 None(제한 없음) 유지 + 숫자일 때만 clamp
    max_colors = clamp_optional_int(max_colors, 16, 2, 256)

    selected_type = select_brick_type(brick_types)
    bt_w, bt_h = parse_brick_type_dims(selected_type)

    # 1) 업로드 파일 -> PIL 이미지
    try:
        file_bytes = await image.read()
        pil = Image.open(BytesIO(file_bytes)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="이미지 파일을 읽을 수 없습니다.")

    # 2) grid_w x grid_h 리사이즈
    resized = pil.resize((grid_w, grid_h), Image.NEAREST)

    # 3) 색상 수 제한
    # max_colors=None 이면 제한 없음 -> quantize 스킵
    if max_colors is not None and max_colors < 256:
        try:
            method = getattr(Image, "MEDIANCUT", 0)
            resized = resized.quantize(colors=max_colors, method=method).convert("RGB")
        except Exception:
            resized = resized.convert("RGB")

    img_np = np.array(resized)  # (H, W, 3)
    h, w = img_np.shape[:2]

    bricks: List[Brick] = []
    palette_counter: Dict[str, Dict[str, Any]] = {}

    # 4) 픽셀 단위로 Brick 생성 + 팔레트 카운트
    # groupId는 "행 단위 그룹"과 맞추기 위해 (y+1)로 지정
    for y in range(h):
        gid = y + 1
        for x in range(w):
            r, g, b = img_np[y, x]
            hex_color = rgb_to_hex((int(r), int(g), int(b)))

            bricks.append(
                Brick(
                    x=x,
                    y=y,
                    z=0,
                    color=hex_color,
                    type=selected_type if selected_type != "plate" else "plate",
                    groupId=gid,
                )
            )

            bucket = palette_counter.setdefault(
                hex_color,
                {"name": hex_color, "count": 0, "types": set()},
            )
            bucket["count"] += 1
            bucket["types"].add(selected_type if selected_type != "plate" else "plate")

    # 5) inventory
    # 현재는 색상별로 동일 type 1종만 쌓이므로 단순 집계
    inv_type = "plate_1x1" if selected_type == "plate" else f"plate_{bt_w}x{bt_h}"
    inventory = [
        {
            "type": inv_type,
            "width": 1 if selected_type == "plate" else bt_w,
            "height": 1 if selected_type == "plate" else bt_h,
            "hex": hex_code,
            "color": hex_code,
            "count": data["count"],
        }
        for hex_code, data in sorted(
            palette_counter.items(),
            key=lambda item: item[1]["count"],
            reverse=True,
        )
    ]

    # 6) 조립 순서: 행(row) 단위 h 단계
    steps: List[GuideStep] = []
    for y in range(h):
        row_bricks = bricks[y * w : (y + 1) * w]
        steps.append(
            GuideStep(
                id=y + 1,
                title=f"{y + 1}행 배치",
                description="왼쪽에서 오른쪽 순서로 배치합니다.",
                bricks=row_bricks,
            )
        )

    # 7) palette 리스트
    palette = [
        PaletteItem(
            color=hex_code,
            hex=hex_code,
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

    # 8) summary / meta / tips
    total_bricks = len(bricks)
    unique_colors = len(palette)  # 기존 API의 uniqueTypes가 사실상 "유니크 색상 수"로 쓰이는 상황 유지

    if total_bricks <= 128:
        difficulty = "초급"
        estimated_time = "30~45분"
    elif total_bricks <= 256:
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
        "조립 전, 색상별로 브릭을 먼저 분류해 두면 훨씬 빠르게 조립할 수 있습니다.",
        "위에서 아래로(행 단위) 내려오며 배치하면 전체 모양을 확인하기 쉽습니다.",
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
