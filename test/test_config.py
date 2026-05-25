import unittest

from src.config import load_config, resolve_telegram_webhook_url


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


class TelegramBotModeTest(unittest.TestCase):
    def test_defaults_to_webhook(self):
        from os import environ

        original_token = environ.get("TELEGRAM_BOT_TOKEN")
        original_supabase_url = environ.get("SUPABASE_URL")
        original_supabase_key = environ.get("SUPABASE_SERVICE_ROLE_KEY")
        original_transcript_key = environ.get("YOUTUBETRANSCRIPT_API_KEY")

        try:
            environ["TELEGRAM_BOT_TOKEN"] = "token"
            environ["SUPABASE_URL"] = "https://example.supabase.co"
            environ["SUPABASE_SERVICE_ROLE_KEY"] = "service-role-key"
            environ["YOUTUBETRANSCRIPT_API_KEY"] = "api-key"
            config = load_config()
            self.assertEqual(config.telegram_bot_mode, "webhook")
        finally:
            if original_token is None:
                environ.pop("TELEGRAM_BOT_TOKEN", None)
            else:
                environ["TELEGRAM_BOT_TOKEN"] = original_token

            if original_supabase_url is None:
                environ.pop("SUPABASE_URL", None)
            else:
                environ["SUPABASE_URL"] = original_supabase_url

            if original_supabase_key is None:
                environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)
            else:
                environ["SUPABASE_SERVICE_ROLE_KEY"] = original_supabase_key

            if original_transcript_key is None:
                environ.pop("YOUTUBETRANSCRIPT_API_KEY", None)
            else:
                environ["YOUTUBETRANSCRIPT_API_KEY"] = original_transcript_key


if __name__ == "__main__":
    unittest.main()
