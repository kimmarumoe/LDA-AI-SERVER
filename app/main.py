# app/main.py

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .models.guide import GuideResponse
from .image_analysis import analyze_image_to_guide

# 앱 메타 정보 추가 (선택이지만 있으면 좋음)
app = FastAPI(
    title="LDA AI Server",
    version="0.1.0",
)

# 프론트(Vite dev 서버)에서 접근할 수 있도록 CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173",
                   "http://127.0.0.1:5173",
                   "https://lda-legodesignaid.vercel.app",
],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/api/guide/analyze", response_model=GuideResponse)
async def analyze_guide(image: UploadFile = File(...)) -> GuideResponse:
    """
    이미지 파일을 받아 레고 조립 가이드를 생성하는 엔드포인트.
    현재는 analyze_image_to_guide()에서 샘플 GuideResponse를 반환하는 더미 버전.
    """
    try:
        guide = await analyze_image_to_guide(image)
        return guide
    except HTTPException:
        # 내부에서 이미 HTTPException을 던진 경우 상태코드를 그대로 유지
        raise
    except Exception as e:
        # TODO: 추후 로깅 추가 예정
        raise HTTPException(status_code=500, detail=str(e))
