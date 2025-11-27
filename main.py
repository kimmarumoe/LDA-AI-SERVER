from typing import List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# =========================
# 1. FastAPI 앱 & CORS 설정
# =========================

app = FastAPI(
    title="LDA Guide API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # 개발 단계: 어디서든 호출 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# 2. 데이터 모델 정의
# =========================

# 브릭 식별자 타입 (그냥 str이지만 의미를 분리)
BrickId = str


class Brick(BaseModel):
    id: BrickId
    x: int
    y: int
    z: int
    color: str
    type: str


class GuideMeta(BaseModel):
    title: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    language: Optional[str] = "ko"   # 기본: 한글


class GuideRequest(BaseModel):
    bricks: List[Brick]
    meta: Optional[GuideMeta] = None


class GuideStep(BaseModel):
    step: int
    title: str
    description: str
    brickIds: List[BrickId]


class GuideStats(BaseModel):
    totalBricks: int
    totalSteps: int


class GuideResponse(BaseModel):
    steps: List[GuideStep]
    summary: Optional[str] = None
    stats: Optional[GuideStats] = None


# =========================
# 3. 가이드 생성 로직 (Mock)
# =========================

def generate_mock_guide(request: GuideRequest) -> GuideResponse:
    """
    간단한 규칙 기반 Mock 가이드:
    - 브릭을 (y, x) 순서로 정렬
    - y(줄) 값이 같은 것끼리 묶어서 한 단계(step)로 만든다.
    """
    bricks = sorted(request.bricks, key=lambda b: (b.y, b.x))

    steps: List[GuideStep] = []
    current_y: Optional[int] = None
    current_group: List[Brick] = []
    step_index = 1

    for brick in bricks:
        if current_y is None:
            # 첫 브릭 처리
            current_y = brick.y

        if brick.y != current_y:
            # 줄이 바뀌면 이전 줄을 하나의 단계로 확정
            step = _build_step_from_row(
                step_index=step_index,
                row_y=current_y,
                bricks_in_row=current_group,
                meta=request.meta,
            )
            steps.append(step)

            # 다음 줄 준비
            step_index += 1
            current_y = brick.y
            current_group = []

        current_group.append(brick)

    # 마지막 줄 처리
    if current_group:
        step = _build_step_from_row(
            step_index=step_index,
            row_y=current_y,
            bricks_in_row=current_group,
            meta=request.meta,
        )
        steps.append(step)

    # 통계 정보 계산
    stats = GuideStats(
        totalBricks=len(request.bricks),
        totalSteps=len(steps),
    )

    # 전체 요약 문장 생성
    summary = _build_summary(meta=request.meta, stats=stats)

    return GuideResponse(
        steps=steps,
        summary=summary,
        stats=stats,
    )


def _build_step_from_row(
    step_index: int,
    row_y: int,
    bricks_in_row: List[Brick],
    meta: Optional[GuideMeta],
) -> GuideStep:
    """
    y가 같은 브릭 묶음(한 줄)을 하나의 GuideStep으로 변환.
    """
    line_number = row_y + 1  # 사람 눈에는 0이 아니라 1번째 줄이 더 자연스러움
    title = f"{step_index}단계: {line_number}번째 줄 브릭 놓기"

    total = len(bricks_in_row)
    design_title = meta.title if meta and meta.title else "디자인"

    description = (
        f"{design_title}의 {line_number}번째 줄에 브릭 {total}개를 "
        f"왼쪽에서 오른쪽 순서대로 차례대로 놓아 주세요."
    )

    brick_ids = [b.id for b in bricks_in_row]

    return GuideStep(
        step=step_index,
        title=title,
        description=description,
        brickIds=brick_ids,
    )


def _build_summary(
    meta: Optional[GuideMeta],
    stats: GuideStats,
) -> str:
    """
    전체 가이드를 한 줄로 요약하는 문장 생성.
    """
    title = meta.title if meta and meta.title else "이 디자인"
    return (
        f"{title}은(는) 총 {stats.totalSteps}단계, "
        f"{stats.totalBricks}개의 브릭으로 완성됩니다."
    )


# =========================
# 4. 엔드포인트 정의
# =========================

@app.post("/api/guide", response_model=GuideResponse)
async def create_guide(request: GuideRequest) -> GuideResponse:
    """
    프론트에서 조립 가이드를 요청하는 엔드포인트.
    """
    guide = generate_mock_guide(request)
    return guide


@app.get("/health")
async def health():
    """
    서버 헬스 체크용 엔드포인트.
    """
    return {"status": "ok"}
