from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from src.app import handle_telegram_update
from src.config import load_config
from src.lib.supabase import SupabaseClient
from src.lib.telegram import TelegramClient


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    content_length = int(handler.headers.get("content-length") or 0)
    raw = handler.rfile.read(content_length) if content_length else b""
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _looks_like_youtube_url(text: str) -> bool:
    normalized = str(text or "").strip()
    return bool(
        re.match(r"^https?://\S+", normalized, flags=re.IGNORECASE)
        or re.match(r"^(www\.)?(youtube\.com|youtu\.be)\S+", normalized, flags=re.IGNORECASE)
    )


def _make_handler(config, db, bot):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Short2English/1.0"

        def _send_json(self, status: int, payload: dict):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_text(self, status: int, text: str):
            body = text.encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "text/plain; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A003
            return

        def do_GET(self):  # noqa: N802
            if self.path == "/health":
                self._send_json(200, {"ok": True, "service": "Short2English"})
                return

            if self.path == "/":
                self._send_text(200, "Short2English bot is running.")
                return

            self._send_json(404, {"ok": False, "error": "Not found"})

        def do_POST(self):  # noqa: N802
            if self.path != "/telegram/webhook":
                self._send_json(404, {"ok": False, "error": "Not found"})
                return

            if config.telegram_webhook_secret:
                incoming = self.headers.get("x-telegram-bot-api-secret-token", "")
                if incoming != config.telegram_webhook_secret:
                    self._send_json(401, {"ok": False, "error": "Unauthorized"})
                    return

            try:
                update = _read_json_body(self)
            except json.JSONDecodeError:
                self._send_json(400, {"ok": False, "error": "Invalid JSON"})
                return

            message = update.get("message") or {}
            chat_id = (message.get("chat") or {}).get("id")
            text = str(message.get("text") or "").strip()
            if chat_id and _looks_like_youtube_url(text):
                def send_ack():
                    try:
                        bot.send_message(chat_id, "링크를 확인 중입니다. 잠시만 기다려주세요.")
                    except Exception as exc:  # noqa: BLE001
                        print(f"Failed to send immediate URL ack: {exc}")

                threading.Thread(target=send_ack, daemon=True).start()

            self._send_json(200, {"ok": True})

            def process_update():
                try:
                    handle_telegram_update(config=config, db=db, bot=bot, update=update)
                except Exception as exc:  # noqa: BLE001
                    print(f"Telegram update handling failed: {exc}")

            threading.Thread(target=process_update, daemon=True).start()

    return Handler


def _start_polling_loop(config, db, bot):
    def run():
        offset = None
        if config.telegram_webhook_url:
            try:
                bot.delete_webhook(drop_pending_updates=False)
                print("Telegram webhook deleted for polling mode")
            except Exception as exc:  # noqa: BLE001
                print(f"Failed to delete Telegram webhook: {exc}")

        while True:
            try:
                updates = bot.get_updates(offset=offset, timeout=30)
                for update in updates:
                    update_id = update.get("update_id")
                    if isinstance(update_id, int):
                        offset = update_id + 1
                    try:
                        handle_telegram_update(config=config, db=db, bot=bot, update=update)
                    except Exception as exc:  # noqa: BLE001
                        print(f"Telegram update handling failed: {exc}")
            except Exception as exc:  # noqa: BLE001
                print(f"Telegram polling failed: {exc}")
                time.sleep(5)
                continue

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def main() -> None:
    config = load_config()
    db = SupabaseClient(config.supabase_url, config.supabase_service_role_key)
    bot = TelegramClient(config.telegram_bot_token)

    if config.telegram_bot_mode == "polling":
        try:
            _start_polling_loop(config, db, bot)
            print("Telegram polling loop started")
        except Exception as exc:  # noqa: BLE001
            print(f"Failed to start Telegram polling loop: {exc}")
    elif config.telegram_webhook_url:
        try:
            bot.set_webhook(config.telegram_webhook_url, config.telegram_webhook_secret)
            print(f"Telegram webhook set to {config.telegram_webhook_url}")
        except Exception as exc:  # noqa: BLE001
            print(f"Failed to set Telegram webhook: {exc}")

    handler = _make_handler(config, db, bot)
    server = ThreadingHTTPServer(("0.0.0.0", config.port), handler)
    server.daemon_threads = True
    print(f"Short2English listening on port {config.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
