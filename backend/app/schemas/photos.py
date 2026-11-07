from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from .common import ApiModel

AiStatus = Literal["pending", "done", "failed", "rejected"]
TakenAtSource = Literal["exif", "user", "upload_time"]


class PresignRequest(ApiModel):
    content_type: str
    size: int = Field(gt=0)


class PresignResponse(ApiModel):
    upload_url: str
    s3_key: str
    method: Literal["PUT"] = "PUT"
    # Headers the browser MUST send with the PUT (they are part of the signature).
    headers: dict[str, str]
    expires_in: int


class CreatePhotoRequest(ApiModel):
    s3_key: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    taken_at: datetime | None = None
    taken_at_source: Literal["exif", "user"] | None = None  # defaults to 'exif' when taken_at is given
    caption: str | None = Field(default=None, max_length=500)


class CreatePhotoResponse(ApiModel):
    id: UUID
    ai_status: AiStatus


class PhotoMarker(ApiModel):
    id: UUID
    lat: float
    lon: float
    thumb_url: str | None
    vote_count: int
    taken_at: datetime | None
    ai_status: AiStatus
    ai_sky_quality: int | None = None


class PhotoListResponse(ApiModel):
    photos: list[PhotoMarker]


class AiObject(ApiModel):
    name: str
    type: str
    confidence: float


class PhotoDetail(ApiModel):
    id: UUID
    username: str
    url: str | None
    thumb_url: str | None
    lat: float
    lon: float
    cell_id: int | None
    taken_at: datetime | None
    taken_at_source: TakenAtSource | None
    uploaded_at: datetime
    caption: str | None
    score_at_capture: float | None
    ai_status: AiStatus
    ai_description: str | None
    ai_objects: list[AiObject] | None
    ai_sky_quality: int | None
    ai_milky_way_visible: bool | None
    ai_light_pollution_notes: str | None
    vote_count: int
    my_vote: Literal[-1, 0, 1] | None = None  # only set when the request carries a valid token


class VoteRequest(ApiModel):
    value: Literal[-1, 0, 1]


class VoteResponse(ApiModel):
    photo_id: UUID
    vote_count: int
    my_vote: Literal[-1, 0, 1]
