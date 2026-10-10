#!/usr/bin/env bash
# 取りこぼし対策: handson-job-id タグが付いて24時間以上経ったリソースだけを消す(設定の tagging.staleHours)。
# 既定は一覧だけ。消すときは --execute を付ける。タグのないリソースには触れない(aws-nuke 系は使わない)。
# 使い方: ./scripts/cleanup-stale.sh <profile> <region> [--execute] [--hours <時間>]
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
exec uv run --quiet --project "$root/mcp/sandbox-runner" sandbox-runner-stale "$@"
