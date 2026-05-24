from __future__ import annotations

import json
from urllib.parse import urlencode

from src.lib.http import request


def _build_url(base_url: str, path: str, query: list[tuple[str, str]] | None = None) -> str:
    base = base_url.rstrip("/")
    url = f"{base}{path}"
    if query:
        url = f"{url}?{urlencode(query, doseq=True)}"
    return url


def _parse_response(response_text: str, method: str, path: str, status: int):
    if status >= 400:
        raise RuntimeError(f"Supabase {method} {path} failed ({status}): {response_text}")

    if not response_text:
        return None

    return json.loads(response_text)


class SupabaseClient:
    def __init__(self, base_url: str, service_role_key: str):
        self.base_url = base_url
        self.service_role_key = service_role_key

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.service_role_key,
            "authorization": f"Bearer {self.service_role_key}",
            "content-type": "application/json",
        }

    def select(
        self,
        table: str,
        *,
        filters: list[dict] | None = None,
        order: list[dict] | None = None,
        limit: int | None = None,
        columns: str = "*",
    ):
        query: list[tuple[str, str]] = [("select", columns)]
        for item in filters or []:
            query.append((str(item["column"]), f"{item['op']}.{item['value']}"))
        for item in order or []:
            direction = "desc" if item.get("ascending") is False else "asc"
            query.append(("order", f"{item['column']}.{direction}"))
        if limit is not None:
            query.append(("limit", str(limit)))

        response = request(
            "GET",
            _build_url(self.base_url, f"/rest/v1/{table}", query),
            headers={
                **self._headers(),
                "prefer": "return=representation",
            },
        )
        return _parse_response(response.text, "GET", f"/rest/v1/{table}", response.status)

    def insert(self, table: str, rows: list[dict]):
        response = request(
            "POST",
            _build_url(self.base_url, f"/rest/v1/{table}"),
            headers={**self._headers(), "prefer": "return=representation"},
            body=json.dumps(rows).encode("utf-8"),
        )
        return _parse_response(response.text, "POST", f"/rest/v1/{table}", response.status)

    def update(self, table: str, changes: dict, filters: list[dict] | None = None):
        query: list[tuple[str, str]] = []
        for item in filters or []:
            query.append((str(item["column"]), f"{item['op']}.{item['value']}"))

        response = request(
            "PATCH",
            _build_url(self.base_url, f"/rest/v1/{table}", query),
            headers={**self._headers(), "prefer": "return=representation"},
            body=json.dumps(changes).encode("utf-8"),
        )
        return _parse_response(response.text, "PATCH", f"/rest/v1/{table}", response.status)
