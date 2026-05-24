from __future__ import annotations

from datetime import datetime, timezone
import re
import threading
import time

from src.lib.telegram import TelegramClient, build_inline_keyboard, send_long_message
from src.lib.transcript import fetch_transcript
from src.lib.youtube import extract_video_id
from src.services.llm import generate_expression_deep_dive, generate_learning_cards
from src.services.messages import (
    format_history_message,
    format_deep_dive_message,
    format_learning_message,
    format_quiz_complete,
    format_quiz_correct,
    format_quiz_question,
    format_quiz_wrong,
    format_review_message,
    format_stats_message,
    start_message,
)
from src.services.quiz import build_quiz_questions, evaluate_quiz_answer
from src.services.repository import (
    close_active_quiz_sessions,
    create_failed_short,
    create_quiz_session,
    create_short_with_cards,
    find_expression_by_sentence_id,
    find_short_by_user_and_video_id,
    get_card_by_id,
    get_active_quiz_session,
    get_user_by_id,
    get_user_stats,
    list_due_cards,
    list_recent_shorts,
    list_weak_cards,
    record_quiz_attempt,
    get_short_cards,
    set_user_active_short,
    upsert_expression,
    update_card_stats,
    update_quiz_session,
    upsert_user,
)

_SEEN_UPDATE_IDS: set[int] = set()


def get_message_text(update: dict) -> str:
    return (update.get("message") or {}).get("text", "").strip()


def is_command(text: str, command: str) -> bool:
    return text == f"/{command}" or text.startswith(f"/{command} ")


def is_likely_url(text: str) -> bool:
    return bool(re.match(r"^https?://\S+", text, flags=re.IGNORECASE) or re.match(r"^(www\.)?(youtube\.com|youtu\.be)\S+", text, flags=re.IGNORECASE))


def send(bot: TelegramClient, chat_id, text: str):
    return bot.send_message(chat_id, text)


def send_with_options(bot: TelegramClient, chat_id, text: str, options: dict | None = None):
    return bot.send_message(chat_id, text, options=options)


def get_update_message(update: dict) -> dict | None:
    return update.get("message")


def get_update_callback_query(update: dict) -> dict | None:
    return update.get("callback_query")


def get_chat_id_from_message(message: dict) -> int | None:
    return (message.get("chat") or {}).get("id")


def get_chat_id_from_update(update: dict) -> int | None:
    message = get_update_message(update)
    if message:
        return get_chat_id_from_message(message)

    callback_query = get_update_callback_query(update)
    if callback_query:
        message = callback_query.get("message") or {}
        return get_chat_id_from_message(message)

    return None


def mark_update_seen(update: dict) -> bool:
    update_id = update.get("update_id")
    if not isinstance(update_id, int):
        return False
    if update_id in _SEEN_UPDATE_IDS:
        return True
    _SEEN_UPDATE_IDS.add(update_id)
    if len(_SEEN_UPDATE_IDS) > 5000:
        _SEEN_UPDATE_IDS.clear()
    return False


def build_expression_keyboard(cards: list[dict]) -> dict:
    button_rows = [
        [{"text": str(index + 1), "callback_data": f"exp:{card['id']}"} for index, card in enumerate(cards[:3])]
    ]
    return build_inline_keyboard(button_rows)


def get_summary_cards(short: dict, cards: list[dict]) -> list[dict]:
    if not cards:
        return []
    return cards[:3]


def send_summary_cards(*, bot: TelegramClient, chat_id, short: dict, cards: list[dict], source: str | None = None):
    summary_cards = get_summary_cards(short, cards)
    options = {"reply_markup": build_expression_keyboard(summary_cards)} if summary_cards else None
    send_with_options(
        bot,
        chat_id,
        format_learning_message(
            url=short["url"],
            title=short.get("title"),
            cards=summary_cards,
            source=source,
        ),
        options=options,
    )


def parse_expression_selection(text: str) -> int | None:
    value = re.sub(r"\D", "", text or "").strip()
    if not value:
        return None
    try:
        selection = int(value)
    except ValueError:
        return None
    return selection if selection > 0 else None


def get_latest_short_and_cards(db, user_id):
    shorts = list_recent_shorts(db, user_id, 1)
    if not shorts:
        return None, []
    short = shorts[0]
    return short, get_short_cards(db, short["id"])


