from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener, urlopen


@dataclass(slots=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    text: str


def request(
    method: str,
    url: str,
    *,
    headers: Optional[Mapping[str, str]] = None,
    body: bytes | None = None,
    proxy_url: str | None = None,
    timeout: float = 30.0,
) -> HttpResponse:
    req = Request(url, data=body, headers=dict(headers or {}), method=method.upper())

    try:
        opener = build_opener(ProxyHandler({"http": proxy_url, "https": proxy_url})) if proxy_url else None
        response_context = opener.open(req, timeout=timeout) if opener else urlopen(req, timeout=timeout)
        with response_context as response:
            return HttpResponse(
                status=getattr(response, "status", 200),
                headers={key.lower(): value for key, value in response.headers.items()},
                text=response.read().decode("utf-8", errors="replace"),
            )
    except HTTPError as exc:
        return HttpResponse(
            status=exc.code,
            headers={key.lower(): value for key, value in (exc.headers or {}).items()},
            text=exc.read().decode("utf-8", errors="replace"),
        )
    except URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc.reason}") from exc
