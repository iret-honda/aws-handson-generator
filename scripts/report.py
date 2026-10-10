#!/usr/bin/env python3
"""実行レポート(トークン数・API料金換算の想定コスト・AWS検証費用の見積もり)を作る。

Claude Code の OpenTelemetry 出力を Collector が書き出した JSON Lines を読み、
jobs/<job-id>/phases.jsonl のフェーズ開始・終了時刻でイベントを振り分けて合計する。
項目名は config/handson.config.json の telemetry.names で差し替えられる(OTel はベータ機能のため)。

使い方:
  python3 scripts/report.py <job-id>                 レポートを jobs/<job-id>/token-report.md に書き出す
  python3 scripts/report.py <job-id> --check         現在の想定コストを上限と比べる(超過で終了コード2)
  python3 scripts/report.py <job-id> --session <id>  指定セッションのイベントだけを数える(複数指定可)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKEN_KEYS = ("input", "output", "cacheRead", "cacheCreation")


def load_config() -> dict:
    return json.loads((ROOT / "config" / "handson.config.json").read_text())


def parse_ts(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def from_nanos(value) -> dt.datetime | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return dt.datetime.fromtimestamp(n / 1e9, tz=dt.timezone.utc)


def otel_value(v: dict):
    for key in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if key in v:
            return v[key]
    return None


def attrs_of(items) -> dict:
    return {a["key"]: otel_value(a.get("value", {})) for a in items or []}


def num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def read_jsonl(path: Path):
    if not path.exists():
        return
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def load_windows(job_dir: Path) -> tuple[list[tuple[str, dt.datetime, dt.datetime]], dict[str, int]]:
    """phases.jsonl から (phase, start, end) の区間を作る。end がなければ現在時刻まで。"""
    now = dt.datetime.now(dt.timezone.utc)
    open_starts: dict[str, dt.datetime] = {}
    windows = []
    starts = defaultdict(int)
    for rec in read_jsonl(job_dir / "phases.jsonl"):
        ts = parse_ts(rec["ts"])
        if rec["event"] == "start":
            open_starts[rec["phase"]] = ts
            starts[rec["phase"]] += 1
        elif rec["event"] == "end" and rec["phase"] in open_starts:
            windows.append((rec["phase"], open_starts.pop(rec["phase"]), ts))
    for phase, start in open_starts.items():
        windows.append((phase, start, now))
    return windows, dict(starts)


def phase_at(windows, ts: dt.datetime) -> str | None:
    for phase, start, end in windows:
        if start <= ts <= end:
            return phase
    return None


def collect_events(cfg: dict, windows, sessions: set[str]):
    """api_request イベントをフェーズごとに合計する。マッチしたイベントも返す。"""
    names = cfg["telemetry"]["names"]
    event_names = set(names["apiRequestEvent"])
    logs_path = ROOT / cfg["telemetry"]["rawDir"] / cfg["telemetry"]["logsFile"]
    totals = defaultdict(lambda: defaultdict(float))
    matched = []
    for batch in read_jsonl(logs_path):
        for rl in batch.get("resourceLogs", []):
            res_attrs = attrs_of(rl.get("resource", {}).get("attributes"))
            for sl in rl.get("scopeLogs", []):
                for rec in sl.get("logRecords", []):
                    a = {**res_attrs, **attrs_of(rec.get("attributes"))}
                    body = otel_value(rec.get("body", {})) or ""
                    if a.get("event.name") not in event_names and body not in event_names:
                        continue
                    if sessions and a.get(names["sessionIdAttr"]) not in sessions:
                        continue
                    ts = None
                    if a.get(names["timestampAttr"]):
                        try:
                            ts = parse_ts(str(a[names["timestampAttr"]]))
                        except ValueError:
                            ts = None
                    ts = ts or from_nanos(rec.get("timeUnixNano")) or from_nanos(rec.get("observedTimeUnixNano"))
                    if ts is None:
                        continue
                    phase = phase_at(windows, ts)
                    if phase is None:
                        continue
                    t = totals[phase]
                    t["input"] += num(a.get(names["inputTokensAttr"]))
                    t["output"] += num(a.get(names["outputTokensAttr"]))
                    t["cacheRead"] += num(a.get(names["cacheReadTokensAttr"]))
                    t["cacheCreation"] += num(a.get(names["cacheCreationTokensAttr"]))
                    t["costUsd"] += num(a.get(names["costUsdAttr"]))
                    t["requests"] += 1
                    matched.append({"ts": ts.isoformat(), "phase": phase, "attributes": a})
    return totals, matched


def collect_metrics(cfg: dict, windows, sessions: set[str]):
    """イベントが取れなかったときの予備。token.usage / cost.usage メトリクスから合計する。"""
    names = cfg["telemetry"]["names"]
    types = {v: k for k, v in names["tokenTypes"].items()}
    metrics_path = ROOT / cfg["telemetry"]["rawDir"] / cfg["telemetry"]["metricsFile"]
    totals = defaultdict(lambda: defaultdict(float))
    last_cumulative: dict[tuple, float] = {}
    for batch in read_jsonl(metrics_path):
        for rm in batch.get("resourceMetrics", []):
            res_attrs = attrs_of(rm.get("resource", {}).get("attributes"))
            for sm in rm.get("scopeMetrics", []):
                for m in sm.get("metrics", []):
                    if m.get("name") not in (names["tokenUsageMetric"], names["costUsageMetric"]):
                        continue
                    data = m.get("sum") or {}
                    cumulative = data.get("aggregationTemporality") in (2, "AGGREGATION_TEMPORALITY_CUMULATIVE")
                    for p in data.get("dataPoints", []):
                        a = {**res_attrs, **attrs_of(p.get("attributes"))}
                        if sessions and a.get(names["sessionIdAttr"]) not in sessions:
                            continue
                        value = num(p.get("asDouble", p.get("asInt")))
                        if cumulative:
                            series = (m["name"], tuple(sorted((k, str(v)) for k, v in a.items())))
                            prev = last_cumulative.get(series, 0.0)
                            last_cumulative[series] = value
                            value = value - prev if value >= prev else value
                        ts = from_nanos(p.get("timeUnixNano"))
                        phase = phase_at(windows, ts) if ts else None
                        if phase is None:
                            continue
                        if m["name"] == names["costUsageMetric"]:
                            totals[phase]["costUsd"] += value
                        else:
                            key = types.get(a.get(names["tokenTypeAttr"]))
                            if key:
                                totals[phase][key] += value
    return totals


def fmt_int(v: float) -> str:
    return f"{int(round(v)):,}"


def build_report(cfg, job_id, totals, retries, source) -> tuple[str, dict]:
    limits = cfg["limits"]
    lines = [
        f"## 実行レポート(job: {job_id})",
        "",
        "| フェーズ | 入力 | 出力 | キャッシュ読込 | キャッシュ作成 | 想定コスト(USD) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    grand = defaultdict(float)
    for p in cfg["phases"]:
        t = totals.get(p["id"], {})
        label = p["label"]
        if p["id"] == "verification":
            label = f"{label}(再試行 {retries}回を含む)"
        lines.append(
            f"| {label} | {fmt_int(t.get('input', 0))} | {fmt_int(t.get('output', 0))} | "
            f"{fmt_int(t.get('cacheRead', 0))} | {fmt_int(t.get('cacheCreation', 0))} | ${t.get('costUsd', 0):.4f} |"
        )
        for k in (*TOKEN_KEYS, "costUsd"):
            grand[k] += t.get(k, 0)
    lines.append(
        f"| 合計 | {fmt_int(grand['input'])} | {fmt_int(grand['output'])} | "
        f"{fmt_int(grand['cacheRead'])} | {fmt_int(grand['cacheCreation'])} | ${grand['costUsd']:.4f} |"
    )
    lines.append("")

    aws_cost_path = ROOT / "jobs" / job_id / "aws-cost.json"
    if aws_cost_path.exists():
        aws = json.loads(aws_cost_path.read_text())
        lines.append(f"AWS検証費用(見積もり): ${num(aws.get('estimatedUsd')):.2f} / 上限 ${limits['awsCostUsd']:.2f}")
        if aws.get("basis"):
            lines.append(f"(根拠: {aws['basis']})")
    else:
        lines.append(f"AWS検証費用(見積もり): 未記録(jobs/{job_id}/aws-cost.json なし) / 上限 ${limits['awsCostUsd']:.2f}")
    lines += [
        "",
        f"トークン費用: ${grand['costUsd']:.4f} / 上限 ${limits['tokenCostUsd']:.2f}",
        "",
        "- 想定コストは Claude Code が出力する **API料金換算の想定コスト** であり、Pro/Max プランの実際の請求額とは一致しない。"
        "正確な請求額は Claude Console で確認すること。",
        f"- 集計元: OpenTelemetry {source}。フェーズの開始・終了時刻(jobs/{job_id}/phases.jsonl)で振り分けた。",
    ]
    return "\n".join(lines) + "\n", grand


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("job_id")
    parser.add_argument("--check", action="store_true", help="想定コストを上限と比べるだけ(超過で終了コード2)")
    parser.add_argument("--session", action="append", default=[], help="数えるセッションID(複数指定可)")
    args = parser.parse_args()

    cfg = load_config()
    job_dir = ROOT / "jobs" / args.job_id
    if not (job_dir / "phases.jsonl").exists():
        print(f"job not found: {args.job_id}", file=sys.stderr)
        return 1

    windows, starts = load_windows(job_dir)
    retries = max(starts.get("verification", 0) - 1, 0)
    sessions = set(args.session)

    totals, matched = collect_events(cfg, windows, sessions)
    source = "api_request イベント"
    if not matched:
        totals = collect_metrics(cfg, windows, sessions)
        source = "token.usage / cost.usage メトリクス(イベントが見つからなかったため)"

    report, grand = build_report(cfg, args.job_id, totals, retries, source)
    limit = cfg["limits"]["tokenCostUsd"]

    if args.check:
        print(f"token cost: ${grand['costUsd']:.4f} / limit ${limit:.2f}")
        return 2 if grand["costUsd"] >= limit else 0

    (job_dir / "telemetry.json").write_text(json.dumps(matched, ensure_ascii=False, indent=2))
    (job_dir / "token-report.md").write_text(report)
    print(report)
    if not matched and not totals:
        print("warning: 該当するテレメトリがない。Collector が起動しているか(./scripts/telemetry.sh status)確認すること。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
