-- +goose Up
CREATE TABLE words (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    word          TEXT UNIQUE NOT NULL,
    translation   TEXT NOT NULL,
    example       TEXT,
    transcription TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE cards (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    word_id    BIGINT NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    type       TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (word_id, type)
);

CREATE INDEX idx_cards_word_type ON cards (word_id, type);

-- 'interval' is a reserved word in Postgres -> interval_days.
CREATE TABLE review_state (
    card_id       BIGINT PRIMARY KEY REFERENCES cards(id) ON DELETE CASCADE,
    repetition    INTEGER NOT NULL DEFAULT 0,
    interval_days INTEGER NOT NULL DEFAULT 1,
    ease_factor   DOUBLE PRECISION NOT NULL DEFAULT 2.5,
    next_review   TIMESTAMPTZ NOT NULL,
    correct_count INTEGER NOT NULL DEFAULT 0,
    wrong_count   INTEGER NOT NULL DEFAULT 0,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    status        TEXT NOT NULL DEFAULT 'new',
    learning_step INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_review_state_next_review ON review_state (next_review);
CREATE INDEX idx_review_state_status_next ON review_state (status, next_review);

CREATE TABLE review_log (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    card_id            BIGINT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    word_id            BIGINT NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    quality            INTEGER,
    rating             TEXT,
    interval_after     INTEGER,
    ease_factor_after  DOUBLE PRECISION,
    response_time_ms   INTEGER,
    reviewed_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_review_log_word_id ON review_log (word_id);
CREATE INDEX idx_review_log_reviewed_at ON review_log (reviewed_at);

-- +goose Down
DROP TABLE IF EXISTS review_log;
DROP TABLE IF EXISTS review_state;
DROP TABLE IF EXISTS cards;
DROP TABLE IF EXISTS words;
