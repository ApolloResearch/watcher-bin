"""Find base64 images embedded in text, by the rules the server and every uploader share.

An image can reach a transcript's text two ways: as a ``data:image/...;base64,``
URI, or as a raw base64 payload with no prefix (when an image content block is
stringified into tool-result text). Both are recognized here, so the server's
image elision and the uploaders' tool-output cap agree on what an image is.
"""

from __future__ import annotations

import re
from collections.abc import Callable

__all__ = ["count_images", "is_image_payload", "replace_images"]

# Data-URIs are matched at ANY length — no {200,} floor like the raw-payload regex
# below — because the explicit scheme prefix rules out false positives and even a
# tiny inline icon is an unreadable payload.
_INLINE_DATA_IMAGE_RE = re.compile(r"data:image/([a-zA-Z0-9.+-]+);base64,[A-Za-z0-9+/]+={0,2}")
# Raw base64 image payloads with no ``data:`` prefix, identified by image magic-byte
# base64 prefixes (PNG ``\x89PNG`` -> ``iVBORw0KGgo``, JPEG ``\xff\xd8\xff`` ->
# ``/9j/``, GIF ``GIF8`` -> ``R0lGOD``). The negative lookbehind requires the prefix to
# start a contiguous base64 run, so an interior occurrence inside an unrelated base64
# blob (a cert/JWT that merely contains "/9j/") is not matched. The {200,} floor keeps
# short base64-looking prose (paths, hashes) out of scope.
_RAW_B64_IMAGE_PREFIXES = ("iVBORw0KGgo", "/9j/", "R0lGOD")
_RAW_B64_IMAGE_RE = re.compile(r"(?<![A-Za-z0-9+/])(?:iVBORw0KGgo|/9j/|R0lGOD)[A-Za-z0-9+/]{200,}={0,2}")


# Base64 with nothing else in it: an image's bytes, where text would have spaces or punctuation.
_BASE64_RE = re.compile(r"[A-Za-z0-9+/]*={0,2}")


def is_image_payload(text: str) -> bool:
    """Whether the whole of ``text`` is an image's encoded bytes: a ``data:image`` URI, or bare image base64.

    Bare base64 counts only when it starts with a PNG, JPEG, GIF or WebP
    signature, so audio, a document or a hex dump in the same place is not
    taken for an image. Ask only of a value where image data is expected, to
    tell its bytes from text that sits there.
    """
    if len(text) < 4:
        # Shorter than the shortest signature ("/9j/"), let alone a data URI.
        return False
    if _INLINE_DATA_IMAGE_RE.fullmatch(text) is not None:
        return True
    # WebP is a RIFF file ("UklGR" in base64) with "WEBP" at byte 8, base64 characters 12 to 16.
    signed = text.startswith(_RAW_B64_IMAGE_PREFIXES) or (text.startswith("UklGR") and text[12:16] == "RUJQ")
    return signed and _BASE64_RE.fullmatch(text) is not None


def count_images(text: str, limit: int) -> int:
    """How many images `replace_images` would replace in ``text``, counting no further than ``limit + 1``.

    A data-URI counts once, so a raw payload starting inside one, which
    `replace_images` replaces with the data-URI, is not counted again. Memory
    stays within ``limit + 1`` data-URI spans.
    """
    spans: list[tuple[int, int]] = []
    if "data:image" in text:
        for match in _INLINE_DATA_IMAGE_RE.finditer(text):
            spans.append(match.span())
            if len(spans) > limit:
                return len(spans)
    found = len(spans)
    if not any(prefix in text for prefix in _RAW_B64_IMAGE_PREFIXES):
        return found
    index = 0
    for match in _RAW_B64_IMAGE_RE.finditer(text):
        start = match.start()
        while index < len(spans) and spans[index][1] <= start:
            index += 1
        if index < len(spans) and spans[index][0] <= start:
            continue
        found += 1
        if found > limit:
            return found
    return found


def _raw_image_mime(run: str) -> str:
    """Infer the image type from a raw base64 payload's magic-byte prefix."""
    if run.startswith("iVBORw0KGgo"):
        return "png"
    if run.startswith("/9j/"):
        return "jpeg"
    return "gif"


def replace_images(text: str, replace: Callable[[str, str], str]) -> str:
    """``text`` with each embedded image replaced by ``replace(payload, mime)``, or ``text`` itself when none is.

    Data-URIs are replaced first so a raw-prefix match can never consume part of
    one; the callback therefore runs in payload-kind order (all data-URIs, then
    raw runs), not text order.
    """
    if "data:image" not in text and not any(prefix in text for prefix in _RAW_B64_IMAGE_PREFIXES):
        return text
    matched = False

    def data_uri(match: re.Match[str]) -> str:
        nonlocal matched
        matched = True
        return replace(match.group(0), match.group(1))

    def raw(match: re.Match[str]) -> str:
        nonlocal matched
        matched = True
        return replace(match.group(0), _raw_image_mime(match.group(0)))

    new_text = _RAW_B64_IMAGE_RE.sub(raw, _INLINE_DATA_IMAGE_RE.sub(data_uri, text))
    return new_text if matched else text
