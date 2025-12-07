# app/main.py

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .models.guide import GuideResponse
from .image_analysis import analyze_image_to_guide

app = FastAPI()

# (필요하면 CORS 설정 – 프론트 localhost:5173 에서 접근하기 위함)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/api/guide/analyze", response_model=GuideResponse)
async def analyze_guide(image: UploadFile = File(...)):
    """
    이미지 파일을 받아 레고 조립 가이드를 생성하는 엔드포인트.
    현재는 샘플 GuideResponse를 반환하는 더미 버전.
    """
    try:
        guide = await analyze_image_to_guide(image)
        return guide
    except Exception as e:
        # TODO: 로깅 추가 예정
        raise HTTPException(status_code=500, detail=str(e))
