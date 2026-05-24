from __future__ import annotations

from urllib.parse import parse_qs, urlparse


YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
}


def _is_video_id(candidate: str | None) -> bool:
    return bool(candidate) and len(candidate) == 11 and all(
        ch.isalnum() or ch in {"_", "-"} for ch in candidate
    )


def extract_video_id(value: object) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None

    if _is_video_id(raw):
        return raw

    try:
        parsed = urlparse(raw if raw.startswith("http") else f"https://{raw}")
    except ValueError:
        return None

    if parsed.hostname not in YOUTUBE_HOSTS:
        return None

    if parsed.hostname == "youtu.be":
        candidate = parsed.path.strip("/").split("/", 1)[0]
        return candidate if _is_video_id(candidate) else None

    if parsed.path.startswith("/shorts/"):
        candidate = parsed.path.split("/shorts/", 1)[1].split("/", 1)[0]
        return candidate if _is_video_id(candidate) else None

    query = parse_qs(parsed.query)
    candidate = (query.get("v") or [None])[0]
    if _is_video_id(candidate):
        return candidate

    if parsed.path.startswith("/embed/"):
        candidate = parsed.path.split("/embed/", 1)[1].split("/", 1)[0]
        return candidate if _is_video_id(candidate) else None

    return None


def build_short_url(video_id: str) -> str:
    return f"https://www.youtube.com/shorts/{video_id}"
