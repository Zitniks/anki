########################################
# Stage 1 — build the landing page (Vite/React)
########################################
FROM node:22-bookworm-slim AS landing-build
WORKDIR /src/landing
COPY landing/package.json landing/package-lock.json ./
RUN npm ci
COPY landing/ ./
RUN npm run build

########################################
# Stage 2 — build the Go server + goose migration CLI
########################################
FROM golang:1.25-bookworm AS go-build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY cmd/ ./cmd/
COPY internal/ ./internal/
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
COPY web/ ./web/
COPY migrations/ ./migrations/
COPY theory_tenses.json word_topics.json book_norwood_builder.json ./
COPY docker-entrypoint.sh ./
RUN chmod +x ./docker-entrypoint.sh ./server ./goose

EXPOSE 8080
ENTRYPOINT ["./docker-entrypoint.sh"]
