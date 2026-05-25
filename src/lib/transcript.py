from __future__ import annotations

import json
import time

from src.lib.http import request
from src.lib.text import clean_transcript_text, normalize_whitespace


DEFAULT_TRANSCRIPT_API_BASE_URL = "https://youtubetranscript.dev/api/v2"
DEFAULT_POLL_INTERVAL_SECONDS = 10
DEFAULT_POLL_TIMEOUT_SECONDS = 20 * 60


class TranscriptUnavailableError(RuntimeError):
    def __init__(self, *, video_id: str, youtube_url: str | None, message: str):
        self.video_id = video_id
        self.youtube_url = youtube_url
        super().__init__(message)


class TranscriptProviderError(RuntimeError):
    def __init__(self, *, status: int | None, code: str | None, message: str):
        self.status = status
        self.code = code
        super().__init__(message)


def _extract_video_ref(video_id: str, youtube_url: str | None) -> str:
    return youtube_url or video_id


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _response_json(response) -> dict:
    try:
        return json.loads(response.text or "{}")
    except json.JSONDecodeError as exc:
        raise TranscriptProviderError(
            status=response.status,
            code=None,
            message=f"YouTubeTranscript.dev returned invalid JSON ({response.status})",
        ) from exc


def _extract_error_message(payload: dict, fallback_status: int) -> str:
    code = (
        payload.get("code")
        or payload.get("error")
        or payload.get("error_code")
        or payload.get("status")
    )
    message = payload.get("message") or payload.get("error_message") or "Unknown API error"
    if code:
        return f"YouTubeTranscript.dev API returned {fallback_status} {code}: {message}"
    return f"YouTubeTranscript.dev API returned {fallback_status}: {message}"


def _raise_for_api_error(response) -> None:
    payload = _response_json(response)
    raise TranscriptProviderError(
        status=response.status,
        code=str(
            payload.get("code")
            or payload.get("error")
            or payload.get("error_code")
            or ""
        )
        or None,
        message=_extract_error_message(payload, response.status),
    )


def _request_json(
    *,
    method: str,
    url: str,
    api_key: str,
    body: dict | None = None,
) -> dict:
    headers = {
        "authorization": f"Bearer {api_key}",
        "content-type": "application/json",
        "accept": "application/json",
    }
    payload = json.dumps(body or {}).encode("utf-8") if body is not None else None
    response = request(method, url, headers=headers, body=payload, timeout=60.0)
    if response.status >= 400:
        _raise_for_api_error(response)
    return _response_json(response)


def _extract_segments(payload: dict) -> list[dict]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    transcript = data.get("transcript") if isinstance(data, dict) else None

    if isinstance(transcript, list):
        segments: list[dict] = []
        for item in transcript:
            if not isinstance(item, dict):
                continue
            text = normalize_whitespace(item.get("text") or item.get("caption") or "")
            if not text:
                continue
            segments.append(
                {
                    "start": float(item.get("start") or 0),
                    "duration": float(item.get("duration") or 0),
                    "text": text,
                }
            )
        return segments

    if isinstance(transcript, dict):
        text = normalize_whitespace(transcript.get("text") or "")
        if text:
            return [{"start": 0, "duration": 0, "text": text}]

        segments = transcript.get("segments") or transcript.get("items")
        if isinstance(segments, list):
            parsed: list[dict] = []
            for item in segments:
                if not isinstance(item, dict):
                    continue
                item_text = normalize_whitespace(item.get("text") or item.get("caption") or "")
                if not item_text:
                    continue
                parsed.append(
                    {
                        "start": float(item.get("start") or item.get("tStartMs") or 0) / 1000.0,
                        "duration": float(item.get("duration") or item.get("dDurationMs") or 0) / 1000.0,
                        "text": item_text,
                    }
                )
            return parsed

    return []


def _extract_title(payload: dict) -> str | None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        return None
    for key in ("title", "video_title", "videoTitle", "name"):
        title = normalize_whitespace(data.get(key) or "")
        if title:
            return title
    return None


def _extract_job_id(payload: dict) -> str | None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        data = payload
    for key in ("job_id", "jobId", "id"):
        value = data.get(key)
        if value:
            return str(value)
    return None


def _extract_status(payload: dict) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if isinstance(data, dict):
        for key in ("status", "state"):
            value = data.get(key)
            if value:
                return str(value).lower()
    value = payload.get("status") or payload.get("state")
    return str(value).lower() if value else ""


def _build_result(payload: dict, source: str) -> dict | None:
    segments = _extract_segments(payload)
    transcript_text = clean_transcript_text(" ".join(item["text"] for item in segments))
    if not transcript_text:
        return None

    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        data = {}

    return {
        "title": _extract_title(payload),
        "entries": segments,
        "transcript_text": transcript_text,
        "source": source,
        "job_id": _extract_job_id(payload),
        "status": _extract_status(payload) or "completed",
        "raw": data,
    }


