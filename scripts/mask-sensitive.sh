#!/usr/bin/env bash
# コミット前に、ジョブの成果物から機密情報をマスキングする。対象は次のとおり。
#   - AWS アカウントID: AWS ドキュメントの例示値 123456789012 に置き換える(本文の規約と同じ値)。
#     本物のIDは jobs/<job-id>/input.json の accountId から読む。
#   - SQS の受信ハンドル(AQEB で始まる長い文字列): 先頭8文字 + "...(省略)" に短縮する。
#     先頭を残すのは、「前回と異なる」ことを記録から読み取れるようにするため。
#   - メッセージID(UUID 形式、検証シート内のみ): <message-id-N> に置き換える。同じIDには同じ番号を振る。
#     本文の出力例は架空のIDなので対象外。
#   - 検証シートの検証者欄: 実名を「検証者A」にする。
# input.json もマスキングするので、このスクリプトはコミット直前(ジョブの最後)に実行する。
# 使い方: ./scripts/mask-sensitive.sh <job-id> [追加でマスキングするアカウントID ...]
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <job-id> [account-id ...]" >&2
  exit 1
fi

root="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 - "$root" "$@" <<'PY'
import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
job_id = sys.argv[2]
extra_ids = sys.argv[3:]
PLACEHOLDER = "123456789012"
# テレメトリの生データと依存パッケージ・合成結果はコミットしないので対象外
SKIP_DIRS = {"node_modules", "cdk.out"}
SKIP_FILES = {"telemetry.json"}

ids = list(extra_ids)
input_json = root / "jobs" / job_id / "input.json"
if input_json.is_file():
    account = json.loads(input_json.read_text()).get("accountId") or ""
    if account and account != PLACEHOLDER:
        ids.append(account)
for i in ids:
    if not re.fullmatch(r"\d{12}", i):
        sys.exit(f"アカウントIDの形式ではありません: {i}")

dirs = [root / d for d in (f"jobs/{job_id}", f"handsons/{job_id}",
                           f".claude/skills/handson-writing/examples/{job_id}")]
files = [p for d in dirs if d.is_dir() for p in sorted(d.rglob("*"))
         if p.is_file() and p.name not in SKIP_FILES
         and not SKIP_DIRS.intersection(p.relative_to(d).parts)]

RECEIPT = re.compile(r"(AQEB[A-Za-z0-9+/=]{4})[A-Za-z0-9+/=]{32,}")
UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
VERIFIER = re.compile(r"^(\| 検証者 \| )(?!\(記入\)|検証者[A-Z] )[^|]+?( \|)$", re.M)
message_ids: dict[str, str] = {}
# 2回目以降の実行で番号が重ならないよう、既にある <message-id-N> の続きから振る
next_no = 1 + max((int(n) for f in files for n in re.findall(r"<message-id-(\d+)>",
                   f.read_text(errors="ignore"))), default=0)


def mask_uuid(m: re.Match) -> str:
    global next_no
    if m.group(0) not in message_ids:
        message_ids[m.group(0)] = f"<message-id-{next_no}>"
        next_no += 1
    return message_ids[m.group(0)]


for f in files:
    try:
        text = f.read_text()
    except UnicodeDecodeError:
        continue
    new = text
    for i in ids:
        new = new.replace(i, PLACEHOLDER)
    new = RECEIPT.sub(r"\1...(省略)", new)
    if "verification" in f.relative_to(root).parts and f.suffix == ".md":
        new = UUID.sub(mask_uuid, new)
        new = VERIFIER.sub(r"\1検証者A\2", new)
    if new != text:
        f.write_text(new)
        print(f"masked: {f.relative_to(root)}")
PY
