#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROTO_DIR="$ROOT/proto"
OUT_DIR="$ROOT/src/grpc_svc/pb"
GRPC_PROTO="$(uv run python -c "import grpc_tools, os; print(os.path.join(os.path.dirname(grpc_tools.__file__), '_proto'))")"

mkdir -p "$OUT_DIR/tutor/v1"
uv run python -m grpc_tools.protoc \
  -I "$PROTO_DIR" -I "$GRPC_PROTO" \
  --python_out="$OUT_DIR" \
  --grpc_python_out="$OUT_DIR" \
  --pyi_out="$OUT_DIR" \
  "$PROTO_DIR/tutor/v1/tutor.proto"

# Fix import path in generated grpc stub.
sed -i '' 's/from tutor.v1 import tutor_pb2/from grpc_svc.pb.tutor.v1 import tutor_pb2/' \
  "$OUT_DIR/tutor/v1/tutor_pb2_grpc.py" 2>/dev/null || \
sed -i 's/from tutor.v1 import tutor_pb2/from grpc_svc.pb.tutor.v1 import tutor_pb2/' \
  "$OUT_DIR/tutor/v1/tutor_pb2_grpc.py"

echo "generated into $OUT_DIR"
