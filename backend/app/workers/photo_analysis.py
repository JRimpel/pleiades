"""Background photo analysis (Architecture §7).

Pipeline per photo: download original -> thumbnail (thumbs/{id}.jpg) -> ephemeris candidates
-> Gemini vision -> update row (done | rejected). Up to MAX_ATTEMPTS tries, then 'failed'.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import timedelta
from typing import Any
from uuid import UUID

from ..ai import vision
from ..ai.types import VisionContext
from ..astro import ephemeris
from ..config import Settings, current_settings
from ..repo import photos as photos_repo
from ..storage import s3, thumbnails
from ..timeutil import utcnow

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3  # first try + 2 retries
RETRY_DELAY_S = 2.0  # multiplied by the attempt number
STALE_AFTER = timedelta(minutes=10)

_executor: ThreadPoolExecutor | None = None
_lock = threading.Lock()


def _get_executor(workers: int | None = None) -> ThreadPoolExecutor:
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=workers or current_settings().photo_workers, thread_name_prefix="photo-ai"
            )
        return _executor


def init_worker(settings: Settings) -> None:
    """Create the executor and requeue photos whose analysis was abandoned. Never raises."""
    _get_executor(settings.photo_workers)
    try:
        stale = photos_repo.claim_stale_pending(utcnow() - STALE_AFTER)
    except Exception as e:  # noqa: BLE001 - boot must not fail because of the DB
        log.warning("Could not requeue pending photos: %s", e)
        return
    for photo_id in stale:
        submit(photo_id)
    if stale:
        log.info("Requeued %d pending photo(s)", len(stale))


def submit(photo_id: UUID) -> Future:
    return _get_executor().submit(_run, photo_id)


def shutdown(wait: bool = True) -> None:
    global _executor
    with _lock:
        if _executor is not None:
            _executor.shutdown(wait=wait)
            _executor = None


def _run(photo_id: UUID) -> str | None:
    try:
        return process_photo(photo_id)
    except Exception:  # noqa: BLE001 - never let a worker thread die silently
        log.exception("Photo %s: unexpected error", photo_id)
        return None


def _analyze_once(photo: dict[str, Any]) -> str:
    photo_id = photo["id"]
    original = s3.get_object_bytes(photo["s3_key"])

    if not photo.get("thumb_key"):
        thumb_key = f"thumbs/{photo_id}.jpg"
        s3.put_object(thumb_key, thumbnails.make_thumbnail(original), "image/jpeg")
        photos_repo.set_thumb(photo_id, thumb_key)
        photo["thumb_key"] = thumb_key

    when = photo.get("taken_at") or photo["uploaded_at"]
    candidates = ephemeris.visible_objects(photo["lat"], photo["lon"], when)
    ctx = VisionContext(lat=photo["lat"], lon=photo["lon"], taken_at=when, candidates=candidates,
                        caption=photo.get("caption"))
    result = vision.analyze_photo(original, photo.get("mime_type") or "image/jpeg", ctx)

    status = "done" if result.is_night_sky else "rejected"
    photos_repo.update_ai_result(
        photo_id,
        status=status,
        description=result.description,
        objects=[o.model_dump() for o in result.objects],
        sky_quality=result.sky_quality,
        milky_way_visible=result.milky_way_visible,
        light_pollution_notes=result.light_pollution_notes,
    )
    return status


def process_photo(photo_id: UUID) -> str | None:
    """Analyze one photo. Returns the final ai_status, or None if there was nothing to do."""
    photo = photos_repo.get_for_processing(photo_id)
    if photo is None or photo["ai_status"] != "pending":
        return None

    last_error: Exception | None = None
    attempts = int(photo.get("ai_attempts") or 0)
    while attempts < MAX_ATTEMPTS:
        attempts = photos_repo.increment_attempts(photo_id)
        try:
            status = _analyze_once(photo)
            log.info("Photo %s analyzed: %s", photo_id, status)
            return status
        except Exception as e:  # noqa: BLE001 - retried, then recorded
            last_error = e
            log.warning("Photo %s attempt %d failed: %s", photo_id, attempts, e)
            if attempts < MAX_ATTEMPTS and RETRY_DELAY_S > 0:
                time.sleep(RETRY_DELAY_S * attempts)

    photos_repo.mark_failed(photo_id, f"{type(last_error).__name__}: {last_error}" if last_error else "max attempts")
    return "failed"
