from __future__ import annotations

import html
import re


def normalize_whitespace(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_answer(value: object) -> str:
    text = normalize_whitespace(value).lower()
    text = re.sub(r"[^\w\s'\-]+", "", text, flags=re.UNICODE)
    text = text.replace("_", "")
    return re.sub(r"\s+", " ", text).strip()


def decode_html_entities(value: object) -> str:
    return html.unescape(str(value or ""))


def mask_expression(expression: object) -> str:
    words = normalize_whitespace(expression).split()
    masked_words = [re.sub(r"[A-Za-z0-9]", "_", word) for word in words if word]
    return " ".join(masked_words)


def split_sentences(text: object) -> list[str]:
    normalized = normalize_whitespace(text).replace("\r", " ").replace("\n", " ")
    if not normalized:
        return []

    parts = re.split(r"(?<=[.!?])\s+", normalized)
    if len(parts) == 1:
        parts = [normalized]
    seen: set[str] = set()
    result: list[str] = []
    for part in parts:
        sentence = normalize_whitespace(part)
        if sentence and sentence not in seen:
            seen.add(sentence)
            result.append(sentence)
    return result


def clean_transcript_text(text: object) -> str:
    normalized = str(text or "")
    normalized = re.sub(r"\[(?:music|applause|laughter|laughs|inaudible|silence|music playing)\]", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\((?:music|applause|laughter|laughs|inaudible|silence)\)", "", normalized, flags=re.IGNORECASE)
    normalized = normalize_whitespace(normalized)

    sentences = split_sentences(normalized)
    cleaned: list[str] = []
    previous = ""
    for sentence in sentences:
        if sentence == previous:
            continue
        cleaned.append(sentence)
        previous = sentence

    return normalize_whitespace(" ".join(cleaned))
