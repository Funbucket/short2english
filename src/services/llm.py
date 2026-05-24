from __future__ import annotations

import json
import re

from src.lib.http import request
from src.lib.text import normalize_whitespace, split_sentences


SUMMARY_CARD_LIMIT = 3

FALLBACK_EXPRESSION_PATTERNS = [
    {"regex": re.compile(r"out of the blue", re.IGNORECASE), "expression": "out of the blue", "meaning": "갑자기 / 뜬금없이"},
    {"regex": re.compile(r"my jam", re.IGNORECASE), "expression": "my jam", "meaning": "내가 좋아하는 것"},
    {"regex": re.compile(r"what do you think of", re.IGNORECASE), "expression": "What do you think of ~?", "meaning": "~에 대해 어떻게 생각해?"},
    {"regex": re.compile(r"come on", re.IGNORECASE), "expression": "come on", "meaning": "설마 / 그만해"},
]


def safe_json_loads(content: str):
    text = str(content or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))

        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            return json.loads(text[first_brace : last_brace + 1])

        raise


def _fallback_key_expression(sentence: str) -> dict[str, str]:
    for pattern in FALLBACK_EXPRESSION_PATTERNS:
        if pattern["regex"].search(sentence):
            return {"expression": pattern["expression"], "meaning": pattern["meaning"]}

    words = [word for word in normalize_whitespace(sentence).split() if word]
    if not words:
        return {"expression": "key expression", "meaning": "핵심 표현"}

    return {
        "expression": " ".join(words[: min(4, len(words))]),
        "meaning": "LLM 설정이 없어 자동 번역을 생성하지 못했습니다.",
    }


def _fallback_cards(transcript_text: str) -> list[dict]:
    sentences = split_sentences(transcript_text)[:SUMMARY_CARD_LIMIT]
    cards = []
    for sentence in sentences[:SUMMARY_CARD_LIMIT]:
        key = _fallback_key_expression(sentence)
        cards.append(
            {
                "sentence": sentence,
                "meaning_ko": "LLM 설정이 없어 임시 카드입니다.",
                "key_expression": key["expression"],
                "key_expression_meaning_ko": key["meaning"],
            }
        )
    return cards


def _normalize_card(card: dict) -> dict:
    return {
        "sentence": normalize_whitespace(card.get("sentence") or card.get("english_text")),
        "meaning_ko": normalize_whitespace(card.get("meaning_ko") or card.get("korean_meaning")),
        "key_expression": normalize_whitespace(card.get("key_expression")),
        "key_expression_meaning_ko": normalize_whitespace(
            card.get("key_expression_meaning_ko") or card.get("key_expression_meaning")
        ),
    }


def _normalize_example(example: object) -> dict[str, str]:
    if isinstance(example, dict):
        return {
            "en": normalize_whitespace(example.get("en") or example.get("english") or example.get("text")),
            "ko": normalize_whitespace(example.get("ko") or example.get("meaning_ko") or example.get("meaning")),
        }

    text = normalize_whitespace(str(example or ""))
    return {"en": text, "ko": ""}


def _normalize_multiline_text(value: object) -> str:
    lines = [normalize_whitespace(line) for line in str(value or "").splitlines()]
    return "\n".join(line for line in lines if line)


def _normalize_expression_result(result: dict, *, card: dict) -> dict:
    expression = normalize_whitespace(result.get("expression") or card.get("key_expression"))
    meaning_ko = normalize_whitespace(result.get("meaning_ko") or card.get("key_expression_meaning_ko"))
    deep_explanation = _normalize_multiline_text(result.get("deep_explanation") or "")
    speaking_line = normalize_whitespace(result.get("speaking_line") or expression)
    examples = [_normalize_example(item) for item in (result.get("examples") or [])]
    examples = [item for item in examples if item["en"]]
    similar_expressions = [
        normalize_whitespace(item.get("expression") or item.get("text") or item)
        for item in (result.get("similar_expressions") or [])
    ]
    similar_expressions = [item for item in similar_expressions if item]

    return {
        "expression": expression,
        "meaning_ko": meaning_ko,
        "deep_explanation": deep_explanation,
        "examples": examples[:4],
        "similar_expressions": similar_expressions[:5],
        "speaking_line": speaking_line,
    }


