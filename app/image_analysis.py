# app/image_analysis.py

from datetime import datetime
from fastapi import UploadFile

from .models.guide import (
    Brick,
    GuideSummary,
    GuideStep,
    PaletteItem,
    GuideMeta,
    GuideResponse,
)


async def analyze_image_to_guide(image: UploadFile) -> GuideResponse:
    """
    TODO: 실제 이미지 분석 로직은 나중에 교체.
    현재는 Analyze 페이지 테스트용 샘플 GuideResponse를 반환하는 더미 버전.
    """

    # 1) 요약 정보
    summary = GuideSummary(
        totalBricks=9,
        uniqueTypes=2,
        difficulty="초급",
        estimatedTime="30~45분",
    )

    # 2) 브릭 좌표 (스마일 16x16 샘플)
    bricks = [
        # 눈 2개 (검정)
        Brick(x=4, y=4, z=0, color="#000000", type="1x1"),
        Brick(x=11, y=4, z=0, color="#000000", type="1x1"),
        # 입 (검정)
        Brick(x=7, y=9, z=0, color="#000000", type="1x1"),
        # 주변 노란색 (배경)
        Brick(x=5, y=5, z=0, color="#facc15", type="1x1"),
        Brick(x=6, y=6, z=0, color="#facc15", type="1x1"),
        Brick(x=8, y=6, z=0, color="#facc15", type="1x1"),
        Brick(x=9, y=5, z=0, color="#facc15", type="1x1"),
        Brick(x=6, y=8, z=0, color="#facc15", type="1x1"),
        Brick(x=8, y=8, z=0, color="#facc15", type="1x1"),
    ]

    # 3) 단계 정보 (지금은 한 단계로 전체 조립)
    groups = [
        GuideStep(
            id=1,
            title="스마일 16x16 전체 조립",
            description="AI 연동 전, Analyze 페이지 테스트용 샘플 가이드입니다.",
            bricks=bricks,
        )
    ]

    # 4) 팔레트 정보
    palette = [
        PaletteItem(
            color="#facc15",
            name="Yellow",
            count=6,
            types=["1x1"],
        ),
        PaletteItem(
            color="#000000",
            name="Black",
            count=3,
            types=["1x1"],
        ),
    ]

    # 5) 메타 정보
    meta = GuideMeta(
        width=16,
        height=16,
        createdAt=datetime.utcnow(),
        source="sample",
    )

    # 6) 최종 GuideResponse 반환
    guide = GuideResponse(
        summary=summary,
        groups=groups,
        palette=palette,
        meta=meta,
    )
    return guide
