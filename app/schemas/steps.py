# app/schemas/steps.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class Placement(BaseModel):
    id: Optional[str] = None
    x: int
    y: int
    w: int = 1
    h: int = 1
    color: str
    type: str


class StepsRequest(BaseModel):
    placements: List[Placement]
    meta: Optional[Dict[str, Any]] = None
    rows_per_step: int = Field(2, ge=1, le=16)
    max_placements_per_step: int = Field(256, ge=16, le=2000)


class StepV2(BaseModel):
    index: int
    title: str
    description: Optional[str] = None
    placements: List[Placement]
