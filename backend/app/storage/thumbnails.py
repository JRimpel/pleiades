"""Thumbnail generation with Pillow."""
from __future__ import annotations

import io

from PIL import Image, ImageOps


def make_thumbnail(data: bytes, max_px: int = 512, quality: int = 82) -> bytes:
    """JPEG thumbnail whose longest side is at most `max_px`, with EXIF orientation applied."""
    with Image.open(io.BytesIO(data)) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=quality, optimize=True, progressive=True)
    return out.getvalue()
