# ai-server/app/models/guide.py
from pydantic import BaseModel
from typing import List, Optional, Literal
from datetime import datetime

class Brick(BaseModel):
    x: int
    y: int
    z: int = 0
    color: str
    type: str
    groupId: Optional[int] = None

class GuideSummary(BaseModel):
    totalBricks: int
    uniqueTypes: int
    difficulty: Literal["초급", "중급", "고급"]
    estimatedTime: str

class GuideStep(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    bricks: List[Brick]

class PaletteItem(BaseModel):
    color: str
    name: Optional[str] = None
    count: int
    types: List[str]

class GuideMeta(BaseModel):
    width: int
    height: int
    createdAt: datetime
    source: Optional[Literal["sample", "ai"]] = "ai"

class GuideResponse(BaseModel):
    summary: GuideSummary
    groups: List[GuideStep]
    palette: List[PaletteItem]
    meta: Optional[GuideMeta] = None

class GuideOptions(BaseModel):
    targetWidth: Optional[int] = None
    targetHeight: Optional[int] = None
    maxBricks: Optional[int] = None
    colorPalette: Optional[list[str]] = None
