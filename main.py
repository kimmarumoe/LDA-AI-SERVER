# ai_server/main.py (중요 부분만 발췌)

from typing import Any, Dict, List

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from image_analysis import analyze_image_bytes  # ★ 방금 만든 서비스 모듈


class GuideSummary(BaseModel):
    totalBricks: int
    uniqueTypes: int
    difficulty: str
    estimatedTime: str


class GuideResponse(BaseModel):
    summary: GuideSummary
    # groups 구조는 아직 확정 X → 느슨하게 Any 사용
    groups: List[Dict[str, Any]]


SAMPLE_GUIDE: Dict[str, Any] = {
    "summary": {
        "totalBricks": 124,
        "uniqueTypes": 8,
        "difficulty": "중급",
        "estimatedTime": "60~90분",
    },
    "groups": [
        {
            "id": 1,
            "title": "1단계 - 외곽선 쌓기",
            "description": "이미지 전체 외곽을 어두운 브릭으로 먼저 쌓아 기준 프레임을 만듭니다.",
            "stepCount": 3,
        },
        {
            "id": 2,
            "title": "2단계 - 주요 색상 채우기",
            "description": "피사체(캐릭터/로고)의 주 색상을 먼저 채우고, 배경은 나중에 채웁니다.",
            "stepCount": 5,
        },
    ],
}


app = FastAPI(title="LDA AI Server")

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.post("/api/guide/analyze", response_model=GuideResponse)
async def analyze_image(image: UploadFile = File(...)) -> GuideResponse:
    """
    업로드된 이미지를 받아서 레고 조립 가이드를 생성하는 엔드포인트.
    - v1: 이미지 색상/크기 기반 규칙으로 summary + groups 계산.
    - 실패 시 샘플 가이드를 반환.
    """
    image_bytes = await image.read()

    try:
        data = analyze_image_bytes(image_bytes)
    except Exception:
        # TODO: logger를 붙여서 예외 로그 남기면 좋음
        return GuideResponse(**SAMPLE_GUIDE)

    return GuideResponse(**data)
