"""Vultr Object Storage via boto3 (S3-compatible API).

The client is built lazily from current settings so the app boots without credentials.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError

from ..config import Settings, current_settings

log = logging.getLogger(__name__)

_clients: dict[tuple[str, str, str, str], BaseClient] = {}
_lock = threading.Lock()

PRESIGN_PUT_EXPIRES = 900
PRESIGN_GET_EXPIRES = 3600


class StorageNotConfigured(RuntimeError):
    pass


def _settings() -> Settings:
    return current_settings()


def client() -> BaseClient:
    s = _settings()
    if not s.s3_configured:
        raise StorageNotConfigured("Vultr S3 credentials are not configured")
    cache_key = (s.s3_endpoint, s.s3_region, s.s3_access_key, s.s3_secret_key)
    with _lock:
        c = _clients.get(cache_key)
        if c is None:
            c = boto3.client(
                "s3",
                endpoint_url=s.s3_endpoint,
                region_name=s.s3_region,
                aws_access_key_id=s.s3_access_key,
                aws_secret_access_key=s.s3_secret_key,
                config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                              connect_timeout=5, read_timeout=30, retries={"max_attempts": 3}),
            )
            _clients[cache_key] = c
        return c


def reset_client() -> None:
    """Drop cached clients (tests)."""
    with _lock:
        _clients.clear()


def presign_put(key: str, content_type: str, content_length: int,
                expires: int = PRESIGN_PUT_EXPIRES) -> tuple[str, dict[str, str]]:
    """Presigned PUT URL. Returns (url, headers the browser must send with the PUT)."""
    url = client().generate_presigned_url(
        "put_object",
        Params={"Bucket": _settings().s3_bucket, "Key": key,
                "ContentType": content_type, "ContentLength": content_length},
        ExpiresIn=expires,
        HttpMethod="PUT",
    )
    return url, {"Content-Type": content_type}


def object_url(key: str | None) -> str | None:
    """Public URL (public-read bucket) or a 1 h presigned GET. None if no key or storage unconfigured."""
    if not key:
        return None
    s = _settings()
    if s.s3_public_base:
        return f"{s.s3_public_base}/{key}"
    if not s.s3_configured:
        return None
    return client().generate_presigned_url(
        "get_object", Params={"Bucket": s.s3_bucket, "Key": key}, ExpiresIn=PRESIGN_GET_EXPIRES
    )


def head_object(key: str) -> dict[str, Any] | None:
    """{size, content_type} or None if the object does not exist."""
    try:
        resp = client().head_object(Bucket=_settings().s3_bucket, Key=key)
    except ClientError as e:
        code = str(e.response.get("Error", {}).get("Code", ""))
        status = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in ("404", "NoSuchKey", "NotFound") or status == 404:
            return None
        raise
    return {"size": int(resp.get("ContentLength", 0)), "content_type": resp.get("ContentType")}


def get_object_bytes(key: str) -> bytes:
    resp = client().get_object(Bucket=_settings().s3_bucket, Key=key)
    return resp["Body"].read()


def put_object(key: str, data: bytes, content_type: str) -> None:
    client().put_object(Bucket=_settings().s3_bucket, Key=key, Body=data, ContentType=content_type)


def bucket_reachable() -> bool:
    """True if the bucket answers a HEAD request. Never raises."""
    try:
        client().head_bucket(Bucket=_settings().s3_bucket)
        return True
    except Exception as e:  # noqa: BLE001 - health check
        log.debug("bucket not reachable: %s", e)
        return False
