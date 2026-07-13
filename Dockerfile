########################################
# Stage 1 — build the landing page (Vite/React)
########################################
FROM node:22-bookworm-slim AS landing-build
WORKDIR /src/landing
COPY front/landing/package.json front/landing/package-lock.json ./
RUN npm ci
COPY front/landing/ ./
RUN npm run build

########################################
# Stage 2 — build the Go server + goose migration CLI
########################################
FROM golang:1.25-bookworm AS go-build
WORKDIR /src
COPY back/go.mod back/go.sum ./
RUN go mod download
COPY back/cmd/ ./cmd/
COPY back/internal/ ./internal/
RUN CGO_ENABLED=0 go build -o /out/server ./cmd/server
# goose isn't a dependency of this module, so install it standalone (its own
# module graph) rather than `go build`, which would try to fold it into go.mod.
RUN CGO_ENABLED=0 GOBIN=/out go install github.com/pressly/goose/v3/cmd/goose@latest

########################################
# Stage 3 — slim runtime image
########################################
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app

COPY --from=go-build /out/server ./server
COPY --from=go-build /out/goose ./goose
COPY --from=landing-build /src/landing/dist ./landing/dist
COPY front/web/ ./web/
COPY back/migrations/ ./migrations/
COPY back/theory_tenses.json back/word_topics.json back/book_norwood_builder.json ./
COPY docker-entrypoint.sh ./
RUN chmod +x ./docker-entrypoint.sh ./server ./goose

EXPOSE 8080
ENTRYPOINT ["./docker-entrypoint.sh"]
