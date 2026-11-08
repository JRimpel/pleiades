from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from .common import ApiModel, ScoreLabel

MAX_TURNS = 12
MAX_MESSAGE_CHARS = 1000


class ChatMessage(ApiModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class LatLon(ApiModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Viewport(ApiModel):
    west: float = Field(ge=-180, le=180)
    south: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)

    @model_validator(mode="after")
    def _ordered(self) -> "Viewport":
        if self.west >= self.east or self.south >= self.north:
            raise ValueError("viewport must satisfy west < east and south < north")
        return self


class ChatContext(ApiModel):
    """What the user is looking at in the app. Every field is optional."""

    location: LatLon | None = None
    time: datetime | None = None  # the hour on the time slider
    selected_cell_id: int | None = None  # the spot open in the details panel
    viewport: Viewport | None = None


class ChatRequest(ApiModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=MAX_TURNS)
    context: ChatContext = Field(default_factory=ChatContext)

    @model_validator(mode="after")
    def _ends_with_user(self) -> "ChatRequest":
        if self.messages[-1].role != "user":
            raise ValueError("the last message must come from the user")
        return self


class ToolCall(ApiModel):
    name: str
    args: dict[str, Any]


class ChatSpot(ApiModel):
    cell_id: int
    name: str | None
    lat: float
    lon: float
    score: float | None = None
    label: ScoreLabel | None = None
    valid_time: datetime | None = None


class ChatPhoto(ApiModel):
    id: UUID
    lat: float
    lon: float
    thumb_url: str | None
    taken_at: datetime | None
    description: str | None
    objects: list[str]


class ChatResponse(ApiModel):
    reply: str
    tool_calls: list[ToolCall]
    spots: list[ChatSpot]
    photos: list[ChatPhoto]
