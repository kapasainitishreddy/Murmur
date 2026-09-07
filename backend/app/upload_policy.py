from __future__ import annotations

from typing import Optional

AUDIO_SUFFIXES = {
    'audio/webm': '.webm',
    'audio/ogg': '.ogg',
    'audio/wav': '.wav',
    'audio/x-wav': '.wav',
    'audio/mpeg': '.mp3',
    'audio/mp4': '.m4a',
    'audio/aac': '.aac',
}


class AudioUploadError(ValueError):
    """Raised when an uploaded file is not an accepted audio type."""


def validate_audio_upload(content_type: Optional[str]) -> str:
    normalized = (content_type or '').split(';', 1)[0].strip().lower()
    if normalized not in AUDIO_SUFFIXES:
        raise AudioUploadError(f'Unsupported audio type: {content_type or "missing"}')
    return normalized


def choose_audio_suffix(content_type: str, filename: Optional[str] = None) -> str:
    del filename  # Never trust a browser-supplied name for filesystem semantics.
    normalized = validate_audio_upload(content_type)
    return AUDIO_SUFFIXES[normalized]
