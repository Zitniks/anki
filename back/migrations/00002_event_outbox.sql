-- +goose Up
CREATE TABLE event_outbox (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    word_id           BIGINT NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    card_type         TEXT NOT NULL,
    correct           BOOLEAN NOT NULL,
    response_time_ms  INTEGER,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at      TIMESTAMPTZ,
    publish_attempts  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_event_outbox_unpublished ON event_outbox (created_at) WHERE published_at IS NULL;

-- +goose Down
DROP TABLE IF EXISTS event_outbox;
