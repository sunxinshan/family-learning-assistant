from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nickname: str
    role: str
    status: str
    created_at: datetime
    last_active_at: datetime | None


class RegisterRequest(BaseModel):
    nickname: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("nickname")
    @classmethod
    def normalize_nickname(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("昵称不能为空")
        return normalized


class LoginRequest(BaseModel):
    nickname: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserPublic


class RefreshRequest(BaseModel):
    refresh_token: str


class UpdateProfileRequest(BaseModel):
    nickname: str = Field(min_length=2, max_length=80)


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)
