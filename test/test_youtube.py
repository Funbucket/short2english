import unittest

from src.lib.text import mask_expression, normalize_answer
from src.lib.youtube import extract_video_id
from src.services.quiz import build_quiz_questions, calculate_priority


class YoutubeAndQuizTest(unittest.TestCase):
    def test_extract_video_id_supports_shorts_urls(self):
        self.assertEqual(
            extract_video_id("https://youtube.com/shorts/abc123DEF45"),
            "abc123DEF45",
        )

    def test_extract_video_id_supports_watch_urls(self):
        self.assertEqual(
            extract_video_id("https://www.youtube.com/watch?v=abc123DEF45"),
            "abc123DEF45",
        )

    def test_extract_video_id_supports_youtu_be_urls(self):
        self.assertEqual(
            extract_video_id("https://youtu.be/abc123DEF45"),
            "abc123DEF45",
        )

    def test_normalize_answer_removes_punctuation_and_case(self):
        self.assertEqual(normalize_answer(" Out of the blue! "), "out of the blue")

    def test_mask_expression_preserves_word_count(self):
        self.assertEqual(mask_expression("out of the blue"), "___ __ ___ ____")

    def test_calculate_priority_favors_weak_and_stale_cards(self):
        now = 1_700_000_000_000
        strong = {
            "wrong_count": 0,
            "correct_count": 5,
            "last_tested_at": "2026-05-25T00:00:00+00:00",
        }
        weak = {
            "wrong_count": 3,
            "correct_count": 0,
            "last_tested_at": "2026-05-15T00:00:00+00:00",
        }
        self.assertGreater(calculate_priority(weak, now), calculate_priority(strong, now))

    def test_build_quiz_questions_uses_key_expression_as_expected_answer(self):
        questions = build_quiz_questions(
            [
                {
                    "id": "1",
                    "english_text": "He called me out of the blue one day.",
                    "korean_meaning": "어느 날 갑자기 그가 나에게 전화했어.",
                    "key_expression": "out of the blue",
                    "key_expression_meaning": "갑자기 / 뜬금없이",
                    "wrong_count": 0,
                    "correct_count": 0,
                    "last_tested_at": None,
                }
            ]
        )

        self.assertEqual(questions[0]["expected_answer"], "out of the blue")
        self.assertIn("갑자기 / 뜬금없이", questions[0]["prompt"])


if __name__ == "__main__":
    unittest.main()
