# ai-server/app/schemas/guide.py

from typing import List, Optional
from pydantic import BaseModel
from typing_extensions import Literal


class GuideSummary(BaseModel):
    """
    레고 가이드 상단 요약 정보
    """
    totalBricks: int
    uniqueTypes: int
    difficulty: Literal["초급", "중급", "고급"]
    estimatedTime: str


class GuideBrick(BaseModel):
    """
    단일 레고 브릭 정보
    """
    x: int
    y: int
    z: int = 0
    color: str
    hex: str
    type: str
    width: int = 1
    height: int = 1
    quantity: int = 1


class GuideStep(BaseModel):
    """
    조립 단계/영역 정보
    """
    id: int
    title: str
    description: Optional[str] = None
    bricks: List[GuideBrick]


class PaletteItem(BaseModel):
    """
    팔레트 정보
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


class GuideResponse(BaseModel):
    """
    레고 조립 가이드 전체 응답 구조
    """
    summary: GuideSummary
    groups: List[GuideStep]
    bricks: List[GuideBrick]
    palette: List[PaletteItem]
    tips: Optional[List[str]] = None
    meta: Optional[GuideMeta] = None
