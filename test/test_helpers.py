import unittest

from src.app import (
    build_expression_keyboard,
    format_processing_error,
    mark_update_seen,
    parse_expression_selection,
    should_retry_existing_short,
)
from src.lib.telegram import chunk_text_for_telegram
from src.lib.text import clean_transcript_text
from src.lib.transcript import TranscriptUnavailableError
from src.services.llm import safe_json_loads
from src.services.messages import format_deep_dive_message


class HelperTest(unittest.TestCase):
    def test_safe_json_loads_handles_code_fences(self):
        payload = """```json
        {"cards":[{"sentence":"Hello","meaning_ko":"안녕","key_expression":"Hello","key_expression_meaning_ko":"인사"}]}
        ```"""
        data = safe_json_loads(payload)
        self.assertEqual(data["cards"][0]["sentence"], "Hello")

    def test_chunk_text_for_telegram_splits_long_text(self):
        text = "\n\n".join([f"paragraph-{index}" for index in range(10)])
        chunks = chunk_text_for_telegram(text, max_len=20)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 20 for chunk in chunks))

    def test_clean_transcript_text_removes_noise(self):
        text = "Hello [Music] there. (applause) Hello there."
        cleaned = clean_transcript_text(text)
        self.assertNotIn("Music", cleaned)
        self.assertNotIn("applause", cleaned.lower())
        self.assertIn("Hello there", cleaned)

    def test_parse_expression_selection_handles_numeric_text(self):
        self.assertEqual(parse_expression_selection("2"), 2)
        self.assertEqual(parse_expression_selection("  #3 "), 3)
        self.assertIsNone(parse_expression_selection("hello"))

    def test_format_deep_dive_message_includes_sections(self):
        message = format_deep_dive_message(
            {
                "expression": "bumpy ride",
                "meaning_ko": "순탄하지 않은 과정",
                "deep_explanation": "기본 뜻: 울퉁불퉁해서 흔들리는 상황\n비유적 의미: 우여곡절이 많은 과정",
                "examples_json": [{"en": "It was a bumpy ride.", "ko": "우여곡절이 많았어."}],
                "similar_expressions_json": ["rough journey"],
                "speaking_line": "It's been a bumpy ride.",
            }
        )
        self.assertIn("📚 Deep Dive — bumpy ride", message)
        self.assertIn("기본 뜻:", message)
        self.assertIn("비유적 의미:", message)
        self.assertIn("예문:", message)
        self.assertIn("rough journey", message)

    def test_build_expression_keyboard_uses_card_ids(self):
        keyboard = build_expression_keyboard(
            [
                {"id": "card-1"},
                {"id": "card-2"},
                {"id": "card-3"},
            ]
        )
        self.assertEqual(keyboard["inline_keyboard"][0][0]["text"], "1")
        self.assertEqual(keyboard["inline_keyboard"][0][0]["callback_data"], "exp:card-1")

    def test_mark_update_seen_filters_duplicate_update_ids(self):
        self.assertFalse(mark_update_seen({"update_id": 12345}))
        self.assertTrue(mark_update_seen({"update_id": 12345}))

    def test_format_processing_error_detects_supabase_schema_issue(self):
        message = format_processing_error(
            RuntimeError(
                'Supabase GET /rest/v1/users failed (404): {"code":"PGRST205","details":null,"hint":null,"message":"Could not find the table \'public.users\' in the schema cache"}'
            )
        )
        self.assertIn("Supabase 설정이 아직 완료되지 않았습니다.", message)
        self.assertIn("supabase/schema.sql", message)

    def test_format_processing_error_detects_transcript_unavailable(self):
        message = format_processing_error(
            TranscriptUnavailableError(
                video_id="g6671WnPUsQ",
                youtube_url="https://www.youtube.com/shorts/g6671WnPUsQ",
                title="test",
                tried_sources=[
                    "youtube_transcript_api",
                    "youtube_page_caption_tracks",
                ],
            )
        )
        self.assertIn("자동으로 읽을 수 있는 자막/전사 트랙을 찾지 못했습니다.", message)
        self.assertIn("다른 Shorts를 보내주세요", message)

    def test_should_retry_existing_short_skips_failed_records(self):
        self.assertFalse(
            should_retry_existing_short(
                {"processing_status": "failed", "error_message": "YouTube blocked access to this video"}
            )
        )
        self.assertFalse(
            should_retry_existing_short(
                {"processing_status": "completed", "error_message": "YouTube blocked access to this video"}
            )
        )
        self.assertTrue(
            should_retry_existing_short(
                {"processing_status": "completed", "error_message": ""}
            )
        )


if __name__ == "__main__":
    unittest.main()
