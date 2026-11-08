"""OWNER: AI/ML. Ephemeris-constrained Gemini image analysis; errors propagate."""
from __future__ import annotations

import io
import json

from PIL import Image

from .explain import _generate_json
from .types import VisionContext, VisionResult


def analyze_photo(image_bytes: bytes, mime_type: str, ctx: VisionContext) -> VisionResult:
    formats = {'image/jpeg': 'JPEG', 'image/png': 'PNG', 'image/webp': 'WEBP'}
    if mime_type not in formats:
        raise ValueError('Unsupported image MIME type')
    if not image_bytes or len(image_bytes) > 15 * 1024 * 1024:
        raise ValueError('Image must be nonempty and at most 15 MB')
    with Image.open(io.BytesIO(image_bytes)) as image:
        if image.format != formats[mime_type]:
            raise ValueError('Image contents do not match MIME type')
        if image.width * image.height > 40_000_000:
            raise ValueError('Image exceeds the 40 megapixel analysis limit')
        image.verify()
    candidates = {c.name.casefold(): c for c in ctx.candidates if c.alt_deg > 0}
    context = ctx.model_dump(mode='json')
    context['candidates'] = [c.model_dump(mode='json') for c in candidates.values()]
    prompt = (
        'Analyze the attached image as a night-sky photograph. Return the requested JSON. '
        'Reject unrelated images with is_night_sky=false. An overcast night sky may still be a night-sky photo. '
        'Above-horizon candidates are possibilities, not proof that an object is pictured. '
        'Camera direction and field of view are unknown; capture metadata may be inaccurate or reflect upload time. '
        'Constellation candidate coordinates are representative anchors, not entire boundaries. '
        'Name objects only when the image itself supplies convincing visual evidence; use exactly the supplied candidate name and type. '
        'Prefer an empty objects list to guessing. Confidence is your assessment, not calibrated probability. '
        'Do not identify an isolated bright point as a particular planet without distinguishing visual evidence. '
        'Describe uncertainty plainly. Do not infer the city causing skyglow, camera settings, or measured Bortle class. '
        'sky_quality is subjective photographic appearance (1-10), not a measured site quality or training label. '
        'Use at most 800 characters for description, 300 for light_pollution_notes, and 15 objects. Context JSON:\n'
        + json.dumps(context, allow_nan=False)
    )
    result = _generate_json(prompt, VisionResult, image_bytes=image_bytes, mime_type=mime_type, timeout_ms=20000)
    if not result.description.strip() or len(result.description) > 800 or len(result.objects) > 15 or len(result.light_pollution_notes or '') > 300:
        raise ValueError('Vision response exceeds supported bounds')
    filtered = []
    seen = set()
    for item in result.objects:
        candidate = candidates.get(item.name.casefold())
        if candidate is None or item.confidence < .75 or candidate.name in seen:
            continue
        seen.add(candidate.name)
        filtered.append(item.model_copy(update={'name': candidate.name, 'type': candidate.type}))
    return result.model_copy(update={'objects': filtered if result.is_night_sky else [],
                                     'milky_way_visible': result.milky_way_visible if result.is_night_sky else False})