def _poll_job(*, api_key: str, base_url: str, job_id: str, timeout_seconds: int, poll_interval_seconds: int) -> dict:
    deadline = time.monotonic() + timeout_seconds
    while True:
        payload = _request_json(
            method="GET",
            url=_join_url(base_url, f"/jobs/{job_id}"),
            api_key=api_key,
        )
        result = _build_result(payload, "youtubetranscript.dev")
        status = _extract_status(payload) or (result or {}).get("status") or ""
        if status in {"completed", "success", "done", "finished"}:
            if result:
                return result
            raise TranscriptProviderError(
                status=None,
                code=None,
                message="YouTubeTranscript.dev ASR job completed without transcript text",
            )
        if status in {"failed", "error", "cancelled", "canceled"}:
            raise TranscriptProviderError(
                status=None,
                code=None,
                message="YouTubeTranscript.dev ASR job failed",
            )

        if time.monotonic() >= deadline:
            raise TranscriptProviderError(
                status=None,
                code=None,
                message="YouTubeTranscript.dev ASR job timed out",
            )

        time.sleep(poll_interval_seconds)


def _transcribe_once(
    *,
    api_key: str,
    base_url: str,
    video_ref: str,
    source: str | None = None,
) -> dict:
    body: dict = {"video": video_ref}
    if source:
        body["source"] = source

    try:
        payload = _request_json(
            method="POST",
            url=_join_url(base_url, "/transcribe"),
            api_key=api_key,
            body=body,
        )
    except TranscriptProviderError as exc:
        message = str(exc).lower()
        if exc.status == 404 and ("no_captions" in message or "no captions" in message):
            return {"status": "no_captions", "title": None}
        raise

    result = _build_result(payload, "youtubetranscript.dev")
    if result:
        return result

    status = _extract_status(payload)
    job_id = _extract_job_id(payload)
    if status == "processing" and job_id:
        return {
            "status": "processing",
            "job_id": job_id,
            "title": _extract_title(payload),
        }

    return {
        "status": status or "unknown",
        "job_id": job_id,
        "title": _extract_title(payload),
    }


def fetch_transcript(
    video_id: str,
    *,
    youtube_url: str | None = None,
    preferred_languages: list[str] | None = None,  # kept for compatibility
    openai_api_key: str | None = None,  # kept for compatibility
    transcription_model: str = "whisper-1",  # kept for compatibility
    youtube_transcript_api_key: str | None = None,
    youtube_transcript_api_base_url: str = DEFAULT_TRANSCRIPT_API_BASE_URL,
) -> dict:
    api_key = (youtube_transcript_api_key or "").strip()
    if not api_key:
        raise TranscriptProviderError(
            status=None,
            code=None,
            message="Missing YOUTUBETRANSCRIPT_API_KEY",
        )

    video_ref = _extract_video_ref(video_id, youtube_url)

    direct = _transcribe_once(
        api_key=api_key,
        base_url=youtube_transcript_api_base_url,
        video_ref=video_ref,
    )
    if direct.get("transcript_text"):
        return direct

    if direct.get("job_id"):
        return _poll_job(
            api_key=api_key,
            base_url=youtube_transcript_api_base_url,
            job_id=direct["job_id"],
            timeout_seconds=DEFAULT_POLL_TIMEOUT_SECONDS,
            poll_interval_seconds=DEFAULT_POLL_INTERVAL_SECONDS,
        )

    # If captions are not available, request ASR explicitly.
    asr = _transcribe_once(
        api_key=api_key,
        base_url=youtube_transcript_api_base_url,
        video_ref=video_ref,
        source="asr",
    )
    if asr.get("transcript_text"):
        return asr

    if asr.get("job_id"):
        return _poll_job(
            api_key=api_key,
            base_url=youtube_transcript_api_base_url,
            job_id=asr["job_id"],
            timeout_seconds=DEFAULT_POLL_TIMEOUT_SECONDS,
            poll_interval_seconds=DEFAULT_POLL_INTERVAL_SECONDS,
        )

    status = str(asr.get("status") or direct.get("status") or "").lower()
    if status == "no_captions":
        raise TranscriptUnavailableError(
            video_id=video_id,
            youtube_url=youtube_url,
            message="이 영상은 자동으로 읽을 수 있는 자막/전사 트랙을 찾지 못했습니다.",
        )

    raise TranscriptProviderError(
        status=None,
        code=None,
        message="YouTubeTranscript.dev did not return a transcript",
    )
