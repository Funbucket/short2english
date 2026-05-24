import unittest

from src.config import resolve_telegram_webhook_url


class ResolveTelegramWebhookUrlTest(unittest.TestCase):
    def test_prefers_explicit_telegram_url(self):
        self.assertEqual(
            resolve_telegram_webhook_url(
                telegram_webhook_url="https://example.com/telegram/webhook",
                public_base_url="https://render.example",
                render_external_url="https://render.example",
            ),
            "https://example.com/telegram/webhook",
        )

    def test_falls_back_to_public_base_url(self):
        self.assertEqual(
            resolve_telegram_webhook_url(
                telegram_webhook_url="",
                public_base_url="https://example.com",
                render_external_url="",
            ),
            "https://example.com/telegram/webhook",
        )

    def test_falls_back_to_render_external_url(self):
        self.assertEqual(
            resolve_telegram_webhook_url(
                telegram_webhook_url="",
                public_base_url="",
                render_external_url="https://short2english.onrender.com/",
            ),
            "https://short2english.onrender.com/telegram/webhook",
        )

    def test_returns_empty_string_without_any_base_url(self):
        self.assertEqual(
            resolve_telegram_webhook_url(
                telegram_webhook_url="",
                public_base_url="",
                render_external_url="",
            ),
            "",
        )


if __name__ == "__main__":
    unittest.main()
