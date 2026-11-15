from pydantic import BaseModel, ConfigDict, Field, field_validator


class CommentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=1000)

    @field_validator("content", mode="before")
    @classmethod
    def strip_content(cls, value):
        return value.strip() if isinstance(value, str) else value


class Comment(BaseModel):
    id: str
    content: str
    nickname: str
    createdAt: str
    updatedAt: str
    edited: bool
    canEdit: bool


class CommentList(BaseModel):
    items: list[Comment]
    hasMore: bool
    total: int


class CommentMutation(BaseModel):
    comment: Comment
    commentCount: int


class CommentCount(BaseModel):
    commentCount: int


class LikeState(BaseModel):
    likedByMe: bool
    likeCount: int
