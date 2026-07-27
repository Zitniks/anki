-- +goose Up
CREATE TABLE theory_topic_progress (
    user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id     TEXT NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, topic_id)
);

-- +goose Down
DROP TABLE theory_topic_progress;
