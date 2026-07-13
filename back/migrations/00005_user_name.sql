-- +goose Up
ALTER TABLE users ADD COLUMN name TEXT;

-- +goose Down
ALTER TABLE users DROP COLUMN name;
