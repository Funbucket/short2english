from __future__ import annotations

import json

from src.lib.http import request


class TelegramClient:
    def __init__(self, token: str):
        self.token = token

    def api_url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.token}/{method}"

    def _request(self, method: str, payload: dict) -> object:
        response = request(
            "POST",
            self.api_url(method),
            headers={"content-type": "application/json"},
            body=json.dumps(payload).encode("utf-8"),
        )
        data = json.loads(response.text or "{}")
        if response.status >= 400 or data.get("ok") is False:
            description = data.get("description") or f"Telegram API request failed: {method}"
            raise RuntimeError(description)
        return data.get("result")

    def send_message(self, chat_id: int | str, text: str, options: dict | None = None) -> object:
        payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        if options:
            payload.update(options)
        return self._request("sendMessage", payload)

    def answer_callback_query(self, callback_query_id: str, text: str | None = None, *, show_alert: bool = False) -> object:
        payload: dict[str, object] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        if show_alert:
            payload["show_alert"] = True
        return self._request("answerCallbackQuery", payload)

    def set_webhook(self, url: str, secret_token: str = "") -> object:
        payload: dict[str, object] = {"url": url}
        if secret_token:
            payload["secret_token"] = secret_token
        return self._request("setWebhook", payload)


def chunk_text_for_telegram(text: str, max_len: int = 3500) -> list[str]:
    paragraphs = [paragraph.strip() for paragraph in str(text or "").split("\n\n")]
    paragraphs = [paragraph for paragraph in paragraphs if paragraph]
    if not paragraphs:
        return [""]

    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= max_len:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        if len(paragraph) <= max_len:
            current = paragraph
            continue

        lines = [line for line in paragraph.splitlines() if line]
        buffer = ""
        for line in lines or [paragraph]:
            line_candidate = f"{buffer}\n{line}" if buffer else line
            if len(line_candidate) <= max_len:
                buffer = line_candidate
                continue
            if buffer:
                chunks.append(buffer)
            if len(line) <= max_len:
                buffer = line
            else:
                for start in range(0, len(line), max_len):
                    chunks.append(line[start : start + max_len])
                buffer = ""
        current = buffer

    if current:
        chunks.append(current)

    return chunks


def send_long_message(
    bot: TelegramClient,
    chat_id: int | str,
    text: str,
    *,
    max_len: int = 3500,
    options: dict | None = None,
) -> list[object]:
    results = []
    for chunk in chunk_text_for_telegram(text, max_len=max_len):
        if not chunk:
            continue
        results.append(bot.send_message(chat_id, chunk, options=options))
    return results


def build_inline_keyboard(button_rows: list[list[dict[str, str]]]) -> dict:
    return {"inline_keyboard": button_rows}
