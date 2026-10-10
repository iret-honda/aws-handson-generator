#!/usr/bin/env bash
# ジョブディレクトリを作成し、ジョブIDを標準出力に返す。
# 使い方: ./scripts/new-job.sh <service-slug> <level>   例: ./scripts/new-job.sh sqs intro
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <service-slug> <level>" >&2
  exit 1
fi

slug=$(echo "$1" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9\n' '-' | sed 's/--*/-/g; s/^-//; s/-$//')
level=$(echo "$2" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9\n' '-' | sed 's/--*/-/g; s/^-//; s/-$//')
date=$(date +%Y%m%d)
root="$(cd "$(dirname "$0")/.." && pwd)"

n=1
while [[ -d "$root/jobs/$slug-$level-$date-$(printf %02d $n)" ]]; do
  n=$((n + 1))
done
job_id="$slug-$level-$date-$(printf %02d $n)"

mkdir -p "$root/jobs/$job_id"
: > "$root/jobs/$job_id/phases.jsonl"
echo "$job_id"