def _openai_chat_completion(prompt: list[dict], *, api_key: str, model: str) -> dict:
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("openai package is not installed") from exc

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=prompt,
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or ""
    return safe_json_loads(content)


def _http_chat_completion(config, prompt: list[dict]) -> dict:
    response = request(
        "POST",
        config.llm_chat_completions_url,
        headers={
            "authorization": f"Bearer {config.llm_api_key}",
            "content-type": "application/json",
        },
        body=json.dumps(
            {
                "model": config.llm_model,
                "messages": prompt,
                "temperature": 0.2,
            }
        ).encode("utf-8"),
    )
    if response.status >= 400:
        raise RuntimeError(f"LLM request failed ({response.status}): {response.text}")

    data = json.loads(response.text or "{}")
    content = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content") or ""
    if not content:
        raise RuntimeError("LLM returned an empty response")

    return safe_json_loads(content)


def _build_prompt(*, video_id: str, title: str | None, transcript_text: str) -> list[dict]:
    return [
        {
            "role": "user",
            "content": "\n".join(
                [
                    "You are an English learning assistant for Korean learners.",
                    "",
                    "Clean the transcript and convert meaningful spoken English into short Telegram learning cards.",
                    "",
                    "Rules:",
                    "- Preserve original order.",
                    "- Ignore [Applause], filler noise, repeated fragments, and broken text.",
                    "- Remove sentences that appear corrupted, incomplete, or likely mis-transcribed.",
                    "- Remove sentences with low English learning value.",
                    "- Keep cards short and mobile-friendly.",
                    "",
                    "Learning value rules:",
                    "Only keep expressions useful for real English learning:",
                    "- common spoken expressions",
                    "- conversational patterns",
                    "- slang",
                    "- idioms",
                    "- sentence patterns",
                    "- frequently used phrases",
                    "",
                    "Avoid:",
                    "- names only",
                    "- isolated facts",
                    "- random entities",
                    "- obvious words",
                    "- low-value vocabulary",
                    "- likely transcription mistakes",
                    "",
                    "Interpretation rules:",
                    "- Interpret meaning using surrounding context.",
                    "- Never translate literally for slang, memes, or spoken English.",
                    "- Prefer spoken meaning over dictionary meaning.",
                    "- Prefer phrase meaning over word meaning.",
                    "- If a word belongs to a phrase, extract the whole phrase.",
                    "- Choose the most natural spoken interpretation.",
                    "",
                    "Return JSON only.",
                    "",
                    "JSON format:",
                    '{',
                    '  "cards": [',
                    '    {',
                    '      "sentence":"...",',
                    '      "meaning_ko":"...",',
                    '      "key_expression":"...",',
                    '      "key_expression_meaning_ko":"..."',
                    '    }',
                    '  ]',
                    '}',
                    "",
                    f"Video ID: {video_id}",
                    f"Title: {title or 'Unknown title'}",
                    "",
                    "Transcript:",
                    transcript_text,
                ]
            ),
        }
    ]


def _parse_cards(result: dict) -> list[dict]:
    cards = result.get("cards") if isinstance(result, dict) else []
    normalized = [_normalize_card(card) for card in cards or []]
    return [
        card
        for card in normalized
        if card["sentence"] and card["meaning_ko"] and card["key_expression"] and card["key_expression_meaning_ko"]
    ][:SUMMARY_CARD_LIMIT]


