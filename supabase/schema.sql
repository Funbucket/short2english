create extension if not exists pgcrypto;

create table if not exists public.users (
  id uuid primary key default gen_random_uuid(),
  telegram_user_id bigint not null unique,
  telegram_chat_id bigint not null,
  username text,
  first_name text,
  last_name text,
  created_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now()
);

create table if not exists public.shorts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  video_id text not null,
  url text not null,
  title text,
  transcript_source text,
  transcript_text text,
  processing_status text not null default 'completed',
  error_message text,
  created_at timestamptz not null default now()
);

create index if not exists shorts_user_id_created_at_idx
  on public.shorts (user_id, created_at desc);

create index if not exists shorts_user_video_id_idx
  on public.shorts (user_id, video_id);

alter table public.users
  add column if not exists active_short_id uuid;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'users_active_short_id_fkey'
  ) then
    alter table public.users
      add constraint users_active_short_id_fkey
      foreign key (active_short_id)
      references public.shorts(id)
      on delete set null;
  end if;
end $$;

create table if not exists public.cards (
  id uuid primary key default gen_random_uuid(),
  short_id uuid not null references public.shorts(id) on delete cascade,
  user_id uuid not null references public.users(id) on delete cascade,
  sequence int not null,
  english_text text not null,
  korean_meaning text not null,
  key_expression text not null,
  key_expression_meaning text not null,
  correct_count int not null default 0,
  wrong_count int not null default 0,
  last_tested_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists cards_user_id_created_at_idx
  on public.cards (user_id, created_at desc);

create index if not exists cards_user_id_wrong_count_idx
  on public.cards (user_id, wrong_count desc, correct_count asc);

create table if not exists public.expressions (
  id uuid primary key default gen_random_uuid(),
  sentence_id uuid not null references public.cards(id) on delete cascade,
  expression text not null,
  meaning_ko text not null,
  deep_explanation text not null,
  examples_json jsonb not null default '[]'::jsonb,
  similar_expressions_json jsonb not null default '[]'::jsonb,
  speaking_line text not null,
  created_at timestamptz not null default now(),
  unique (sentence_id)
);

create index if not exists expressions_sentence_id_idx
  on public.expressions (sentence_id, created_at desc);

create table if not exists public.quiz_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  telegram_chat_id bigint not null,
  status text not null default 'active',
  questions jsonb not null,
  current_index int not null default 0,
  score int not null default 0,
  total_questions int not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz
);

create index if not exists quiz_sessions_user_status_idx
  on public.quiz_sessions (user_id, status, created_at desc);

create table if not exists public.quiz_attempts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  card_id uuid not null references public.cards(id) on delete cascade,
  session_id uuid references public.quiz_sessions(id) on delete set null,
  quiz_date date not null default current_date,
  is_correct boolean not null,
  answer text,
  created_at timestamptz not null default now()
);

create index if not exists quiz_attempts_user_date_idx
  on public.quiz_attempts (user_id, quiz_date desc);

create index if not exists quiz_attempts_card_idx
  on public.quiz_attempts (card_id, created_at desc);
