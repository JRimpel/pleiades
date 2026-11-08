from __future__ import annotations

import logging
import re
import uuid
from datetime import timedelta
from uuid import UUID

from flask import Blueprint, g, request

from ..auth import optional_user, require_auth
from ..config import current_settings
from ..errors import ApiError, bad_request, not_found
from ..geo import parse_bbox
from ..repo import cells as cells_repo
from ..repo import photos as photos_repo
from ..repo import scores as scores_repo
from ..repo import votes as votes_repo
from ..schemas.photos import (CreatePhotoRequest, CreatePhotoResponse, PhotoDetail, PhotoListResponse, PhotoMarker,
                              PresignRequest, PresignResponse, VoteRequest, VoteResponse)
from ..storage import s3
from ..timeutil import floor_hour, utcnow
from ..workers import photo_analysis
from .params import body, int_arg

log = logging.getLogger(__name__)

bp = Blueprint("photos", __name__)

S3_KEY_RE = re.compile(r"^photos/([0-9a-f-]{36})\.(jpg|png|webp)$")
EXT_MIME = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
MAX_FUTURE_SKEW = timedelta(hours=1)


def _storage_unavailable() -> ApiError:
    return ApiError(503, "storage_unavailable", "Photo storage is not configured")


@bp.post("/photos/presign")
@require_auth
def presign():
    settings = current_settings()
    req = PresignRequest.model_validate(body())
    content_type = req.content_type.strip().lower()
    ext = settings.allowed_mime_types.get(content_type)
    if ext is None:
        raise ApiError(415, "unsupported_media_type",
                       f"content_type must be one of: {', '.join(settings.allowed_mime_types)}")
    if req.size > settings.max_upload_bytes:
        raise ApiError(413, "file_too_large", f"Photos must be at most {settings.max_upload_bytes} bytes")
    if not settings.s3_configured:
        raise _storage_unavailable()

    key = f"photos/{uuid.uuid4()}.{ext}"
    url, headers = s3.presign_put(key, content_type, req.size)
    resp = PresignResponse(upload_url=url, s3_key=key, headers=headers, expires_in=s3.PRESIGN_PUT_EXPIRES)
    return resp.model_dump(mode="json")


@bp.post("/photos")
@require_auth
def create_photo():
    settings = current_settings()
    req = CreatePhotoRequest.model_validate(body())
    user_id = g.user["id"]
    now = utcnow()

    if photos_repo.count_recent_uploads(user_id, now - timedelta(hours=1)) >= settings.uploads_per_hour:
        raise ApiError(429, "rate_limited", f"Upload limit is {settings.uploads_per_hour} photos per hour")

    m = S3_KEY_RE.match(req.s3_key)
    if not m:
        raise bad_request("Invalid s3_key; use the key returned by /api/photos/presign")
    if not settings.s3_configured:
        raise _storage_unavailable()
    head = s3.head_object(req.s3_key)
    if head is None:
        raise ApiError(400, "upload_not_found", "No uploaded object found for s3_key")
    if head["size"] > settings.max_upload_bytes:
        raise ApiError(413, "file_too_large", f"Photos must be at most {settings.max_upload_bytes} bytes")

    taken_at = req.taken_at
    if taken_at is not None:
        taken_at = taken_at if taken_at.tzinfo else taken_at.replace(tzinfo=now.tzinfo)
        if taken_at > now + MAX_FUTURE_SKEW:
            raise bad_request("taken_at is in the future")
    taken_at_source = (req.taken_at_source or "exif") if taken_at else "upload_time"

    cell_id = cells_repo.nearest_cell(req.lat, req.lon)
    score_at_capture = None
    if taken_at is not None and cell_id is not None:
        score = scores_repo.score_for(cell_id, floor_hour(taken_at))
        score_at_capture = score["score"] if score else None

    photo_id = UUID(m.group(1))
    try:
        photos_repo.insert(
            photo_id=photo_id, user_id=user_id, s3_key=req.s3_key,
            mime_type=head.get("content_type") or EXT_MIME[m.group(2)],
            lat=req.lat, lon=req.lon, cell_id=cell_id, taken_at=taken_at, taken_at_source=taken_at_source,
            caption=req.caption, score_at_capture=score_at_capture,
        )
    except photos_repo.PhotoExists as e:
        raise ApiError(409, "photo_exists", "This upload was already registered") from e

    photo_analysis.submit(photo_id)
    return CreatePhotoResponse(id=photo_id, ai_status="pending").model_dump(mode="json"), 201


@bp.get("/photos")
def list_photos():
    bbox = parse_bbox(request.args.get("bbox"))
    sort = request.args.get("sort", "recent")
    if sort not in ("top", "recent"):
        raise bad_request("sort must be 'top' or 'recent'")
    limit = int_arg("limit", 200, 1, 500)
    markers = [
        PhotoMarker(
            id=r["id"], lat=r["lat"], lon=r["lon"], thumb_url=s3.object_url(r["thumb_key"]),
            vote_count=r["vote_count"], taken_at=r["taken_at"], ai_status=r["ai_status"],
            ai_sky_quality=r["ai_sky_quality"],
        )
        for r in photos_repo.list_markers(bbox, sort, limit)
    ]
    return PhotoListResponse(photos=markers).model_dump(mode="json")


@bp.post("/photos/wipe")
def wipe_photos():
    """Demo reset: delete every photo, its votes, and its stored files. Deliberately unauthenticated."""
    rows = photos_repo.delete_all()
    keys = [k for r in rows for k in (r.get("s3_key"), r.get("thumb_key")) if k]
    if keys and current_settings().s3_configured:
        try:
            s3.delete_objects(keys)
        except Exception as e:  # noqa: BLE001 - rows are already gone; leftover files are harmless
            log.warning("wipe: could not delete %d stored objects: %s", len(keys), e)
    return {"deleted": len(rows)}


@bp.get("/photos/<uuid:photo_id>")
def get_photo(photo_id: UUID):
    p = photos_repo.get_detail(photo_id)
    if p is None:
        raise not_found("Photo not found")
    user = optional_user()
    my_vote = votes_repo.get_my_vote(user["id"], photo_id) if user else None
    detail = PhotoDetail(
        id=p["id"], username=p["username"], url=s3.object_url(p["s3_key"]), thumb_url=s3.object_url(p["thumb_key"]),
        lat=p["lat"], lon=p["lon"], cell_id=p["cell_id"], taken_at=p["taken_at"],
        taken_at_source=p["taken_at_source"], uploaded_at=p["uploaded_at"], caption=p["caption"],
        score_at_capture=p["score_at_capture"], ai_status=p["ai_status"], ai_description=p["ai_description"],
        ai_objects=p["ai_objects"], ai_sky_quality=p["ai_sky_quality"],
        ai_milky_way_visible=p["ai_milky_way_visible"], ai_light_pollution_notes=p["ai_light_pollution_notes"],
        vote_count=p["vote_count"], my_vote=my_vote,
    )
    return detail.model_dump(mode="json")


@bp.post("/photos/<uuid:photo_id>/vote")
@require_auth
def vote(photo_id: UUID):
    req = VoteRequest.model_validate(body())
    count = votes_repo.set_vote(g.user["id"], photo_id, req.value)
    if count is None:
        raise not_found("Photo not found")
    return VoteResponse(photo_id=photo_id, vote_count=count, my_vote=req.value).model_dump(mode="json")
