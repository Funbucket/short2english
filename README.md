# Short2English

Telegram bot backend that turns YouTube Shorts into English learning cards and daily quiz sessions.

## What is implemented

- Telegram webhook server
- `/start`, `/test`, `/review`, `/stats`, `/history`
- YouTube Shorts URL parsing
- Best-effort YouTube transcript extraction
- Two-stage learning UX with summary cards and optional deep dive
- Inline keyboard and numeric selection for deep learning
- Supabase persistence
- Quiz session tracking

## Environment

Create a `.env` file with at least:

```bash
PORT=3000
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_WEBHOOK_URL=https://your-domain.example/telegram/webhook
TELEGRAM_WEBHOOK_SECRET=optional-secret-token

SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# Primary OpenAI settings
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4.1-mini
TRANSCRIPTION_MODEL=whisper-1
TRANSCRIPT_LANGUAGES=en

# Optional fallback for OpenAI-compatible providers.
LLM_CHAT_COMPLETIONS_URL=https://api.openai.com/v1/chat/completions
LLM_API_KEY=your-llm-api-key
LLM_MODEL=gpt-4o-mini
```

## Supabase schema

Apply the SQL in `supabase/schema.sql` before running the bot.
The schema includes `expressions` as a cache for deep-dive results.

## Run

```bash
python -m src.main
```

## Test

```bash
python -m unittest discover -s test
```

## Deploy

### Render

- `render.yaml` is included in the repo.
- Render injects `RENDER_EXTERNAL_URL`, so the app derives the Telegram webhook URL automatically.
- The service uses the native Python runtime, not Docker.
- Set the required secrets in the Render dashboard or Blueprint:
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_WEBHOOK_SECRET`
  - `SUPABASE_URL`
  - `SUPABASE_SERVICE_ROLE_KEY`
  - `OPENAI_API_KEY`
  - Optional: `OPENAI_MODEL`, `TRANSCRIPTION_MODEL`, `TRANSCRIPT_LANGUAGES`
  - Optional fallback: `LLM_CHAT_COMPLETIONS_URL`, `LLM_API_KEY`, `LLM_MODEL`
- Render will set `PORT=10000` from the Blueprint.
- Deploy by linking the repo to a Render Web Service or by applying the Blueprint.

### Telegram deployment checklist

1. Create a Telegram bot with `@BotFather` and copy the bot token.
2. Create a Supabase project and apply `supabase/schema.sql`.
3. Create a Render Web Service from this repo.
4. Add the required environment variables in Render:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_WEBHOOK_SECRET`
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `OPENAI_API_KEY`
5. Deploy the service.
6. After the first deploy, open the Render logs and confirm that `Telegram webhook set to .../telegram/webhook` appears.
7. Open the Telegram bot and send `/start`.
8. Send a YouTube Shorts URL.
9. Tap a number button or send `1`, `2`, or `3` to open the deep-dive card.

### Quick test commands

- Health check:
  - `curl https://YOUR-RENDER-URL/health`
- Webhook test:
  - After deployment, send a Telegram message to the bot and confirm the webhook receives it in Render logs.
- Deep-dive test:
  - Send a Shorts URL, then tap the inline button or send a number.

## Notes

- Transcript extraction tries `youtube_transcript_api` first, then falls back to `yt-dlp` + OpenAI audio transcription if `OPENAI_API_KEY` is set.
- Without an LLM configured, the bot still stores shorts and creates placeholder cards, but the Korean meaning fields will not be high quality.
- The first message is intentionally short. Users can tap a number button or send a number to open the deep-dive card for that expression.
