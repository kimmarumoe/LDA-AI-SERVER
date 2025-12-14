# ai-server/app/routers/guide.py

from fastapi import APIRouter, UploadFile, File, HTTPException

from app.schemas.guide import GuideResponse
from app.image_analysis import analyze_image_to_guide

router = APIRouter(
    prefix="/api/guide",
    tags=["guide"],
)


@router.post("/analyze", response_model=GuideResponse)
async def analyze_guide(file: UploadFile = File(...)) -> GuideResponse:
    """
    업로드된 이미지를 기반으로 레고 조립 가이드를 생성하는 엔드포인트

    - 실제 분석 로직은 app.image_analysis.analyze_image_to_guide 에서 담당한다.
    - 이 엔드포인트는 분석 결과를 GuideResponse 형태로 감싸서 반환만 한다.
    """
    if not file:
        raise HTTPException(status_code=400, detail="이미지 파일이 필요합니다.")

    try:
        # 실제 이미지 분석 함수 호출
        result = await analyze_image_to_guide(file)
    except Exception as e:
        # 분석 도중 에러가 발생하면 500 에러로 감싸서 반환
        raise HTTPException(
            status_code=500,
            detail=f"이미지 분석 중 오류가 발생했습니다: {str(e)}",
        )

    # dict 형태의 result를 Pydantic 모델(GuideResponse)로 변환
    return GuideResponse(**result)
