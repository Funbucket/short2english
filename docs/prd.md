# PRD — Short2English v1.0

## 1. Overview

### Product Name

Short2English

### One-line Summary

> Turn YouTube Shorts into English learning cards and daily quiz sessions through Telegram.
> 

### Vision

영어 공부 시간을 따로 만드는 것이 아니라, 사용자가 이미 소비하는 콘텐츠를 자동으로 학습 데이터로 변환한다.

---

## 2. Problem

기존 영어 학습 문제:

- 무엇을 공부할지 매번 결정해야 한다
- 재미있는 콘텐츠와 학습이 분리되어 있다
- 표현을 봐도 기억에 남지 않는다
- 입력(input)은 많지만 출력(output)은 적다
- 앱 설치 후 지속적으로 사용하기 어렵다

현재 행동:

```
영어 쇼츠 시청
      ↓
재밌게 보고 끝
```

목표 행동:

```
영어 쇼츠 공유
      ↓
자동 학습 카드 생성
      ↓
짧게 읽기
      ↓
매일 퀴즈
      ↓
반복 학습
```

---

## 3. Goals

### Primary Goal

영어 콘텐츠 소비를 자동 학습 루프로 전환

### Success Definition

사용자가:

```
쇼츠 링크 공유
↓
학습 카드 확인
↓
매일 /test 수행
↓
반복적으로 표현 습득
```

---

## 4. Target User

Primary User:

- 영어 회화가 부족한 사람
- 영어 쇼츠를 자주 보는 사람
- 공부 루틴 유지가 어려운 사람
- 짧고 빠른 학습 선호
- Telegram 사용 가능

---

## 5. User Flow

### Initial Entry

사용자:

```
/start
```

Bot:

```
안녕하세요 👋

YouTube Shorts 링크를 보내주세요.

자동으로:

✅ 문장 정리
✅ 뜻 생성
✅ 핵심 표현 추출
✅ 학습 저장
✅ 퀴즈 생성
```

---

### Learning Flow

사용자:

```
https://youtube.com/shorts/xxxxx
```

Backend:

```
URL 수신
↓
video_id 추출
↓
Transcript 추출
↓
Transcript 정리
↓
LLM 처리
↓
문장 생성
↓
Supabase DB 저장
↓
Telegram 응답
```

Bot:

```
🎬 Shorts English

🔗 영상:
https://youtube.com/shorts/xxxxx

1.

He calls me out of the blue one day.

뜻:
어느 날 갑자기 그가 나에게 전화했어.

핵심:
out of the blue
=
갑자기 / 뜬금없이

---

2.

This is my jam.

뜻:
이거 완전 내 취향이야.

핵심:
my jam
=
내가 좋아하는 것

---

3.

What do you think of that girl?

뜻:
저 여자애 어떻게 생각해?

핵심:
What do you think of ~?
=
~에 대해 어떻게 생각해?

🎤 전체 문장을 한번 읽어보세요
```

---

## 6. Daily Quiz Flow

사용자:

```
/test
```

Backend:

```
사용자 학습 기록 조회
↓
우선순위 계산
↓
오늘의 퀴즈 세트 생성
↓
5~10문제 선택
```

문제 구성:

```
40% 자주 틀린 표현
30% 최근 학습 표현
30% 오래 안 본 표현
```

우선순위 계산:

```
priority_score= (
wrong_count*3
-correct_count
+days_since_last_tested
)
```

Bot:

```
📝 Today's Quiz (1/7)

뜻:

갑자기 / 뜬금없이

빈칸:

He called me _____ _____ _____ one day.
```

사용자:

```
out of the blue
```

Bot:

```
✅ Correct

다음 문제 (2/7)
```

퀴즈 종료:

```
🎉 Today's Result

점수:
6 / 7

틀린 표현:

1.
out of the blue
(3번 틀림)

2.
come on
(2번 틀림)

내일 다시 출제 예정
```

---

## 7. Commands

### `/start`

초기 안내

### `/test`

오늘의 퀴즈 (5~10문항)

### `/review`

자주 틀린 표현 복습

### `/stats`

약점 표현 확인

예:

```
📊 Weak Expressions

1.
out of the blue
틀린 횟수: 4

2.
come on
틀린 횟수: 3
```

### `/history`

최근 학습한 쇼츠

예:

```
📚 Recent Shorts

1. Key & Peele
2. Daily Vlog
3. TED Clip
```

---

## 8. Functional Requirements

### F1. URL Detection

지원:

```
youtube.com/shorts/
youtube.com/watch
youtu.be
```

---

### F2. Transcript Extraction

우선순위:

```
1. YouTube Transcript API
2. Whisper fallback
```

---

### F3. Transcript Cleanup

제거:

- `[Applause]`
- filler words
- duplicated fragments
- broken text

---

### F4. Learning Card Generation

규칙:

- 의미 있는 모든 문장 처리
- 원래 순서 유지
- 문장당 핵심 표현 하나
- 모바일 친화적 출력
- 짧은 카드 유지

Output:

```
[
{
"sentence":"...",
"meaning_ko":"...",
"key_expression":"...",
"key_expression_meaning_ko":"..."
}
]
```

---

### F5. Telegram Formatting

규칙:

- 최소 스크롤
- 긴 메시지 자동 분할
- 모바일 최적화

---

### F6. Quiz Generation

지원:

- 5~10문항 세션
- 빈칸 문제
- 정답 체크
- 점수 계산
- 정답/오답 저장
- 오답 우선 재출제

---

## 9. Architecture

```
Telegram

↓ webhook

Vercel FastAPI

↓

URL Detection

↓

Transcript API

↓

OpenAI API

↓

Sentence Generator

↓

Database

↓

Telegram Response
```

---

## 10. Database Schema

### users

```
id
telegram_id
username
created_at
```

---

### videos

```
id
video_id
youtube_url
title
transcript
created_at
```

---

### sentences

영상의 문장 단위 저장

```
id
video_id
order_index
sentence
meaning_ko
created_at
```

예:

```
video: Key & Peele clip

1:
He calls me out of the blue one day.

2:
This is my jam.
```

---

### expressions

문장 내 핵심 표현 저장

```
id
sentence_id
expression
meaning_ko
created_at
```

예:

```
sentence:
He calls me out of the blue one day.

expression:
out of the blue
```

---

### user_sentence_learning

사용자별 학습 상태

```
id
user_id
sentence_id
correct_count
wrong_count
last_tested_at
created_at
```

---

### quiz_sessions

퀴즈 기록

```
id
user_id
score
total_count
created_at
```

---

### quiz_answers

문제별 응답 기록

```
id
quiz_session_id
sentence_id
expression_id
question
user_answer
correct_answer
is_correct
created_at
```

---

## 11. Success Metrics

### North Star Metric

```
Weekly completed quizzes
```

Supporting Metrics:

Usage:

```
Short links/day
Cards generated/day
```

Retention:

```
D1
D7
D30
```

Learning:

```
Average wrong_count decrease
```

---

## Core Product Principle

> Don't ask users to study English. Turn what they already watch into learning automatically.
>
