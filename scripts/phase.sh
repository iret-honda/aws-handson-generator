#!/usr/bin/env bash
# フェーズの開始・終了時刻をジョブログ(phases.jsonl)に追記する。集計スクリプトはこの時刻でトークンを振り分ける。
# 使い方: ./scripts/phase.sh <job-id> <research|writing|verification|review> <start|end> [メモ]
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: $0 <job-id> <phase> <start|end> [note]" >&2
  exit 1
fi

job_id=$1 phase=$2 event=$3 note=${4:-}
root="$(cd "$(dirname "$0")/.." && pwd)"
log="$root/jobs/$job_id/phases.jsonl"

case "$phase" in research|writing|verification|review) ;; *) echo "unknown phase: $phase" >&2; exit 1 ;; esac
case "$event" in start|end) ;; *) echo "event must be start or end" >&2; exit 1 ;; esac
[[ -f "$log" ]] || { echo "job not found: $job_id" >&2; exit 1; }

python3 - "$log" "$phase" "$event" "$note" <<'PY'
import json, sys, datetime
log, phase, event, note = sys.argv[1:]
rec = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds"),
       "phase": phase, "event": event}
if note:
    rec["note"] = note
with open(log, "a") as f:
    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
print(json.dumps(rec, ensure_ascii=False))
PY
