# ai-server/app/schemas/guide.py

from typing import List, Optional
from pydantic import BaseModel, Field
from typing_extensions import Literal


class GuideSummary(BaseModel):
    """
    레고 가이드 상단 요약 정보 (STEP 01에서도 사용)
    """
    totalBricks: int
    uniqueTypes: int
    difficulty: Literal["초급", "중급", "고급"]
    estimatedTime: str


class GuideBrick(BaseModel):
    """
    단일 레고 브릭(배치) 정보

    - STEP 01: 보통 1x1 기반 배치가 들어올 수 있음
    - STEP 02: 최적화된 큰 브릭(예: 2x4, 1x5 등)이 width/height로 반영됨

    주의:
    - 이 모델은 '완성본 placements'에도 쓰고,
      STEP 02의 'delta(이번 단계 추가분)'에도 그대로 재사용한다.
    """
    # (선택) step/placements 참조용 ID - 없으면 프론트에서 index 기반으로 만들어도 됨
    id: Optional[str] = None

    # (선택) 섹션(서브어셈블리) 구분
    sectionId: Optional[str] = None

    x: int
    y: int
    z: int = 0

    # 색상 정보
    color: str
    hex: str

    # 브릭 규격("2x4" 같은 문자열)
    type: str

    # 브릭 실제 점유 크기 (2D 모자이크)
    width: int = 1
    height: int = 1

    # (선택) BOM/집계용 수량. placements에서는 1이 기본.
    quantity: int = 1


class StepPartSummary(BaseModel):
    """
    STEP 02: "이번 단계에 추가할 부품 목록" (설명서 박스용)
    """
    type: str          # "2x4"
    hex: str           # "#AABBCC"
    color: Optional[str] = None  # "Dark Blue" 같은 표시용
    count: int


class GuideBuildStep(BaseModel):
    """
    STEP 02: 조립 단계 정보 (설명서 스타일)

    핵심 규칙:
    - bricks는 '이번 step에 추가되는 delta'이다.
    - 하이라이트는 bricks를 그대로 강조하면 됨.
    """
    id: str
    sectionId: str
    index: int

    title: str
    description: Optional[str] = None

    # 이번 단계에 새로 추가되는 브릭(= 하이라이트 대상)
    bricks: List[GuideBrick] = Field(default_factory=list)

    # 이번 단계에 필요한 부품 목록(설명서 박스)
    partsSummary: List[StepPartSummary] = Field(default_factory=list)


class PaletteItem(BaseModel):
    """
    팔레트 정보 (STEP 01/02 공통)
    """
    color: str
    name: Optional[str] = None
    count: int
    types: List[str]


class GuideMeta(BaseModel):
    """
    가이드 메타 정보
    """
    width: int
    height: int
    createdAt: str
    source: Optional[Literal["sample", "ai"]] = None

    # STEP 02 확장(선택)
    gridSize: Optional[str] = None
    colorLimit: Optional[int] = None
    brickMode: Optional[str] = None
    optimized: Optional[bool] = None
    sectionMode: Optional[str] = None


class GuideBounds(BaseModel):
    """
    섹션(서브어셈블리) 영역 정보
    """
    x: int
    y: int
    w: int
    h: int


class GuideSection(BaseModel):
    """
    STEP 02: 섹션 정보 (레고 설명서의 '봉투/세션' 느낌)
    """
    id: str
    name: str
    bounds: GuideBounds


class GuideStep(BaseModel):
    """
    (레거시) 조립 단계/영역 정보
    - 과거 구조 호환용. STEP 02에서는 GuideBuildStep(steps)를 권장.
    """
    id: int
    title: str
    description: Optional[str] = None
    bricks: List[GuideBrick] = Field(default_factory=list)


class GuideResponse(BaseModel):
    """
    레고 조립 가이드 전체 응답 구조 (SSOT)

    권장 사용:
    - STEP 01(include_steps=0):
      summary + palette + bricks(+ meta) 중심, steps/sections는 빈 배열 또는 None
    - STEP 02(include_steps=1):
      sections + steps + (최적화된) bricks + palette + summary
    """
    schemaVersion: int = 1

    # step1 - step2 브릿지 토큰
    analysisId: Optional[str] = None

    summary: GuideSummary

    # 레거시(기존 응답 호환). 앞으로 단계적으로 사용 줄이기.
    groups: List[GuideStep] = Field(default_factory=list)

    # 전체 placements(완성본 기준). STEP 02에서는 최적화된 큰 브릭 placements로 채움.
    bricks: List[GuideBrick] = Field(default_factory=list)

    palette: List[PaletteItem] = Field(default_factory=list)

    tips: Optional[List[str]] = None
    meta: Optional[GuideMeta] = None

    # STEP 02 확장 필드
    sections: List[GuideSection] = Field(default_factory=list)
    steps: List[GuideBuildStep] = Field(default_factory=list)

