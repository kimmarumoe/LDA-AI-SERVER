"""게시글 입력과 공개 응답을 구분해 회원 아이디·비밀번호 노출을 막는다."""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas.guide import GuideResponse, GuideBuildStep


class PostText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=5000)

    @field_validator("title", "description", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class PostInput(PostText):
    workId: str = Field(min_length=1, max_length=64)


class ThumbnailCell(BaseModel):
    x: int
    y: int
    hex: str


class Thumbnail(BaseModel):
    width: int
    height: int
    cells: list[ThumbnailCell]


class PostSummary(BaseModel):
    id: str
    title: str
    description: str
    nickname: str
    createdAt: str
    updatedAt: str
    thumbnail: Thumbnail


class PostList(BaseModel):
    items: list[PostSummary]
    hasMore: bool


class PostDetail(PostSummary):
    analysis: GuideResponse
    steps: list[GuideBuildStep]
    canEdit: bool