def get_user_active_short(db, user_id):
    user = get_user_by_id(db, user_id)
    if not user or not user.get("active_short_id"):
        return None, []

    short_rows = db.select(
        "shorts",
        filters=[{"column": "id", "op": "eq", "value": user["active_short_id"]}],
        limit=1,
    )
    shorts = short_rows if isinstance(short_rows, list) else []
    if not shorts:
        return None, []
    short = shorts[0]
    return short, get_short_cards(db, short["id"])


def load_expression_payload(*, config, db, card: dict) -> dict:
    existing = find_expression_by_sentence_id(db, card["id"])
    if existing:
        return existing

    generated = generate_expression_deep_dive(config=config, card=card)
    payload = {
        "sentence_id": card["id"],
        "expression": generated["expression"],
        "meaning_ko": generated["meaning_ko"],
        "deep_explanation": generated["deep_explanation"],
        "examples_json": generated.get("examples") or [],
        "similar_expressions_json": generated.get("similar_expressions") or [],
        "speaking_line": generated["speaking_line"],
    }
    stored = upsert_expression(db, payload)
    return stored or payload


def send_expression_deep_dive(*, config, db, bot: TelegramClient, chat_id, card: dict):
    expression = load_expression_payload(config=config, db=db, card=card)
    send_long_message(bot, chat_id, format_deep_dive_message(expression))
    return expression


def start_progress_notifier(bot: TelegramClient, chat_id, stop_event: threading.Event, stages: list[tuple[int, str]]):
    def run():
        for delay, message in stages:
            if stop_event.wait(delay):
                return
            try:
                send(bot, chat_id, message)
            except Exception as exc:  # noqa: BLE001
                print(f"Failed to send progress update: {exc}")

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def process_short_url_job(*, config, db, bot: TelegramClient, telegram_message: dict, chat_id, text: str, video_id: str, url: str):
    user = None
    stop_event = threading.Event()
    start_progress_notifier(
        bot,
        chat_id,
        stop_event,
        [
            (30, "아직 자막을 찾는 중입니다. 영상에 따라 조금 더 걸릴 수 있어요."),
            (90, "아직 처리 중입니다. 자막이 없으면 더 느려질 수 있어요."),
        ],
    )
    try:
        send(bot, chat_id, "자막을 찾는 중입니다. 잠시만 기다려주세요.")
        user = upsert_user(db, telegram_message)
        existing_short = find_short_by_user_and_video_id(db, user["id"], video_id)
        if existing_short:
            cards = get_short_cards(db, existing_short["id"])
            if not cards:
                send(bot, chat_id, "저장된 학습 카드가 없습니다. 새 YouTube Shorts 링크를 보내주세요.")
                return
            set_user_active_short(db, user["id"], existing_short["id"])
            send_summary_cards(
                bot=bot,
                chat_id=chat_id,
                short=existing_short,
                cards=cards,
                source="saved",
            )
            return

        transcript = fetch_transcript(
            video_id,
            youtube_url=url,
            preferred_languages=config.transcript_languages,
            openai_api_key=config.openai_api_key,
            transcription_model=config.transcription_model,
        )
        send(bot, chat_id, "학습 카드를 만드는 중입니다.")
        generated = generate_learning_cards(
            config=config,
            video_id=video_id,
            title=transcript.get("title"),
            transcript_text=transcript["transcript_text"],
        )
        if not generated["cards"]:
            raise RuntimeError("학습 카드를 생성하지 못했습니다.")
        cards_to_store = [
            {
                "english_text": card["sentence"],
                "korean_meaning": card["meaning_ko"],
                "key_expression": card["key_expression"],
                "key_expression_meaning": card["key_expression_meaning_ko"],
            }
            for card in generated["cards"]
        ]
        result = create_short_with_cards(
            db,
            user_id=user["id"],
            video_id=video_id,
            url=url,
            title=transcript.get("title"),
            transcript_source=transcript.get("source"),
            transcript_text=transcript["transcript_text"],
            cards=cards_to_store,
        )
        set_user_active_short(db, user["id"], result["short"]["id"])

        send_summary_cards(
            bot=bot,
            chat_id=chat_id,
            short=result["short"],
            cards=result["cards"],
            source=generated["source"],
        )
    except Exception as exc:
        if user:
            try:
                create_failed_short(
                    db,
                    user_id=user["id"],
                    video_id=video_id,
                    url=url,
                    title=None,
                    transcript_source=None,
                    error_message=str(exc),
                )
            except Exception as inner_exc:  # noqa: BLE001
                print(f"Failed to persist short error: {inner_exc}")
        send_long_message(
            bot,
            chat_id,
            "\n".join(
                [
                    "Short 처리를 완료하지 못했습니다.",
                    "",
                    str(exc),
                    "",
                    "원인:",
                    "- YouTube captions가 없을 수 있음",
                    "- transcript extraction이 실패했을 수 있음",
                    "- LLM 설정이 필요할 수 있음",
                ]
            ),
        )
    finally:
        stop_event.set()


