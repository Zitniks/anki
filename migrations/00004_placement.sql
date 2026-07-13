-- +goose Up
ALTER TABLE users ADD COLUMN cefr_level TEXT;

-- +goose Down
ALTER TABLE users DROP COLUMN cefr_level;
