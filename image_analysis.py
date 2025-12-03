# ai_server/image_analysis.py

from io import BytesIO
from typing import Any, Dict, List
from collections import Counter

import numpy as np
from PIL import Image


# 분석용 타겟 해상도
# - 픽셀 1개를 1x1 브릭 1개라고 가정
# - 48 x 48 = 2304 브릭 정도 → 너무 과하지도, 너무 작지도 않은 수준
TARGET_WIDTH = 48
TARGET_HEIGHT = 48


def _open_image(image_bytes: bytes) -> Image.Image:
    """
    바이트 데이터를 Pillow 이미지로 변환하는 헬퍼 함수.
    FastAPI나 UploadFile에 의존하지 않는 순수 로직.
    """
    buffer = BytesIO(image_bytes)
    img = Image.open(buffer)
    return img.convert("RGB")  # 색상 계산을 위해 RGB로 통일


def _resize_for_bricks(img: Image.Image) -> Image.Image:
    """
    브릭 분석용으로 이미지를 작은 그리드로 리사이즈.
    - 너무 크면 브릭 개수가 과도하게 커지므로 제한.
    - NEAREST로 줄여서 색상이 번지지 않도록 유지.
    """
    # Pillow 버전에 따라 Resampling enum 유무가 달라질 수 있어서 안전하게 처리
    resampling = getattr(Image, "Resampling", None)
    if resampling is not None:
        return img.resize(
            (TARGET_WIDTH, TARGET_HEIGHT),
            resample=resampling.NEAREST,
        )
    return img.resize((TARGET_WIDTH, TARGET_HEIGHT), resample=Image.NEAREST)


def _estimate_summary(np_img: np.ndarray) -> Dict[str, Any]:
    """
    numpy 이미지 배열을 받아서 브릭 요약 정보를 계산.
    - totalBricks: 전체 픽셀 수 ≒ 브릭 개수
    - uniqueTypes: 색상 개수
    - difficulty, estimatedTime: 간단한 규칙 기반
    """
    height, width, _ = np_img.shape
    pixels = np_img.reshape(-1, 3)

    total_bricks = height * width

    # RGB 색상 튜플로 변환 후 고유 색상 수 계산
    colors = [tuple(p) for p in pixels]
    unique_colors = len(set(colors))

    # 난이도는 색상 수 + 크기 기준의 대략적인 룰로 설정
    if total_bricks <= 800 and unique_colors <= 6:
        difficulty = "초급"
        estimated_time = "20~40분"
    elif total_bricks <= 2000 and unique_colors <= 12:
        difficulty = "중급"
        estimated_time = "40~90분"
    else:
        difficulty = "상급"
        estimated_time = "90분 이상"

    return {
        "totalBricks": int(total_bricks),
        "uniqueTypes": int(unique_colors),
        "difficulty": difficulty,
        "estimatedTime": estimated_time,
    }


def _build_color_groups(np_img: np.ndarray, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    가장 많이 등장하는 상위 색상들을 기반으로 브릭 그룹을 생성.
    - 실제 LEGO 팔레트가 아닌, 단순 RGB 기준.
    - 나중에 팔레트 매핑 로직으로 교체 가능.
    """
    pixels = np_img.reshape(-1, 3)
    colors = [tuple(p) for p in pixels]
    counter = Counter(colors)
    most_common = counter.most_common(top_k)

    groups: List[Dict[str, Any]] = []

    for idx, (rgb, count) in enumerate(most_common, start=1):
        r, g, b = rgb
        hex_color = f"#{r:02X}{g:02X}{b:02X}"
        groups.append(
            {
                "name": f"주요 색상 #{idx}",
                "items": [
                    f"1x1 브릭 {count}개 (RGB {r}, {g}, {b}, {hex_color})",
                ],
            }
        )

    return groups


def analyze_image_bytes(image_bytes: bytes) -> Dict[str, Any]:
    """
    외부에서 호출하는 메인 함수.
    - 이미지 바이트를 받아서 summary + groups 정보를 반환.
    - FastAPI, UploadFile 등에 의존하지 않는 순수 로직.
    """
    img = _open_image(image_bytes)
    img_small = _resize_for_bricks(img)

    np_img = np.array(img_small, dtype=np.uint8)

    summary = _estimate_summary(np_img)
    groups = _build_color_groups(np_img)

    return {
        "summary": summary,
        "groups": groups,
        # TODO: 나중에 bricks / steps / tips 등 확장 가능
    }
