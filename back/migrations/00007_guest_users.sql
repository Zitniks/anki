-- +goose Up
ALTER TABLE users ADD COLUMN is_guest BOOLEAN NOT NULL DEFAULT false;

-- +goose Down
ALTER TABLE users DROP COLUMN is_guest;
