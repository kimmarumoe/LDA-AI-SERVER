# app/image_analysis.py

from datetime import datetime
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
    GuideResponse,
)

GRID_WIDTH = 16
GRID_HEIGHT = 16


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"#{r:02X}{g:02X}{b:02X}"


async def analyze_image_to_guide(image: UploadFile) -> GuideResponse:
    """
    업로드된 이미지를 16x16 모자이크로 단순 변환하고,
    1행 단위로 조립 가이드(steps/groups)를 생성합니다.
    """

    # 1) 업로드 파일 -> PIL 이미지
    file_bytes = await image.read()
    pil = Image.open(BytesIO(file_bytes)).convert("RGB")

    # 2) 16x16 리사이즈 (각 픽셀 = 1 브릭)
    resized = pil.resize((GRID_WIDTH, GRID_HEIGHT), Image.NEAREST)
    img_np = np.array(resized)  # (H, W, 3)

    bricks: List[Brick] = []
    palette_counter: Dict[str, Dict[str, Any]] = {}

    # 3) 픽셀 단위로 Brick 생성 + 팔레트 카운트
    for y in range(GRID_HEIGHT):
        for x in range(GRID_WIDTH):
            r, g, b = img_np[y, x]
            hex_color = rgb_to_hex((int(r), int(g), int(b)))

            bricks.append(
                Brick(
                    x=x,
                    y=y,
                    z=0,
                    color=hex_color,
                    type="plate",  # MVP: 전부 1x1 plate 취급
                )
            )

            bucket = palette_counter.setdefault(
                hex_color,
                {"name": hex_color, "count": 0, "types": set()},
            )
            bucket["count"] += 1
            bucket["types"].add("plate")

    # 4) inventory (색상별 1x1 plate 수량)
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

    # 5) 조립 순서: 행(row) 단위 16단계
    steps: List[GuideStep] = []
    for y in range(GRID_HEIGHT):
        row_bricks = [b for b in bricks if b.y == y]
        steps.append(
            GuideStep(
                id=y + 1,
                title=f"{y + 1}행 배치",
                description="왼쪽에서 오른쪽 순서로 배치합니다.",
                bricks=row_bricks,
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

    # 7) summary / meta / tips
    total_bricks = len(bricks)
    unique_colors = len(palette)

    if total_bricks <= 128:
        difficulty = "초급"
        estimated_time = "30~45분"
    elif total_bricks <= 256:
        difficulty = "중급"
        estimated_time = "45~90분"
    else:
        difficulty = "상급"
        estimated_time = "90분 이상"

    summary = GuideSummary(
        totalBricks=total_bricks,
        uniqueTypes=unique_colors,
        difficulty=difficulty,
        estimatedTime=estimated_time,
    )

    meta = GuideMeta(
        width=GRID_WIDTH,
        height=GRID_HEIGHT,
        createdAt=datetime.utcnow(),
        source="ai",
    )

    tips = [
        "조립 전, 색상별로 브릭을 먼저 분류해 두면 훨씬 빠르게 조립할 수 있습니다.",
        "위에서 아래로(행 단위) 내려오며 배치하면 전체 모양을 확인하기 쉽습니다.",
    ]

    # ✅ GuideResponse 스키마가 extra를 허용하지 않는 경우를 대비해
    #    모델 생성 대신 dict로 반환해도 FastAPI가 response_model로 필터링합니다.
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
