# ai-server/app/routers/guide.py

from datetime import datetime
from fastapi import APIRouter, UploadFile, File, HTTPException

from app.schemas.guide import (
    GuideResponse,
    GuideSummary,
    GuideBrick,
    GuideStep,
    PaletteItem,
    GuideMeta,
)

router = APIRouter(
    prefix="/api/guide",
    tags=["guide"],
)


@router.post("/analyze", response_model=GuideResponse)
async def analyze_guide(file: UploadFile = File(...)) -> GuideResponse:
    """
    업로드된 이미지를 기반으로 레고 조립 가이드를 생성하는 엔드포인트 (더미 버전)

    - 현재는 파일 내용을 실제로 분석하지 않고
    - 프론트에서 개발/연동을 테스트하기 위한 샘플 데이터를 반환한다.
    """
    if not file:
        raise HTTPException(status_code=400, detail="이미지 파일이 필요합니다.")

    # 1) summary
    summary = GuideSummary(
        totalBricks=124,
        uniqueTypes=8,
        difficulty="중급",
        estimatedTime="60~90분",
    )

    # 2) bricks (전체 브릭 리스트)
    bricks = [
        GuideBrick(
            x=0,
            y=0,
            z=0,
            color="bright-red",
            hex="#FF0000",
            type="plate",
            width=1,
            height=1,
            quantity=1,
        ),
        GuideBrick(
            x=1,
            y=0,
            z=0,
            color="bright-yellow",
            hex="#F9E54E",
            type="plate",
            width=1,
            height=1,
            quantity=1,
        ),
        GuideBrick(
            x=0,
            y=1,
            z=0,
            color="bright-blue",
            hex="#0055BF",
            type="tile",
            width=1,
            height=1,
            quantity=1,
        ),
        GuideBrick(
            x=1,
            y=1,
            z=1,
            color="bright-red",
            hex="#FF0000",
            type="brick",
            width=1,
            height=1,
            quantity=1,
        ),
    ]

    # 3) groups (단계/영역별)
    groups = [
        GuideStep(
            id=1,
            title="1단계 - 배경 채우기",
            description="배경이 되는 영역을 먼저 채웁니다.",
            bricks=bricks[:2],
        ),
        GuideStep(
            id=2,
            title="2단계 - 포인트 영역 쌓기",
            description="중요한 포인트 위치에 브릭을 쌓아 입체감을 만듭니다.",
            bricks=bricks[2:],
        ),
    ]

    # 4) palette (색상 요약)
    palette = [
        PaletteItem(
            color="bright-red",
            name="레드",
            count=60,
            types=["plate", "brick"],
        ),
        PaletteItem(
            color="bright-yellow",
            name="옐로우",
            count=32,
            types=["plate"],
        ),
        PaletteItem(
            color="bright-blue",
            name="블루",
            count=32,
            types=["tile"],
        ),
    ]

    # 5) meta / tips
    meta = GuideMeta(
        width=16,
        height=16,
        createdAt=datetime.utcnow().isoformat(),
        source="sample",
    )

    tips = [
        "비슷한 색상 브릭은 미리 분류해두면 조립 속도가 빨라집니다.",
        "중요한 포인트 영역부터 먼저 쌓고 배경을 마무리하는 순서를 추천합니다.",
    ]

    return GuideResponse(
        summary=summary,
        groups=groups,
        bricks=bricks,
        palette=palette,
        tips=tips,
        meta=meta,
    )
