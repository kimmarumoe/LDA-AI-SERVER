"""저장 시점의 완성 가이드를 검증한다. 임시 analysisId에는 의존하지 않는다."""
import json
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.schemas.guide import GuideResponse, GuideBuildStep


class WorkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=80)
    analysis: GuideResponse
    steps: list[GuideBuildStep] = Field(min_length=1, max_length=16384)
    options: dict = Field(default_factory=dict)

    @field_validator("title", mode="before")
    @classmethod
    def clean_title(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def complete_guide(self):
        if not self.analysis.bricks or not self.analysis.meta:
            raise ValueError("분석 결과와 조립 가이드가 필요합니다.")
        if not all(step.bricks for step in self.steps):
            raise ValueError("빈 조립 단계는 저장할 수 없습니다.")
        if len(json.dumps(self.model_dump(), ensure_ascii=False).encode()) > 12 * 1024 * 1024:
            raise ValueError("저장할 작품 데이터가 너무 큽니다.")
        return self


class WorkSummary(BaseModel):
    id: str
    title: str
    createdAt: str


class WorkDetail(WorkSummary):
    analysis: GuideResponse
    steps: list[GuideBuildStep]
    options: dict
