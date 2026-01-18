# app/schemas/steps.py
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

class Placement(BaseModel):
    id: Optional[str] = None
    x: int
    y: int
    w: int = 1
    h: int = 1
    color: str
    type: str

class PartSummaryItem(BaseModel):
    type: str
    color: str
    count: int

class StepBBox(BaseModel):
    minX: int
    minY: int
    maxX: int
    maxY: int

class StepStats(BaseModel):
    placements: int
    studs: int

class StepV2(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    index: int
    section_id: Optional[int] = Field(default=None, alias="sectionId")
    title: str
    description: Optional[str] = None
    placements: List[Placement]

    parts_summary: List[PartSummaryItem] = Field(default_factory=list, alias="partsSummary")
    bbox: Optional[StepBBox] = None
    stats: Optional[StepStats] = None