def _build_expression_prompt(*, card: dict) -> list[dict]:
    return [
        {
            "role": "user",
            "content": "\n".join(
                [
                    "You are an English learning assistant for Korean learners.",
                    "",
                    "Turn one short learning card into a deep-dive explanation for Telegram.",
                    "",
                    "Rules:",
                    "- Focus on the selected expression.",
                    "- Explain the basic meaning first, then the figurative or natural spoken meaning.",
                    "- Keep it concise and mobile-friendly.",
                    "- Give 2 to 4 realistic examples.",
                    "- Provide 2 to 4 similar expressions.",
                    "- Keep the speaking line short and natural.",
                    "",
                    "Return JSON only.",
                    "",
                    "JSON format:",
                    "{",
                    '  "expression": "...",',
                    '  "meaning_ko": "...",',
                    '  "deep_explanation": "기본 뜻: ...\\n비유적 의미: ...",',
                    '  "examples": [',
                    '    {"en": "...", "ko": "..."}',
                    "  ],",
                    '  "similar_expressions": ["...", "..."],',
                    '  "speaking_line": "..."',
                    "}",
                    "",
                    "Card:",
                    json.dumps(
                        {
                            "sentence": card.get("sentence") or card.get("english_text") or "",
                            "meaning_ko": card.get("meaning_ko") or card.get("korean_meaning") or "",
                            "key_expression": card.get("key_expression") or "",
                            "key_expression_meaning_ko": card.get("key_expression_meaning_ko")
                            or card.get("key_expression_meaning")
                            or "",
                        },
                        ensure_ascii=False,
                    ),
                ]
            ),
        }
    ]


def generate_learning_cards(*, config, video_id: str, title: str | None, transcript_text: str) -> dict:
    if config.openai_api_key:
        try:
            result = _openai_chat_completion(
                _build_prompt(video_id=video_id, title=title, transcript_text=transcript_text),
                api_key=config.openai_api_key,
                model=config.openai_model,
            )
            cards = _parse_cards(result)
            if cards:
                return {"source": "openai", "cards": cards}
        except Exception:
            pass

    if config.llm_chat_completions_url and config.llm_api_key and config.llm_model:
        try:
            result = _http_chat_completion(
                config,
                _build_prompt(video_id=video_id, title=title, transcript_text=transcript_text),
            )
            cards = _parse_cards(result)
            if cards:
                return {"source": "llm", "cards": cards}
        except Exception:
            pass

    return {"source": "fallback", "cards": _fallback_cards(transcript_text)}


def _fallback_deep_dive(card: dict) -> dict:
    expression = normalize_whitespace(card.get("key_expression") or card.get("sentence") or "")
    meaning_ko = normalize_whitespace(card.get("key_expression_meaning_ko") or card.get("key_expression_meaning") or "")
    sentence = normalize_whitespace(card.get("sentence") or card.get("english_text") or "")
    sentence_meaning = normalize_whitespace(card.get("meaning_ko") or card.get("korean_meaning") or meaning_ko)
    return {
        "expression": expression,
        "meaning_ko": meaning_ko or sentence_meaning,
        "deep_explanation": "\n".join(
            [
                f"기본 뜻: {meaning_ko or sentence_meaning or '핵심 표현입니다.'}",
                f"비유적 의미: {sentence_meaning or '문맥에 따라 자연스럽게 해석하세요.'}",
            ]
        ),
        "examples": [{"en": sentence or expression, "ko": sentence_meaning or meaning_ko or ""}],
        "similar_expressions": [],
        "speaking_line": expression or sentence,
    }


def generate_expression_deep_dive(*, config, card: dict) -> dict:
    if config.openai_api_key:
        try:
            result = _openai_chat_completion(
                _build_expression_prompt(card=card),
                api_key=config.openai_api_key,
                model=config.openai_model,
            )
            payload = _normalize_expression_result(result, card=card)
            if payload["expression"] and payload["meaning_ko"]:
                return {"source": "openai", **payload}
        except Exception:
            pass

    if config.llm_chat_completions_url and config.llm_api_key and config.llm_model:
        try:
            result = _http_chat_completion(config, _build_expression_prompt(card=card))
            payload = _normalize_expression_result(result, card=card)
            if payload["expression"] and payload["meaning_ko"]:
                return {"source": "llm", **payload}
        except Exception:
            pass

    return {"source": "fallback", **_fallback_deep_dive(card)}
