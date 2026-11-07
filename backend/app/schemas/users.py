from __future__ import annotations

from uuid import UUID

from pydantic import Field

from .common import ApiModel


class CreateUserRequest(ApiModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.\-]+$")


class CreateUserResponse(ApiModel):
    user_id: UUID
    username: str
    token: str
