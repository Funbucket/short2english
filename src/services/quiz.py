from __future__ import annotations

from datetime import datetime, timezone

from src.lib.text import mask_expression, normalize_answer


def calculate_priority(card: dict, now: float | None = None) -> int:
    current_ms = now if now is not None else datetime.now(tz=timezone.utc).timestamp() * 1000
    last_tested = card.get("last_tested_at")
    if last_tested:
        try:
            last_tested_dt = datetime.fromisoformat(str(last_tested).replace("Z", "+00:00"))
            days_since_last_tested = max(0, int((current_ms - last_tested_dt.timestamp() * 1000) // 86_400_000))
        except ValueError:
            days_since_last_tested = 30
    else:
        days_since_last_tested = 30

    return int(card.get("wrong_count") or 0) * 3 - int(card.get("correct_count") or 0) + days_since_last_tested


def build_quiz_questions(cards: list[dict], limit: int = 7) -> list[dict]:
    sorted_cards = sorted(cards, key=calculate_priority, reverse=True)[:limit]
    questions = []
    for index, card in enumerate(sorted_cards, start=1):
        questions.append(
            {
                "index": index,
                "card_id": card["id"],
                "english_text": card["english_text"],
                "korean_meaning": card["korean_meaning"],
                "key_expression": card["key_expression"],
                "key_expression_meaning": card["key_expression_meaning"],
                "expected_answer": normalize_answer(card["key_expression"]),
                "prompt": "\n".join(
                    [
                        "뜻:",
                        card["key_expression_meaning"],
                        "",
                        "빈칸:",
                        mask_expression(card["key_expression"]),
                    ]
                ),
            }
        )
    return questions


def evaluate_quiz_answer(question: dict, answer: str) -> dict:
    normalized_answer = normalize_answer(answer)
    expected = normalize_answer(question.get("expected_answer") or question.get("key_expression"))
    return {
        "is_correct": normalized_answer == expected,
        "normalized_answer": normalized_answer,
        "normalized_expected": expected,
    }
