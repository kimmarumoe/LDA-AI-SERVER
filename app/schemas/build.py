# ai-server/app/schemas/build.py
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from typing_extensions import Literal

from app.schemas.guide import GuideSection, GuideBuildStep, GuideBrick


class BuildStepsRequest(BaseModel):
    """
    STEP 02: analysisId 기반 조립 가이드 생성 요청

    - STEP1에서 받은 analysisId를 이용해 서버에 저장된 분석 결과를 재사용한다.
    - 이미지 파일을 다시 업로드하지 않는다(Method B).
    """

    analysisId: str = Field(..., min_length=8)

    # STEP2에서 사용할 브릭 타입(없으면 서버 기본 정책 사용)
    brickTypes: Optional[List[str]] = None

    # 섹션(서브어셈블리) 분할 정책
    sectionMode: Literal["single", "rows", "quadrants"] = "rows"
    rowsPerSection: int = Field(16, ge=1, le=96)

    # 스텝 분할 정책
    rowsPerStep: int = Field(2, ge=1, le=16)
    maxPlacementsPerStep: int = Field(256, ge=16, le=5000)

    # 큰 브릭 패킹(최적화) 여부
    optimize: bool = True

    # (선택) 추후 확장용 메타(클라이언트 버전/옵션 등)
    meta: Optional[Dict[str, Any]] = None


class BuildStepsResponse(BaseModel):
    """
    STEP 02: 섹션/스텝 생성 결과

    - steps[].bricks = 이번 스텝에 추가되는 delta(= 하이라이트 대상)
    - 필요하면 bricks(전체 placements)를 함께 내려서, 전체 BOM/렌더 재사용도 가능
    """

    analysisId: str

    sections: List[GuideSection] = Field(default_factory=list)
    steps: List[GuideBuildStep] = Field(default_factory=list)

    # (선택) 전체 placements(완성본)도 내려주고 싶으면 사용
    bricks: List[GuideBrick] = Field(default_factory=list)

    meta: Optional[Dict[str, Any]] = None
