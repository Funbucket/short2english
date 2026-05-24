from __future__ import annotations

from datetime import datetime, timezone

from src.services.quiz import calculate_priority


def _rows(value):
    return value if isinstance(value, list) else []


def find_user_by_telegram_id(db, telegram_user_id: int):
    rows = _rows(
        db.select(
            "users",
            filters=[{"column": "telegram_user_id", "op": "eq", "value": telegram_user_id}],
            limit=1,
        )
    )
    return rows[0] if rows else None


def upsert_user(db, telegram_message: dict):
    user = telegram_message.get("from") or {}
    chat_id = (telegram_message.get("chat") or {}).get("id")
    telegram_user_id = user.get("id")
    existing = find_user_by_telegram_id(db, telegram_user_id)

    payload = {
        "telegram_user_id": telegram_user_id,
        "telegram_chat_id": chat_id,
        "username": user.get("username"),
        "first_name": user.get("first_name"),
        "last_name": user.get("last_name"),
        "last_seen_at": datetime.now(tz=timezone.utc).isoformat(),
    }

    if not existing:
        created = _rows(db.insert("users", [payload]))
        return created[0]

    updated = _rows(
        db.update(
            "users",
            payload,
            filters=[{"column": "telegram_user_id", "op": "eq", "value": telegram_user_id}],
        )
    )
    return updated[0] if updated else existing


def set_user_active_short(db, user_id, short_id):
    rows = _rows(
        db.update(
            "users",
            {
                "active_short_id": short_id,
                "last_seen_at": datetime.now(tz=timezone.utc).isoformat(),
            },
            filters=[{"column": "id", "op": "eq", "value": user_id}],
        )
    )
    return rows[0] if rows else None


def get_user_by_id(db, user_id):
    rows = _rows(
        db.select(
            "users",
            filters=[{"column": "id", "op": "eq", "value": user_id}],
            limit=1,
        )
    )
    return rows[0] if rows else None


def find_short_by_user_and_video_id(db, user_id, video_id: str):
    rows = _rows(
        db.select(
            "shorts",
            filters=[
                {"column": "user_id", "op": "eq", "value": user_id},
                {"column": "video_id", "op": "eq", "value": video_id},
            ],
            limit=1,
            order=[{"column": "created_at", "ascending": False}],
        )
    )
    return rows[0] if rows else None


def get_short_cards(db, short_id):
    return _rows(
        db.select(
            "cards",
            filters=[{"column": "short_id", "op": "eq", "value": short_id}],
            order=[{"column": "sequence", "ascending": True}],
        )
    )


def get_card_by_id(db, card_id):
    rows = _rows(
        db.select(
            "cards",
            filters=[{"column": "id", "op": "eq", "value": card_id}],
            limit=1,
        )
    )
    return rows[0] if rows else None


def create_short_with_cards(
    db,
    *,
    user_id,
    video_id: str,
    url: str,
    title: str | None,
    transcript_source: str | None,
    transcript_text: str,
    cards: list[dict],
):
    created_shorts = _rows(
        db.insert(
            "shorts",
            [
                {
                    "user_id": user_id,
                    "video_id": video_id,
                    "url": url,
                    "title": title,
                    "transcript_source": transcript_source,
                    "transcript_text": transcript_text,
                    "processing_status": "completed",
                    "error_message": None,
                }
            ],
        )
    )
    short = created_shorts[0]

    card_rows = [
        {
            "short_id": short["id"],
            "user_id": user_id,
            "sequence": index + 1,
            "english_text": card["english_text"],
            "korean_meaning": card["korean_meaning"],
            "key_expression": card["key_expression"],
            "key_expression_meaning": card["key_expression_meaning"],
        }
        for index, card in enumerate(cards)
    ]
    created_cards = _rows(db.insert("cards", card_rows)) if card_rows else []
    return {"short": short, "cards": created_cards}


def create_failed_short(
    db,
    *,
    user_id,
    video_id: str,
    url: str,
    title: str | None,
    transcript_source: str | None,
    error_message: str,
):
    created_shorts = _rows(
        db.insert(
            "shorts",
            [
                {
                    "user_id": user_id,
                    "video_id": video_id,
                    "url": url,
                    "title": title,
                    "transcript_source": transcript_source,
                    "transcript_text": None,
                    "processing_status": "failed",
                    "error_message": error_message,
                }
            ],
        )
    )
    return created_shorts[0]


def find_expression_by_sentence_id(db, sentence_id):
    rows = _rows(
        db.select(
            "expressions",
            filters=[{"column": "sentence_id", "op": "eq", "value": sentence_id}],
            limit=1,
        )
    )
    return rows[0] if rows else None


