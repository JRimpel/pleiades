from __future__ import annotations

import io
from urllib.parse import parse_qs, urlparse

import pytest
from moto import mock_aws
from PIL import Image

from app.storage import s3, thumbnails


@pytest.fixture
def bucket(app):
    with mock_aws():
        s3.reset_client()
        with app.app_context():
            s3.client().create_bucket(Bucket=app.config["SETTINGS"].s3_bucket)
            yield app
        s3.reset_client()


def _jpeg(w=1600, h=900, color=(10, 10, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="JPEG")
    return buf.getvalue()


def test_presign_put_signs_content_type(bucket):
    url, headers = s3.presign_put("photos/x.jpg", "image/jpeg", 1234)
    q = parse_qs(urlparse(url).query)
    assert urlparse(url).path.endswith("/pleiades-test/photos/x.jpg")  # path-style addressing
    assert q["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert "content-type" in q["X-Amz-SignedHeaders"][0]
    assert q["X-Amz-Expires"] == [str(s3.PRESIGN_PUT_EXPIRES)]
    assert headers == {"Content-Type": "image/jpeg"}


def test_put_head_get_roundtrip(bucket):
    data = _jpeg()
    assert s3.head_object("photos/missing.jpg") is None
    s3.put_object("photos/a.jpg", data, "image/jpeg")
    assert s3.head_object("photos/a.jpg") == {"size": len(data), "content_type": "image/jpeg"}
    assert s3.get_object_bytes("photos/a.jpg") == data


def test_bucket_reachable(bucket, app):
    assert s3.bucket_reachable() is True


def test_bucket_unreachable_never_raises(app):
    with app.app_context():
        app.config["SETTINGS"] = app.config["SETTINGS"].__class__()  # unconfigured
        assert s3.bucket_reachable() is False


def test_object_url_presigned_and_public(bucket, app):
    url = s3.object_url("thumbs/a.jpg")
    assert "X-Amz-Signature" in url and "/thumbs/a.jpg" in url
    assert s3.object_url(None) is None
    from dataclasses import replace

    app.config["SETTINGS"] = replace(app.config["SETTINGS"], s3_public_base="https://cdn.example")
    assert s3.object_url("thumbs/a.jpg") == "https://cdn.example/thumbs/a.jpg"


def test_object_url_unconfigured(app):
    with app.app_context():
        app.config["SETTINGS"] = app.config["SETTINGS"].__class__()
        assert s3.object_url("thumbs/a.jpg") is None


def test_thumbnail_resizes_and_converts():
    thumb = thumbnails.make_thumbnail(_jpeg(1600, 900))
    with Image.open(io.BytesIO(thumb)) as img:
        assert img.format == "JPEG" and max(img.size) == 512 and img.size == (512, 288)

    buf = io.BytesIO()
    Image.new("RGBA", (300, 200), (0, 0, 0, 128)).save(buf, format="PNG")
    with Image.open(io.BytesIO(thumbnails.make_thumbnail(buf.getvalue()))) as img:
        assert img.mode == "RGB" and img.size == (300, 200)  # never upscales


def test_thumbnail_applies_exif_orientation():
    img = Image.new("RGB", (400, 200), (0, 0, 0))
    exif = img.getexif()
    exif[0x0112] = 6  # rotate 90° CW on display
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    with Image.open(io.BytesIO(thumbnails.make_thumbnail(buf.getvalue()))) as out:
        assert out.size == (200, 400)
