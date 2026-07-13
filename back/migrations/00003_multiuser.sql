-- +goose Up
CREATE TABLE users (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE words ADD COLUMN user_id BIGINT REFERENCES users(id) ON DELETE CASCADE;

INSERT INTO users (id, email, password_hash) OVERRIDING SYSTEM VALUE VALUES (1, 'local@anki', '');
UPDATE words SET user_id = 1 WHERE user_id IS NULL;

ALTER TABLE words ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE words DROP CONSTRAINT words_word_key;
ALTER TABLE words ADD CONSTRAINT words_user_word_unique UNIQUE (user_id, word);
CREATE INDEX idx_words_user_id ON words (user_id);

-- +goose Down
DROP INDEX IF EXISTS idx_words_user_id;
ALTER TABLE words DROP CONSTRAINT IF EXISTS words_user_word_unique;
ALTER TABLE words ADD CONSTRAINT words_word_key UNIQUE (word);
ALTER TABLE words DROP COLUMN user_id;
DROP TABLE IF EXISTS users;
