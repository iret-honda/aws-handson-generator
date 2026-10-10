"""検証費用の見積もりと上限の判定。実績(請求データ)ではなく見積もりで止める。

ラウンドごとの見積もり = items(リクエスト課金などの固定分)の合計 + Σ 時間課金の単価 × 経過時間。
経過時間は、そのラウンドで最初に run_step を呼んでから teardown が終わるまで(終わっていなければ現在まで)。
時間課金のリソースに minimumHours があれば、経過時間がそれより短くても minimumHours 分を計上する。
Cost Explorer API は呼び出しごとに課金されるので使わない。
"""

from __future__ import annotations

import json
import subprocess
import sys

from .job import ROOT, Job, now, parse_iso


def load_plan(job: Job) -> dict:
    path = job.job_dir / "aws-cost.json"
    if not path.is_file():
        return {"items": [], "hourlyResources": [], "estimatedUsd": None}
    return json.loads(path.read_text())


def round_elapsed_hours(r: dict) -> float:
    start = parse_iso(r["startedAt"])
    end = parse_iso(r["endedAt"]) if r.get("endedAt") else now()
    return max((end - start).total_seconds(), 0) / 3600


def estimate(job: Job) -> dict:
    cfg = job.config["limits"]
    plan = load_plan(job)
    session = job.load_session()
    fixed = sum(float(i.get("usd") or 0) for i in plan.get("items", []))
    hourly = plan.get("hourlyResources", [])

    rounds = []
    total = 0.0
    for n, r in sorted(session.get("rounds", {}).items(), key=lambda kv: int(kv[0])):
        hours = round_elapsed_hours(r)
        hourly_usd = sum(float(h.get("unitPriceUsdPerHour") or 0) * max(hours, float(h.get("minimumHours") or 0))
                         for h in hourly)
        usd = fixed + hourly_usd
        total += usd
        rounds.append({
            "round": int(n), "elapsedMinutes": round(hours * 60, 1), "fixedUsd": round(fixed, 4),
            "hourlyUsd": round(hourly_usd, 4), "estimatedUsd": round(usd, 4), "ended": bool(r.get("endedAt")),
        })

    limit = float(cfg["awsCostUsd"])
    stop_at = limit * float(cfg.get("teardownRatio", 0.9))
    return {
        "jobId": job.job_id,
        "region": job.region,
        "planEstimatedUsdPerRound": plan.get("estimatedUsd"),
        "rounds": rounds,
        "totalEstimatedUsd": round(total, 4),
        "limitUsd": limit,
        "teardownAtUsd": round(stop_at, 4),
        "basis": "jobs/<job-id>/aws-cost.json の items(固定分)と hourlyResources(時間課金 × 経過時間)。"
                 "見積もり額であり実績額ではない(Cost Explorer は使わない)",
        "overLimit": total >= stop_at,
    }


def token_check(job: Job) -> tuple[bool, str]:
    """scripts/report.py --check でトークン費用を上限と比べる。(超過したか, 出力)。"""
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "report.py"), job.job_id, "--check"],
                       capture_output=True, text=True, cwd=ROOT)
    return p.returncode == 2, (p.stdout or p.stderr).strip()


def limits_status(job: Job, round_no: int | None = None) -> dict:
    """3つの上限(AWS費用、トークン費用、実行時間)の状態。どれかを超えたら action=teardown。"""
    cost = estimate(job)
    session = job.load_session()
    max_minutes = float(job.config["limits"]["maxRuntimeMinutes"])
    reasons = []
    if cost["overLimit"]:
        reasons.append(f"AWS検証費用の見積もり ${cost['totalEstimatedUsd']:.4f} が ${cost['teardownAtUsd']:.2f}"
                       f"(上限 ${cost['limitUsd']:.2f} の{int(job.config['limits'].get('teardownRatio', 0.9) * 100)}%)に達した")
    elapsed = None
    if round_no is not None and str(round_no) in session.get("rounds", {}):
        r = session["rounds"][str(round_no)]
        elapsed = round(round_elapsed_hours(r) * 60, 1)
        if elapsed >= max_minutes and not r.get("endedAt"):
            reasons.append(f"ラウンド {round_no} の実行時間 {elapsed} 分が上限 {max_minutes:g} 分に達した")
    over_tokens, token_msg = token_check(job)
    if over_tokens:
        reasons.append(f"トークン費用が上限に達した({token_msg})")
    return {
        "action": "teardown" if reasons else "continue",
        "reasons": reasons,
        "awsEstimatedUsd": cost["totalEstimatedUsd"],
        "awsLimitUsd": cost["limitUsd"],
        "roundElapsedMinutes": elapsed,
        "maxRuntimeMinutes": max_minutes,
        "tokens": token_msg,
    }
