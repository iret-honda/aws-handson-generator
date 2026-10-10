#!/usr/bin/env bash
# 手元の OpenTelemetry Collector を Docker で起動・停止する。
# 使い方: ./scripts/telemetry.sh up|down|status
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
name=handson-otelcol
image=otel/opentelemetry-collector-contrib:0.160.0

case "${1:-}" in
  up)
    mkdir -p "$root/telemetry/data"
    if docker ps --format '{{.Names}}' | grep -qx "$name"; then
      echo "already running: $name"
      exit 0
    fi
    docker rm -f "$name" >/dev/null 2>&1 || true
    docker run -d --name "$name" \
      -p 4317:4317 -p 4318:4318 \
      -v "$root/telemetry/otelcol-config.yaml:/etc/otelcol-contrib/config.yaml:ro" \
      -v "$root/telemetry/data:/data" \
      --user "$(id -u):$(id -g)" \
      "$image" >/dev/null
    echo "started: $name ($image)"
    ;;
  down)
    docker rm -f "$name" >/dev/null && echo "stopped: $name"
    ;;
  status)
    docker ps --filter "name=^${name}$" --format '{{.Names}} {{.Status}}'
    ls -l "$root/telemetry/data" 2>/dev/null || true
    ;;
  *)
    echo "usage: $0 up|down|status" >&2
    exit 1
    ;;
esac
