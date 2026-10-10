"""取りこぼし対策: handson-job-id タグが付いて24時間以上経ったリソースだけを消す。

アカウント全体を掃除するツール(aws-nuke など)は使わない。タグのないリソースには触れない。
作成日時が分からないリソースは、そのジョブのセッション(jobs/<job-id>/sandbox/session.json)の
最初のラウンド開始時刻で判断し、それも分からなければ消さずに報告する。
既定は一覧だけ(dry run)。消すときは --execute を付ける。

使い方: ./scripts/cleanup-stale.sh <profile> <region> [--execute] [--hours 24]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys

from .job import ROOT, load_config, now, parse_iso
from .resources import Aws, delete_rank, stack_name


def job_started_at(job_id: str) -> dt.datetime | None:
    if not job_id:
        return None
    session = ROOT / "jobs" / job_id / "sandbox" / "session.json"
    if session.is_file():
        rounds = json.loads(session.read_text()).get("rounds", {})
        starts = [parse_iso(r["startedAt"]) for r in rounds.values() if r.get("startedAt")]
        if starts:
            return min(starts)
    input_json = ROOT / "jobs" / job_id / "input.json"
    if input_json.is_file():
        created = json.loads(input_json.read_text()).get("createdAt")
        if created:
            return parse_iso(created)
    return None


def main(argv: list[str] | None = None) -> int:
    cfg = load_config()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("profile")
    parser.add_argument("region")
    parser.add_argument("--execute", action="store_true", help="実際に削除する(省略時は一覧だけ)")
    parser.add_argument("--hours", type=float, default=float(cfg["tagging"]["staleHours"]))
    args = parser.parse_args(argv)

    tag_key = cfg["tagging"]["jobTagKey"]
    aws = Aws(args.profile, args.region)
    cutoff = now() - dt.timedelta(hours=args.hours)
    inv = aws.inventory(tag_key, "", any_value=True)

    stale, young, unknown = [], [], []
    for r in inv.remaining:
        m = re.search(r"job=(\S+)", r.note)
        job_id = m.group(1) if m else ""
        created = parse_iso(r.created_at) if r.created_at else job_started_at(job_id)
        row = (r, job_id, created)
        if created is None:
            unknown.append(row)
        elif created <= cutoff:
            stale.append(row)
        else:
            young.append(row)

    print(f"# {tag_key} タグ付きリソース({args.profile} / {args.region}、{args.hours:g}時間より前を対象)")
    for title, rows in (("対象(古い)", stale), ("対象外(新しい)", young), ("対象外(作成日時が不明)", unknown)):
        print(f"\n## {title}: {len(rows)}件")
        for r, job_id, created in rows:
            print(f"- {r.arn}  job={job_id or '?'}  created={created.isoformat(timespec='seconds') if created else '?'}")

    if not args.execute:
        print("\n一覧だけ表示しました。削除するには --execute を付けて再実行してください。")
        return 0

    failed = 0
    stale.sort(key=lambda row: delete_rank(row[0].kind))
    for r, job_id, _ in stale:
        if r.kind == "cloudformation:stack":
            if not aws.has_job_tag(r.arn, tag_key, job_id):
                result = "skip: タグを確認できなかった"
            else:
                result = aws.delete_stack(r.arn, int(cfg.get("sandbox", {}).get("teardownStackWaitSeconds", 900)))
            label = stack_name(r.arn)
        else:
            result = aws.delete(r.arn, tag_key, job_id)
            label = r.arn
        failed += not result.startswith("deleted")
        print(f"{result}: {label}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
