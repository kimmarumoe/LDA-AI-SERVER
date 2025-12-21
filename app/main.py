# app/main.py

import os
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .models.guide import GuideResponse
from .image_analysis import analyze_image_to_guide

# 앱 메타 정보 추가
app = FastAPI(
    title="LDA AI Server",
    version="0.1.0",
)

# ============================
# 환경 구분 (local | prod)
# - local: 로컬 개발(프론트 Vite dev 서버: localhost:5173)
# - prod : 배포 환경(프론트 Vercel: *.vercel.app)
ENV = os.getenv("ENV", "local")

# ============================
# CORS 설정 (환경별 분리)
# - 로컬에서는 localhost만 허용해서 빠르게 개발/테스트
# - 배포에서는 Vercel의 Preview/Production 도메인 전체를 허용
#   (예: lda-legodesignaid-git-main-xxx.vercel.app)
if ENV == "local":
    # 프론트(Vite dev 서버)에서 접근할 수 있도록 CORS 설정 (로컬 개발용)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    # 프론트(Vercel 배포)에서 접근할 수 있도록 CORS 설정 (배포용)
    # Vercel은 Preview 배포 시 도메인이 매번 달라질 수 있어 정규식 허용이 안전함
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https://.*\.vercel\.app",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/health")
async def health_check():
    # 서버 상태 확인용 (배포 후 살아있는지 체크할 때 유용)
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
