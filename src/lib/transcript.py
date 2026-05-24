from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from src.lib.http import request
from src.lib.text import clean_transcript_text, decode_html_entities, normalize_whitespace


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _lazy_import_youtube_transcript_api():
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        return YouTubeTranscriptApi
    except ImportError:
        return None


def _lazy_import_ytdlp():
    try:
        import yt_dlp

        return yt_dlp
    except ImportError:
        return None


def _lazy_import_openai_client():
    try:
        from openai import OpenAI

        return OpenAI
    except ImportError:
        return None


def _find_balanced_fragment(
    text: str,
    start_index: int,
    open_char: str,
    close_char: str,
) -> str | None:
    depth = 0
    in_string = False
    escape = False

    for index in range(start_index, len(text)):
        char = text[index]

        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return text[start_index : index + 1]

    return None


def _ensure_json3(url: str) -> str:
    parsed = urlparse(url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params.setdefault("fmt", "json3")
    return urlunparse(parsed._replace(query=urlencode(params)))


def _extract_json_fragment(text: str, marker: str, open_char: str, close_char: str):
    marker_index = text.find(marker)
    if marker_index == -1:
        return None

    fragment_start = text.find(open_char, marker_index)
    if fragment_start == -1:
        return None

    fragment = _find_balanced_fragment(text, fragment_start, open_char, close_char)
    if not fragment:
        return None

    return json.loads(fragment)


def _extract_title(html: str) -> str | None:
    match = re.search(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return decode_html_entities(re.sub(r"\s*-\s*YouTube\s*$", "", match.group(1)))


def _extract_caption_tracks(html: str) -> list[dict]:
    for marker in ('"captionTracks":',):
        try:
            fragment = _extract_json_fragment(html, marker, "[", "]")
            if isinstance(fragment, list):
                return fragment
        except (json.JSONDecodeError, TypeError):
            continue

    return []


def _choose_caption_track(tracks: list[dict]) -> dict | None:
    available = [track for track in tracks if track and track.get("baseUrl")]
    if not available:
        return None

    def sort_key(track: dict):
        language = str(track.get("languageCode") or "").lower()
        english = 0 if language.startswith("en") else 1
        auto = 1 if track.get("kind") == "asr" else 0
        return (english, auto)

    return sorted(available, key=sort_key)[0]


def _decode_xml_text(value: object) -> str:
    return decode_html_entities(re.sub(r"<[^>]+>", "", str(value or "")))


def _fetch_json_or_xml(url: str):
    response = request(
        "GET",
        url,
        headers={
            "user-agent": USER_AGENT,
            "accept": "application/json, text/xml, application/xml, text/plain, */*",
        },
    )
    if response.status >= 400:
        raise RuntimeError(f"Transcript request failed ({response.status})")

    content_type = response.headers.get("content-type", "")
    text = response.text
    stripped = text.strip()

    if "json" in content_type or stripped.startswith("{") or stripped.startswith("["):
        return json.loads(stripped)

    return text


def _extract_transcript_entries(payload) -> list[dict]:
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        entries: list[dict] = []
        for event in payload["events"]:
            text = normalize_whitespace(
                "".join((segment.get("utf8") or "") for segment in event.get("segs", []))
            )
            if not text:
                continue
            entries.append(
                {
                    "start": float(event.get("tStartMs") or 0) / 1000.0,
                    "duration": float(event.get("dDurationMs") or 0) / 1000.0,
                    "text": text,
                }
            )
        return entries

    if (
        isinstance(payload, dict)
        and isinstance(payload.get("transcript"), dict)
        and isinstance(payload["transcript"].get("body"), dict)
        and isinstance(payload["transcript"]["body"].get("transcriptSegments"), list)
    ):
        entries: list[dict] = []
        for segment in payload["transcript"]["body"]["transcriptSegments"]:
            text = normalize_whitespace(segment.get("utf8") or "")
            if not text:
                continue
            entries.append(
                {
                    "start": float(segment.get("tStartMs") or 0) / 1000.0,
                    "duration": float(segment.get("dDurationMs") or 0) / 1000.0,
                    "text": text,
                }
            )
        return entries

    if isinstance(payload, str):
        matches = re.findall(r"<text[^>]*>([\s\S]*?)</text>", payload)
        entries: list[dict] = []
        for match in matches:
            text = normalize_whitespace(_decode_xml_text(match))
            if text:
                entries.append({"start": 0, "duration": 0, "text": text})
        return entries

    return []


def fetch_youtube_metadata(video_id: str) -> dict:
    response = request(
        "GET",
        f"https://www.youtube.com/watch?v={video_id}&hl=en&gl=US",
        headers={"user-agent": USER_AGENT},
    )
    if response.status >= 400:
        raise RuntimeError(f"YouTube page request failed ({response.status})")

    html = response.text
    return {
        "title": _extract_title(html),
        "caption_tracks": _extract_caption_tracks(html),
    }


def _fetch_with_youtube_transcript_api(video_id: str, preferred_languages: list[str] | None):
    transcript_api_cls = _lazy_import_youtube_transcript_api()
    if transcript_api_cls is None:
        return None

    try:
        ytt_api = transcript_api_cls()
        fetched = ytt_api.fetch(video_id, languages=preferred_languages or ["en"])
        entries = [
            {
                "start": float(item.start or 0),
                "duration": float(item.duration or 0),
                "text": normalize_whitespace(item.text),
            }
            for item in fetched
            if normalize_whitespace(item.text)
        ]
        transcript_text = clean_transcript_text(" ".join(item["text"] for item in entries))
        if not transcript_text:
            raise RuntimeError("Transcript was empty")
        title = None
        try:
            title = fetch_youtube_metadata(video_id)["title"]
        except Exception:
            title = None
        return {
            "title": title,
            "entries": entries,
            "transcript_text": transcript_text,
            "source": "youtube_transcript_api",
        }
    except Exception:  # noqa: BLE001
        return None


def _download_audio_with_ytdlp(youtube_url: str) -> tuple[str, str | None]:
    yt_dlp = _lazy_import_ytdlp()
    if yt_dlp is None:
        raise RuntimeError("yt-dlp is not installed")

    with tempfile.TemporaryDirectory(prefix="short2english-audio-") as tmpdir:
        output_template = str(Path(tmpdir) / "audio.%(ext)s")
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "quiet": True,
            "noplaylist": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=True)
            title = info.get("title")

        audio_candidates = sorted(Path(tmpdir).glob("audio.*"))
        if not audio_candidates:
            raise RuntimeError("Failed to download audio for transcription")

        audio_path = audio_candidates[0]
        fd, final_path = tempfile.mkstemp(prefix="short2english-audio-", suffix=audio_path.suffix)
        os.close(fd)
        shutil.copyfile(audio_path, final_path)
        return final_path, title


def _transcribe_audio_with_openai(
    *,
    audio_path: str,
    api_key: str,
    model: str,
) -> str:
    openai_cls = _lazy_import_openai_client()
    if openai_cls is None:
        raise RuntimeError("openai is not installed")

    client = openai_cls(api_key=api_key)
    with open(audio_path, "rb") as audio_file:
        result = client.audio.transcriptions.create(
            model=model,
            file=audio_file,
            language="en",
        )

    text = getattr(result, "text", "") or ""
    text = clean_transcript_text(text)
    if not text:
        raise RuntimeError("OpenAI transcription returned empty text")
    return text


def _fetch_with_audio_fallback(
    *,
    youtube_url: str | None,
    openai_api_key: str | None,
    transcription_model: str,
):
    if not youtube_url or not openai_api_key:
        return None

    try:
        audio_path, title = _download_audio_with_ytdlp(youtube_url)
        try:
            transcript_text = _transcribe_audio_with_openai(
                audio_path=audio_path,
                api_key=openai_api_key,
                model=transcription_model,
            )
        finally:
            try:
                Path(audio_path).unlink(missing_ok=True)
            except OSError:
                pass
        return {
            "title": title,
            "entries": [],
            "transcript_text": transcript_text,
            "source": "openai_audio_transcription",
        }
    except Exception:
        return None


def fetch_transcript(
    video_id: str,
    *,
    youtube_url: str | None = None,
    preferred_languages: list[str] | None = None,
    openai_api_key: str | None = None,
    transcription_model: str = "whisper-1",
) -> dict:
    youtube_transcript = _fetch_with_youtube_transcript_api(video_id, preferred_languages)
    if youtube_transcript:
        return youtube_transcript

    metadata = fetch_youtube_metadata(video_id)
    track = _choose_caption_track(metadata["caption_tracks"])
    if track:
        transcript_url = _ensure_json3(track["baseUrl"])
        payload = _fetch_json_or_xml(transcript_url)
        entries = _extract_transcript_entries(payload)
        transcript_text = clean_transcript_text(" ".join(entry["text"] for entry in entries))

        if transcript_text:
            return {
                "title": metadata["title"],
                "track": track,
                "entries": entries,
                "transcript_text": transcript_text,
                "source": "youtube_caption_fallback",
            }

    audio_fallback = _fetch_with_audio_fallback(
        youtube_url=youtube_url,
        openai_api_key=openai_api_key,
        transcription_model=transcription_model,
    )
    if audio_fallback:
        return audio_fallback

    raise RuntimeError("No transcript track found for this video")