def handle_expression_selection_by_card_id(*, config, db, bot: TelegramClient, user: dict, chat_id, card_id: str):
    card = get_card_by_id(db, card_id)
    if not card or card.get("user_id") != user["id"]:
        send(bot, chat_id, "선택한 표현을 찾지 못했습니다.")
        return None

    return send_expression_deep_dive(config=config, db=db, bot=bot, chat_id=chat_id, card=card)


def handle_expression_selection_by_number(*, config, db, bot: TelegramClient, user: dict, chat_id, selection: int):
    short, cards = get_user_active_short(db, user["id"])
    if not short or not cards:
        short, cards = get_latest_short_and_cards(db, user["id"])
    if not short:
        send(bot, chat_id, "먼저 YouTube Shorts 링크를 보내주세요.")
        return None

    if not cards:
        send(bot, chat_id, "저장된 학습 카드가 없습니다. 새 YouTube Shorts 링크를 보내주세요.")
        return None

    summary_cards = get_summary_cards(short, cards)
    if not summary_cards:
        send(bot, chat_id, "저장된 학습 카드가 없습니다. 새 YouTube Shorts 링크를 보내주세요.")
        return None

    if selection < 1 or selection > len(summary_cards):
        send(bot, chat_id, f"1부터 {len(summary_cards)} 사이 번호를 선택해주세요.")
        return None

    card = summary_cards[selection - 1]
    return send_expression_deep_dive(config=config, db=db, bot=bot, chat_id=chat_id, card=card)


def handle_callback_query(*, config, db, bot: TelegramClient, update: dict):
    callback_query = get_update_callback_query(update)
    if not callback_query:
        return

    callback_id = callback_query.get("id")
    data = str(callback_query.get("data") or "").strip()
    message = callback_query.get("message") or {}
    user_payload = {"from": callback_query.get("from") or {}, "chat": message.get("chat") or {}}
    user = upsert_user(db, user_payload)
    chat_id = get_chat_id_from_message(message)
    if chat_id is None:
        return

    if callback_id:
        try:
            bot.answer_callback_query(callback_id, "불러오는 중...")
        except Exception:
            pass

    if data.startswith("exp:"):
        card_id = data.split(":", 1)[1].strip()
        if card_id:
            handle_expression_selection_by_card_id(
                config=config,
                db=db,
                bot=bot,
                user=user,
                chat_id=chat_id,
                card_id=card_id,
            )
        return

    if callback_id:
        try:
            bot.answer_callback_query(callback_id, "지원하지 않는 선택입니다.", show_alert=False)
        except Exception:
            pass


def handle_short_url(*, config, db, bot: TelegramClient, telegram_message: dict, text: str):
    chat_id = (telegram_message.get("chat") or {}).get("id")
    video_id = extract_video_id(text)

    if not video_id:
        send(bot, chat_id, "유효한 YouTube Shorts URL을 찾지 못했습니다.")
        return

    url = text if text.startswith("http") else f"https://{text}"

    thread = threading.Thread(
        target=process_short_url_job,
        kwargs={
            "config": config,
            "db": db,
            "bot": bot,
            "telegram_message": telegram_message,
            "chat_id": chat_id,
            "text": text,
            "video_id": video_id,
            "url": url,
        },
        daemon=True,
    )
    thread.start()


def start_quiz_session(*, config, db, bot: TelegramClient, telegram_message: dict):
    chat_id = (telegram_message.get("chat") or {}).get("id")
    user = upsert_user(db, telegram_message)
    cards = list_due_cards(db, user["id"], config.quiz_size)

    if not cards:
        send(bot, chat_id, "먼저 YouTube Shorts 링크를 보내서 학습 카드를 만들어주세요.")
        return None

    close_active_quiz_sessions(db, user["id"])
    questions = build_quiz_questions(cards, config.quiz_size)
    session = create_quiz_session(db, user_id=user["id"], chat_id=chat_id, questions=questions)
    send(bot, chat_id, format_quiz_question(questions[0], 1, len(questions)))
    return session


