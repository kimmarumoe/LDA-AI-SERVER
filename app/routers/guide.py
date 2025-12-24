# app/routers/guide.py
from fastapi import APIRouter, UploadFile, File, HTTPException

from app.models.guide import GuideResponse          # ✅ models로 통일
from app.image_analysis import analyze_image_to_guide

router = APIRouter(prefix="/api/guide", tags=["guide"])

@router.post("/analyze", response_model=GuideResponse)
async def analyze_guide(image: UploadFile = File(...)) -> GuideResponse:
    if not image:
        raise HTTPException(status_code=400, detail="이미지 파일이 필요합니다.")

    # ✅ 여기서 GuideResponse(**result) 같은 “재조립” 하지 말고 그대로 반환
    return await analyze_image_to_guide(image)
