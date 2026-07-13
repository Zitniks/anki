#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROTO_DIR="$ROOT/proto"
OUT_DIR="$ROOT/internal/ai/pb"

mkdir -p "$OUT_DIR"

protoc \
  -I "$PROTO_DIR" \
  -I "$(go env GOPATH)/pkg/mod/$(go list -m -f '{{.Path}}@{{.Version}}' google.golang.org/protobuf 2>/dev/null || echo 'google.golang.org/protobuf@v1.34.1')" \
  --go_out="$OUT_DIR" --go_opt=paths=source_relative \
  --go-grpc_out="$OUT_DIR" --go-grpc_opt=paths=source_relative \
  "$PROTO_DIR/tutor/v1/tutor.proto"

echo "generated into $OUT_DIR"