def handle_quiz_answer(*, db, bot: TelegramClient, telegram_message: dict, user: dict, session: dict, text: str):
    chat_id = (telegram_message.get("chat") or {}).get("id")
    questions = session.get("questions") or []
    current_index = int(session.get("current_index") or 0)
    question = questions[current_index] if current_index < len(questions) else None

    if not question:
        update_quiz_session(
            db,
            session["id"],
            {"status": "completed", "completed_at": datetime.now(tz=timezone.utc).isoformat()},
        )
        send(bot, chat_id, "진행 중인 퀴즈가 없습니다.")
        return

    result = evaluate_quiz_answer(question, text)
    card_rows = db.select("cards", filters=[{"column": "id", "op": "eq", "value": question["card_id"]}], limit=1)
    card = card_rows[0] if card_rows else None

    if card:
        update_card_stats(db, card, result["is_correct"])

    record_quiz_attempt(
        db,
        {
            "user_id": user["id"],
            "card_id": question["card_id"],
            "session_id": session["id"],
            "is_correct": result["is_correct"],
            "answer": text,
        },
    )

    next_index = current_index + 1
    next_score = int(session.get("score") or 0) + (1 if result["is_correct"] else 0)
    update_quiz_session(db, session["id"], {"current_index": next_index, "score": next_score})

    response_parts = [format_quiz_correct() if result["is_correct"] else format_quiz_wrong(question["key_expression"])]
    if next_index < len(questions):
        response_parts.extend(["", format_quiz_question(questions[next_index], next_index + 1, len(questions))])
        send_long_message(bot, chat_id, "\n".join(response_parts))
        return

    update_quiz_session(
        db,
        session["id"],
        {
            "status": "completed",
            "completed_at": datetime.now(tz=timezone.utc).isoformat(),
        },
    )
    weak_cards = list_weak_cards(db, user["id"], 5)
    response_parts.extend(["", format_quiz_complete(next_score, len(questions), weak_cards)])
    send_long_message(bot, chat_id, "\n".join(response_parts))


def handle_telegram_update(*, config, db, bot: TelegramClient, update: dict):
    if mark_update_seen(update):
        return

    if get_update_callback_query(update):
        handle_callback_query(config=config, db=db, bot=bot, update=update)
        return

    text = get_message_text(update)
    message = update.get("message")
    if not message or not message.get("chat") or not message.get("from"):
        return

    chat_id = message["chat"]["id"]

    if is_command(text, "start"):
        send(bot, chat_id, start_message())
        try:
            upsert_user(db, message)
        except Exception as exc:  # noqa: BLE001
            print(f"Failed to upsert user on /start: {exc}")
        return

    if is_command(text, "test"):
        user = upsert_user(db, message)
        start_quiz_session(config=config, db=db, bot=bot, telegram_message=message)
        return

    if is_command(text, "review"):
        user = upsert_user(db, message)
        send_long_message(bot, chat_id, format_review_message(list_weak_cards(db, user["id"], 5)))
        return

    if is_command(text, "stats"):
        user = upsert_user(db, message)
        send(bot, chat_id, format_stats_message(get_user_stats(db, user["id"])))
        return

    if is_command(text, "history"):
        user = upsert_user(db, message)
        send(bot, chat_id, format_history_message(list_recent_shorts(db, user["id"], 5)))
        return

    if is_likely_url(text):
        handle_short_url(config=config, db=db, bot=bot, telegram_message=message, text=text)
        return

    user = upsert_user(db, message)

    selection = parse_expression_selection(text)
    if selection is not None:
        latest_short, latest_cards = get_latest_short_and_cards(db, user["id"])
        if latest_short and latest_cards:
            summary_cards = get_summary_cards(latest_short, latest_cards)
            if 1 <= selection <= len(summary_cards):
                handle_expression_selection_by_number(
                    config=config,
                    db=db,
                    bot=bot,
                    user=user,
                    chat_id=chat_id,
                    selection=selection,
                )
            else:
                send(bot, chat_id, f"1부터 {len(summary_cards)} 사이 번호를 선택해주세요.")
            return

    active_session = get_active_quiz_session(db, user["id"])
    if active_session:
        handle_quiz_answer(db=db, bot=bot, telegram_message=message, user=user, session=active_session, text=text)
        return

    send(bot, chat_id, start_message())
