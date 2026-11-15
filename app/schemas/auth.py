from pydantic import BaseModel, Field, ConfigDict


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=24, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)


class RegisterInput(LoginInput):
    # 신규 가입만 제한하여 기존의 긴 비밀번호로도 로그인할 수 있게 한다.
    password: str = Field(min_length=8, max_length=20)
    nickname: str = Field(min_length=1, max_length=30, pattern=r".*\S.*")


class Member(BaseModel):
    id: int
    username: str
    nickname: str


class NicknameInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nickname: str = Field(min_length=1, max_length=30, pattern=r".*\S.*")


class PasswordInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    currentPassword: str = Field(min_length=8, max_length=128)
    newPassword: str = Field(min_length=8, max_length=20)
