# app/image_analysis.py

from datetime import datetime, timezone
from io import BytesIO
from typing import Dict, Any, Tuple, List

import numpy as np
from fastapi import UploadFile
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
    if not isinstance(value, int):
        return default
    return max(min_v, min(max_v, value))

def clamp_optional_int(value: int | None, default: int, min_v: int, max_v: int) -> int | None:
    # None은 "제한 없음"
    if value is None:
        return None

    # 0 이하면 "제한 없음" (라우터에서 처리하더라도 2중 방어)
    if isinstance(value, int) and value <= 0:
        return None

    # bool은 int의 하위 타입이라 걸러주는 게 안전
    if isinstance(value, bool):
        return default

    # int가 아니면 기본값으로
    if not isinstance(value, int):
        return default

    return max(min_v, min(max_v, value))

async def analyze_image_to_guide(
    image: UploadFile,
    grid_w: int = 16,
    grid_h: int = 16,
    max_colors: int | None = 16,
):
    """
    업로드된 이미지를 grid_w x grid_h 모자이크로 변환하고,
    1행 단위로 조립 가이드(steps)를 생성합니다.
    """

    #  grid는 항상 범위 제한
    grid_w = clamp_int(grid_w, 16, 8, 128)
    grid_h = clamp_int(grid_h, 16, 8, 128)

    # max_colors는 None(제한 없음) 유지 + 숫자일 때만 clamp
    max_colors = clamp_optional_int(max_colors, 16, 2, 256)

    # 1) 업로드 파일 -> PIL 이미지
    file_bytes = await image.read()
    pil = Image.open(BytesIO(file_bytes)).convert("RGB")

    # 2) grid_w x grid_h 리사이즈
    resized = pil.resize((grid_w, grid_h), Image.NEAREST)

    # 3) 색상 수 제한
    # ✅ max_colors=None 이면 제한 없음 → quantize 스킵
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
    for y in range(h):
        for x in range(w):
            r, g, b = img_np[y, x]
            hex_color = rgb_to_hex((int(r), int(g), int(b)))

            bricks.append(
                Brick(
                    x=x,
                    y=y,
                    z=0,
                    color=hex_color,
                    type="plate",
                )
            )

            bucket = palette_counter.setdefault(
                hex_color,
                {"name": hex_color, "count": 0, "types": set()},
            )
            bucket["count"] += 1
            bucket["types"].add("plate")

    # 5) inventory
    inventory = [
        {
            "type": "plate_1x1",
            "width": 1,
            "height": 1,
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
    # ✅ bricks가 row-major로 쌓이므로 슬라이스로 바로 자르기 (빠르고 단순)
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
    unique_colors = len(palette)

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
        createdAt=datetime.now(timezone.utc),  # ✅ utcnow 경고 회피
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
