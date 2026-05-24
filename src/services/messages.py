from __future__ import annotations

from src.lib.text import normalize_whitespace
from src.lib.text import mask_expression
from src.lib.youtube import build_short_url


def start_message() -> str:
    return "\n".join(
        [
            "안녕하세요 👋",
            "",
            "YouTube Shorts 링크를 보내주세요.",
            "",
            "자동으로:",
            "- 문장 정리",
            "- 요약 카드 생성",
            "- 번호 선택 시 deep dive",
            "- Supabase 저장",
            "- 퀴즈 생성",
            "",
            "명령어:",
            "/test 오늘의 퀴즈",
            "/review 자주 틀린 표현",
            "/stats 약점 확인",
            "/history 최근 학습한 쇼츠",
        ]
    )


def format_learning_message(*, url: str, title: str | None, cards: list[dict], source: str | None = None) -> str:
    lines = ["🎬 Shorts English", "", f"🔗 영상: {url}"]
    if title:
        lines.append(f"📺 제목: {title}")
    lines.append("")

    for index, card in enumerate(cards[:3]):
        sentence = card.get("sentence") or card.get("english_text") or ""
        meaning_ko = card.get("meaning_ko") or card.get("korean_meaning") or ""
        key_expression = card.get("key_expression") or ""
        key_expression_meaning = (
            card.get("key_expression_meaning_ko")
            or card.get("key_expression_meaning")
            or ""
        )
        lines.extend(
            [
                f"{index + 1}. {sentence}",
                f"뜻: {meaning_ko}",
                f"핵심: {key_expression} = {key_expression_meaning}",
                "",
            ]
        )

    lines.append("👇 더 공부하고 싶은 번호 선택")
    return "\n".join(lines)


def _split_deep_explanation(text: str) -> tuple[str, str, str]:
    basic = ""
    figurative = ""
    extra_lines = []
    for raw_line in (text or "").splitlines():
        line = normalize_whitespace(raw_line)
        if not line:
            continue
        if line.startswith("기본 뜻:"):
            basic = normalize_whitespace(line.split("기본 뜻:", 1)[1])
            continue
        if line.startswith("비유적 의미:"):
            figurative = normalize_whitespace(line.split("비유적 의미:", 1)[1])
            continue
        extra_lines.append(line)
    return basic, figurative, "\n".join(extra_lines)


def format_deep_dive_message(expression: dict) -> str:
    key_expression = expression.get("expression") or expression.get("key_expression") or ""
    meaning_ko = expression.get("meaning_ko") or expression.get("key_expression_meaning_ko") or ""
    deep_explanation = expression.get("deep_explanation") or ""
    speaking_line = expression.get("speaking_line") or key_expression
    examples = expression.get("examples") or expression.get("examples_json") or []
    similar_expressions = expression.get("similar_expressions") or expression.get("similar_expressions_json") or []
    basic_meaning, figurative_meaning, extra_explanation = _split_deep_explanation(deep_explanation)

    lines = [f"📚 Deep Dive — {key_expression}", "", "핵심 표현:", key_expression, ""]

    if meaning_ko:
        lines.extend(["뜻:", meaning_ko, ""])

    if basic_meaning:
        lines.extend(["기본 뜻:", basic_meaning, ""])

    if figurative_meaning:
        lines.extend(["비유적 의미:", figurative_meaning, ""])

    if extra_explanation:
        lines.extend(["설명:", extra_explanation, ""])

    if examples:
        lines.extend(["예문:", ""])
        for index, example in enumerate(examples[:3], start=1):
            if isinstance(example, dict):
                example_en = normalize_whitespace(example.get("en") or example.get("english") or example.get("text"))
                example_ko = normalize_whitespace(example.get("ko") or example.get("meaning_ko") or example.get("meaning"))
            else:
                example_en = normalize_whitespace(example)
                example_ko = ""
            if not example_en:
                continue
            lines.append(f"{index}. {example_en}")
            if example_ko:
                lines.append(f"→ {example_ko}")
            lines.append("")

    if similar_expressions:
        lines.extend(["비슷한 표현:", ""])
        for item in similar_expressions[:4]:
            if isinstance(item, dict):
                text = normalize_whitespace(item.get("expression") or item.get("text"))
            else:
                text = normalize_whitespace(item)
            if text:
                lines.append(f"• {text}")
        lines.append("")

    if speaking_line:
        lines.extend(["🎤 따라 말하기:", "", speaking_line])

    return "\n".join(lines).strip()


def format_quiz_question(question: dict, position: int, total: int) -> str:
    return "\n".join(
        [
            f"📝 Today's Quiz ({position}/{total})",
            "",
            "뜻:",
            question["key_expression_meaning"],
            "",
            "빈칸:",
            mask_expression(question["key_expression"]),
        ]
    )


def format_quiz_correct() -> str:
    return "✅ Correct"


def format_quiz_wrong(expected: str) -> str:
    return "\n".join(["❌ Wrong", "", f"정답: {expected}"])


def format_quiz_complete(score: int, total: int, missed_cards: list[dict] | None = None) -> str:
    lines = ["🎉 Today's Result", "", "점수:", f"{score} / {total}"]
    missed_cards = missed_cards or []

    if missed_cards:
        lines.extend(["", "틀린 표현:"])
        for index, card in enumerate(missed_cards[:5], start=1):
            lines.extend(
                [
                    "",
                    f"{index}.",
                    card["key_expression"],
                    f"({int(card.get('wrong_count') or 0)}번 틀림)",
                ]
            )

    lines.extend(["", "내일 다시 출제 예정"])
    return "\n".join(lines)


def format_review_message(cards: list[dict]) -> str:
    if not cards:
        return "아직 틀린 표현이 없습니다."

    lines = ["🔁 Review", ""]
    for index, card in enumerate(cards, start=1):
        lines.extend(
            [
                f"{index}. {card['key_expression']}",
                f"뜻: {card['key_expression_meaning']}",
                f"틀린 횟수: {int(card.get('wrong_count') or 0)}",
                "",
            ]
        )
    return "\n".join(lines).strip()


def format_stats_message(stats: dict) -> str:
    return "\n".join(
        [
            "📊 Weak Expressions",
            "",
            f"쇼츠 수: {stats['shortCount']}",
            f"카드 수: {stats['cardCount']}",
            f"퀴즈 응답 수: {stats['attemptCount']}",
            f"정답률: {stats['accuracy']}%",
            f"약점 카드: {stats['weakCardCount']}",
        ]
    )


def format_history_message(shorts: list[dict]) -> str:
    if not shorts:
        return "최근 학습한 쇼츠가 없습니다."

    lines = ["📚 Recent Shorts", ""]
    for index, short in enumerate(shorts, start=1):
        lines.append(f"{index}. {short.get('title') or build_short_url(short['video_id'])}")
    return "\n".join(lines)