def upsert_expression(db, expression: dict):
    existing = find_expression_by_sentence_id(db, expression["sentence_id"])
    payload = {
        "sentence_id": expression["sentence_id"],
        "expression": expression["expression"],
        "meaning_ko": expression["meaning_ko"],
        "deep_explanation": expression["deep_explanation"],
        "examples_json": expression.get("examples_json") or [],
        "similar_expressions_json": expression.get("similar_expressions_json") or [],
        "speaking_line": expression["speaking_line"],
    }

    if existing:
        rows = _rows(
            db.update(
                "expressions",
                payload,
                filters=[{"column": "id", "op": "eq", "value": existing["id"]}],
            )
        )
        return rows[0] if rows else existing

    rows = _rows(db.insert("expressions", [payload]))
    return rows[0] if rows else None


def list_recent_shorts(db, user_id, limit: int = 10):
    return _rows(
        db.select(
            "shorts",
            filters=[{"column": "user_id", "op": "eq", "value": user_id}],
            order=[{"column": "created_at", "ascending": False}],
            limit=limit,
        )
    )


def list_user_cards(db, user_id):
    return _rows(
        db.select(
            "cards",
            filters=[{"column": "user_id", "op": "eq", "value": user_id}],
            order=[{"column": "created_at", "ascending": False}],
        )
    )


def list_weak_cards(db, user_id, limit: int = 5):
    return _rows(
        db.select(
            "cards",
            filters=[{"column": "user_id", "op": "eq", "value": user_id}],
            order=[
                {"column": "wrong_count", "ascending": False},
                {"column": "correct_count", "ascending": True},
                {"column": "created_at", "ascending": False},
            ],
            limit=limit,
        )
    )


def list_due_cards(db, user_id, limit: int = 10):
    cards = list_user_cards(db, user_id)
    return sorted(cards, key=calculate_priority, reverse=True)[:limit]


def close_active_quiz_sessions(db, user_id):
    sessions = _rows(
        db.select(
            "quiz_sessions",
            filters=[
                {"column": "user_id", "op": "eq", "value": user_id},
                {"column": "status", "op": "eq", "value": "active"},
            ],
            order=[{"column": "created_at", "ascending": False}],
        )
    )

    for session in sessions:
        db.update(
            "quiz_sessions",
            {
                "status": "completed",
                "completed_at": datetime.now(tz=timezone.utc).isoformat(),
                "updated_at": datetime.now(tz=timezone.utc).isoformat(),
            },
            filters=[{"column": "id", "op": "eq", "value": session["id"]}],
        )

    return sessions


def create_quiz_session(db, *, user_id, chat_id, questions: list[dict]):
    rows = _rows(
        db.insert(
            "quiz_sessions",
            [
                {
                    "user_id": user_id,
                    "telegram_chat_id": chat_id,
                    "status": "active",
                    "questions": questions,
                    "current_index": 0,
                    "score": 0,
                    "total_questions": len(questions),
                    "updated_at": datetime.now(tz=timezone.utc).isoformat(),
                }
            ],
        )
    )
    return rows[0]


def get_active_quiz_session(db, user_id):
    rows = _rows(
        db.select(
            "quiz_sessions",
            filters=[
                {"column": "user_id", "op": "eq", "value": user_id},
                {"column": "status", "op": "eq", "value": "active"},
            ],
            order=[{"column": "created_at", "ascending": False}],
            limit=1,
        )
    )
    return rows[0] if rows else None


def update_quiz_session(db, session_id, changes: dict):
    rows = _rows(
        db.update(
            "quiz_sessions",
            {
                **changes,
                "updated_at": datetime.now(tz=timezone.utc).isoformat(),
            },
            filters=[{"column": "id", "op": "eq", "value": session_id}],
        )
    )
    return rows[0] if rows else None


def record_quiz_attempt(db, attempt: dict):
    rows = _rows(db.insert("quiz_attempts", [attempt]))
    return rows[0]


def update_card_stats(db, card: dict, is_correct: bool):
    updated = {
        "correct_count": int(card.get("correct_count") or 0) + (1 if is_correct else 0),
        "wrong_count": int(card.get("wrong_count") or 0) + (0 if is_correct else 1),
        "last_tested_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    rows = _rows(db.update("cards", updated, filters=[{"column": "id", "op": "eq", "value": card["id"]}]))
    return rows[0] if rows else None


def get_user_stats(db, user_id):
    shorts, cards, attempts = [
        list_recent_shorts(db, user_id, 1000),
        list_user_cards(db, user_id),
        _rows(db.select("quiz_attempts", filters=[{"column": "user_id", "op": "eq", "value": user_id}])),
    ]

    correct_attempts = sum(1 for item in attempts if item.get("is_correct"))
    accuracy = round((correct_attempts / len(attempts)) * 100) if attempts else 0

    return {
        "shortCount": len(shorts),
        "cardCount": len(cards),
        "attemptCount": len(attempts),
        "accuracy": accuracy,
        "weakCardCount": sum(1 for card in cards if int(card.get("wrong_count") or 0) > 0),
    }
