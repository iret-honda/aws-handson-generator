#!/usr/bin/env python3
"""ゲート2(後片付け漏れなしで連続合格)の達成状況を表示する。

各ジョブの検証ラウンドの結果(jobs/<job-id>/verification/round-<n>.json、検証担当が書く)を時刻順に並べ、
直近から数えて「合格かつ後片付け後のタグ付きリソース0件」が何回続いているかを数える。
必要な回数は config/handson.config.json の gate2.requiredConsecutivePasses。

使い方: python3 scripts/gate-status.py [--json]
終了コード: 0 = 達成、3 = 未達成
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    required = json.loads((ROOT / "config" / "handson.config.json").read_text())["gate2"]["requiredConsecutivePasses"]
    rows = []
    for f in sorted(ROOT.glob("jobs/*/verification/round-*.json")):
        r = json.loads(f.read_text())
        if r.get("mode") != "auto":
            continue  # フェーズ1の手動検証は数えない
        ok = r.get("result") == "pass" and r.get("cleanup", {}).get("remainingCount") == 0
        rows.append({"file": str(f.relative_to(ROOT)), "jobId": r.get("jobId"), "round": r.get("round"),
                     "endedAt": r.get("endedAt") or "", "result": r.get("result"),
                     "remaining": r.get("cleanup", {}).get("remainingCount"), "ok": ok})
    rows.sort(key=lambda r: r["endedAt"])

    streak = 0
    for r in reversed(rows):
        if not r["ok"]:
            break
        streak += 1
    achieved = streak >= required

    if args.json:
        print(json.dumps({"required": required, "streak": streak, "achieved": achieved, "rounds": rows},
                         ensure_ascii=False, indent=2))
    else:
        print("| 終了時刻 | ジョブ | ラウンド | 判定 | 残ったリソース |")
        print("| --- | --- | --- | --- | --- |")
        for r in rows:
            print(f"| {r['endedAt']} | {r['jobId']} | {r['round']} | {r['result']} | {r['remaining']} |")
        print(f"\nゲート2: 直近の連続合格 {streak} 回 / 必要 {required} 回 → {'達成' if achieved else '未達成'}")
    return 0 if achieved else 3


if __name__ == "__main__":
    sys.exit(main())
