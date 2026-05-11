-- Housing Assistant — Lakebase OLTP schema
-- Run idempotently: all statements use IF NOT EXISTS.
-- Database: housing_app  Schema: public

CREATE TABLE IF NOT EXISTS users (
  user_id      TEXT        PRIMARY KEY,
  email        TEXT        UNIQUE NOT NULL,
  display_name TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per user; budget and commute preferences live here.
CREATE TABLE IF NOT EXISTS user_constraints (
  user_id           TEXT        PRIMARY KEY REFERENCES users (user_id) ON DELETE CASCADE,
  budget_weekly_max INTEGER,                -- NZD
  household_size    SMALLINT,
  has_pets          BOOLEAN,
  work_location     TEXT,                   -- canonical suburb name or "lat,lon"
  preferred_modes   TEXT[],                 -- e.g. ARRAY['transit','walk']
  max_commute_mins  SMALLINT,
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS saved_searches (
  search_id  TEXT        PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
  user_id    TEXT        NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
  name       TEXT        NOT NULL,
  query_json JSONB       NOT NULL,          -- serialised agent query parameters
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS alerts (
  alert_id       TEXT        PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
  user_id        TEXT        NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
  search_id      TEXT        REFERENCES saved_searches (search_id) ON DELETE SET NULL,
  threshold_json JSONB,                     -- e.g. {"max_rent_weekly": 750}
  channel        TEXT        NOT NULL CHECK (channel IN ('email', 'webhook')),
  channel_target TEXT        NOT NULL,      -- email address or webhook URL
  is_active      BOOLEAN     NOT NULL DEFAULT TRUE,
  last_fired_at  TIMESTAMPTZ,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Full conversation history; used for context re-warming and debugging.
CREATE TABLE IF NOT EXISTS conversation_turns (
  turn_id    TEXT        PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
  user_id    TEXT        NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
  session_id TEXT        NOT NULL,
  role       TEXT        NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
  content    TEXT        NOT NULL,
  tool_calls JSONB,                         -- raw tool call objects for assistant/tool turns
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conv_turns_user_session
  ON conversation_turns (user_id, session_id, created_at);
