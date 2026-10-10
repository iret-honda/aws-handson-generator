"""sandbox-runner MCP サーバー。AWS への書き込み経路をこのサーバー1つに絞る(設計書「ツールとMCPサーバー構成」)。

ツール:
- list_steps: 本文(README.md)の手順とコマンドのブロックを一覧する(読み取りのみ。AWS に触れない)
- run_step: 1手順を実行して出力を返す。上限を超えていたら実行せず teardown を促す
- list_tagged_resources: このジョブのタグが付いたリソースの一覧(後片付け検証は0件で合格)
- teardown: ジョブのリソースを全削除する(IaC の destroy の後、タグで残骸を掃除)
- estimate_job_cost: 作成予定のリソースと経過時間から費用を見積もる

プロファイルとリージョンは jobs/<job-id>/input.json の値で、ジョブで最初に呼ばれたときに固定する。
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import cost, shell, steps
from .job import Job, SandboxError, iso, now, open_job, parse_iso
from .policy import Context, PolicyError, scan_command
from .resources import Aws, delete_rank, stack_name

mcp = FastMCP(
    "sandbox-runner",
    instructions=(
        "ハンズオン検証用のサンドボックス実行サーバー。検証担当(handson-verifier)だけが使う。"
        "本文のコマンドは list_steps で得たブロックIDを run_step に渡して、そのまま実行する。"
        "run_step が action=teardown を返したら、それ以上実行せず teardown を呼ぶ。"
        "ラウンドの最後には必ず teardown を呼ぶ。"
    ),
)


def _context(job: Job, aws: Aws | None = None) -> Context:
    return Context(
        job_id=job.job_id, profile=job.profile, region=job.region, tag_key=job.tag_key,
        repo_root=Path(shell.ROOT), allowed_roots=job.allowed_roots(), tfstate=job.tfstate,
        config=job.config, cwd=shell.current_cwd(job),
        has_job_tag=(lambda t: aws.has_job_tag(t, job.tag_key, job.job_id)) if aws else None,
    )


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n... (中略: {len(text) - limit} 文字。全文は jobs/<job-id>/sandbox/runs/ のログ) ...\n{text[-half:]}"


def _append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _created_after(job: Job) -> dt.datetime:
    return parse_iso(job.created_at) - dt.timedelta(hours=1)


def _readme_steps(job: Job) -> list[steps.Step]:
    readme = job.handson_dir / "README.md"
    if not readme.is_file():
        raise SandboxError(f"handsons/{job.job_id}/README.md がありません")
    return steps.parse(readme.read_text())


@mcp.tool()
def list_steps(job_id: str) -> dict:
    """本文(handsons/<job-id>/README.md)の手順を一覧する。各手順のコマンドのブロックID(例: step-12#1)、
    操作か確認か(role)、確認ポイント、出力例を返す。AWS には触れない。"""
    readme = Path(shell.ROOT) / "handsons" / job_id / "README.md"
    if not readme.is_file():
        raise SandboxError(f"handsons/{job_id}/README.md がありません")
    parsed = steps.parse(readme.read_text())
    return {"jobId": job_id, "stepCount": len(parsed), "steps": [s.to_dict() for s in parsed]}


@mcp.tool()
def run_step(job_id: str, round: int, block_id: str | None = None, command: str | None = None,
             note: str = "", timeout_seconds: int | None = None) -> dict:
    """1手順を実行して出力を返す。

    - block_id: list_steps のブロックID。本文のコマンドをそのまま実行する(通常はこちら)
    - command: 本文にないコマンド。コンソール操作のCLI代替などに限り、note に理由を必ず書く
      (例: "CLI代替で検証: 手順5のコンソール操作")
    - round: 検証ラウンドの番号(1から)。新しい番号で呼ぶとシェルの状態(変数・作業ディレクトリ)を初期化する。
      前のラウンドを teardown していないと新しいラウンドは始められない
    - timeout_seconds: 省略時は設定の既定値(600秒)。上限は設定の maxTimeoutSeconds

    シェル変数と作業ディレクトリは同じラウンドの手順間で引き継ぐ。AWS_PROFILE / AWS_REGION / HANDSON_JOB_ID は
    ランナーが固定値を設定する(本文の export 行は実行せずに取り除く)。
    3つの上限(AWS費用の見積もり、トークン費用、実行時間)のどれかを超えていたら実行せず action=teardown を返す。
    """
    job = open_job(job_id)
    sb = job.config.get("sandbox", {})
    if (block_id is None) == (command is None):
        raise SandboxError("block_id と command のどちらか一方を指定してください")
    if command is not None and not note.strip():
        raise SandboxError("本文にないコマンドを実行するときは note に理由を書いてください(例: CLI代替で検証)")
    if round < 1:
        raise SandboxError("round は1以上")

    session = job.load_session()
    rounds = session.setdefault("rounds", {})
    key = str(round)
    if key not in rounds:
        open_rounds = [n for n, r in rounds.items() if not r.get("endedAt")]
        if open_rounds:
            raise SandboxError(f"ラウンド {', '.join(open_rounds)} が teardown されていません。先に teardown を呼んでください")
        rounds[key] = {"startedAt": iso(now()), "steps": 0}
        job.save_session(session)
        shell.reset(job)
    elif rounds[key].get("endedAt"):
        raise SandboxError(f"ラウンド {round} は teardown 済みです。新しいラウンド番号で始めてください")

    limits = cost.limits_status(job, round)
    if limits["action"] == "teardown":
        return {"executed": False, "action": "teardown", "limits": limits,
                "message": "上限に達したため実行しませんでした。teardown を呼んでください"}

    step_info: dict = {}
    if block_id is not None:
        try:
            step, block = steps.find_block(_readme_steps(job), block_id)
        except KeyError:
            raise SandboxError(f"ブロック {block_id} が本文にありません。list_steps で確認してください") from None
        text = block.code
        step_info = {"stepId": step.id, "title": step.title, "role": block.role,
                     "checks": step.checks, "expected": step.expected}
    else:
        text = command or ""

    timeout = min(int(timeout_seconds or sb.get("defaultTimeoutSeconds", 600)), int(sb.get("maxTimeoutSeconds", 1800)))
    record = {"ts": iso(now()), "round": round, "blockId": block_id, "command": text, "note": note}
    runs_log = job.sandbox_dir / "runs" / f"round-{round}.jsonl"

    aws = Aws(job.profile, job.region)
    try:
        rewritten, notes = scan_command(text, _context(job, aws))
    except PolicyError as e:
        _append(runs_log, record | {"result": "denied", "reason": str(e)})
        return {"executed": False, "result": "denied", "reason": str(e), **step_info, "command": text}

    syntax = shell.syntax_error(rewritten)
    if syntax:
        _append(runs_log, record | {"result": "syntax-error", "stderr": syntax})
        return {"executed": False, "result": "syntax-error", "stderr": syntax, **step_info, "command": text}

    res = shell.run(job, rewritten, timeout)
    cwd = Path(res.cwd).resolve()
    if not any(cwd == r or r in cwd.parents for r in job.allowed_roots()):
        (job.sandbox_dir / "shell" / "cwd").write_text(str(job.handson_dir))
        notes.append(f"作業ディレクトリがジョブの外({cwd})に出たため、{job.handson_dir} に戻した")

    session = job.load_session()
    session["rounds"][key]["steps"] = session["rounds"][key].get("steps", 0) + 1
    job.save_session(session)
    _append(runs_log, record | {"result": "ran", "exitCode": res.exit_code, "timedOut": res.timed_out,
                                "durationSec": res.duration_sec, "cwd": res.cwd, "stdout": res.stdout,
                                "stderr": res.stderr, "notes": notes})

    limit_chars = int(sb.get("outputLimitChars", 12000))
    after = cost.limits_status(job, round)
    return {
        "executed": True,
        **step_info,
        "command": text,
        "exitCode": res.exit_code,
        "timedOut": res.timed_out,
        "durationSec": res.duration_sec,
        "cwd": res.cwd,
        "stdout": _truncate(res.stdout, limit_chars),
        "stderr": _truncate(res.stderr, limit_chars // 2),
        "notes": notes,
        "action": after["action"],
        "limits": after,
    }


@mcp.tool()
def list_tagged_resources(job_id: str) -> dict:
    """このジョブの handson-job-id タグが付いたリソースを一覧する(読み取りのみ)。
    Resource Groups Tagging API、CloudFormation スタック、IAM ロール・ポリシー(グローバル)に加え、
    名前にジョブIDを含むロググループ(タグが付かずに残りやすい)も調べる。
    タグ API に反映待ちで残っている削除済みのものは pendingPropagation に分け、remainingCount に数えない。"""
    job = open_job(job_id)
    inv = Aws(job.profile, job.region).inventory(job.tag_key, job.job_id, _created_after(job))
    return {"jobId": job_id, "profile": job.profile, "region": job.region, "checkedAt": iso(now()), **inv.to_dict()}


def _iac_destroy(job: Job) -> list[dict]:
    env = shell.base_env(job)
    timeout = int(job.config.get("sandbox", {}).get("teardownStackWaitSeconds", 900))
    results = []

    def run(cmd: list[str], cwd: Path) -> dict:
        try:
            p = subprocess.run(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                               timeout=timeout)
            return {"command": " ".join(cmd), "exitCode": p.returncode, "output": (p.stdout + p.stderr)[-3000:]}
        except subprocess.TimeoutExpired:
            return {"command": " ".join(cmd), "exitCode": 124, "output": "timeout"}

    if job.iac == "cdk":
        cdk_dir = job.handson_dir / "cdk"
        if (cdk_dir / "node_modules").is_dir():
            results.append(run(["npx", "cdk", "destroy", "-c", f"jobId={job.job_id}", "--force"], cdk_dir))
        else:
            results.append({"command": "npx cdk destroy", "skipped": "node_modules がないため、"
                            "タグ付きの CloudFormation スタックの削除で代える"})
    else:
        tf_dir = job.handson_dir / "terraform"
        if job.tfstate.is_file() and tf_dir.is_dir():
            results.append(run(["terraform", "init", "-input=false", f"-backend-config=path={job.tfstate}"], tf_dir))
            results.append(run(["terraform", "destroy", "-auto-approve", "-input=false",
                                "-var", f"job_id={job.job_id}", "-var", f"region={job.region}"], tf_dir))
        else:
            results.append({"command": "terraform destroy", "skipped": f"{job.tfstate.name} がない"})
    return results


@mcp.tool()
def teardown(job_id: str) -> dict:
    """ジョブのリソースを全削除し、ラウンドを終える。上限超過時と、各ラウンドの最後に必ず呼ぶ。

    1. IaC の destroy(CDK は `npx cdk destroy --force`、Terraform は `terraform destroy`)
    2. handson-job-id タグ付きの CloudFormation スタックを削除
    3. タグ付きリソースを、削除の直前にタグを確かめてから種類ごとに削除(対応外の種類は要手動削除として返す)
    4. 最後に棚卸しして、残った件数を返す
    タグのないリソースには触れない(名前にジョブIDを含むロググループだけは例外的に消す)。"""
    job = open_job(job_id)
    sb = job.config.get("sandbox", {})
    aws = Aws(job.profile, job.region)
    log: dict = {"startedAt": iso(now()), "iac": _iac_destroy(job), "stacks": [], "passes": []}

    inv = aws.inventory(job.tag_key, job.job_id, _created_after(job))
    for r in inv.remaining:
        if r.kind == "cloudformation:stack":
            name = stack_name(r.arn)
            if aws.has_job_tag(r.arn, job.tag_key, job.job_id):
                log["stacks"].append({"stack": name, "result": aws.delete_stack(r.arn, int(sb.get("teardownStackWaitSeconds", 900)))})

    for n in range(int(sb.get("teardownMaxPasses", 3))):
        inv = aws.inventory(job.tag_key, job.job_id, _created_after(job))
        targets = sorted([r for r in inv.remaining if r.kind != "cloudformation:stack"], key=lambda r: delete_rank(r.kind))
        if not targets:
            break
        results = [{"arn": r.arn, "kind": r.kind,
                    "result": aws.delete(r.arn, job.tag_key, job.job_id, by_name=r.source == "name-match")}
                   for r in targets]
        log["passes"].append(results)
        if not any(x["result"].startswith("deleted") for x in results):
            break
        if n + 1 < int(sb.get("teardownMaxPasses", 3)):
            time.sleep(15)  # 終了処理中のインスタンスなど、依存先の削除が反映されるのを待つ

    final = aws.inventory(job.tag_key, job.job_id, _created_after(job))
    session = job.load_session()
    ended = []
    for k, r in session.get("rounds", {}).items():
        if not r.get("endedAt"):
            r["endedAt"] = iso(now())
            ended.append(int(k))
    job.save_session(session)
    log |= {"endedAt": iso(now()), "endedRounds": ended, **final.to_dict()}
    _append(job.sandbox_dir / "teardown.jsonl", log)
    return {"jobId": job_id, **log, "estimate": cost.estimate(job)}


@mcp.tool()
def estimate_job_cost(job_id: str) -> dict:
    """作成予定・作成済みのリソース(jobs/<job-id>/aws-cost.json)と、各ラウンドの経過時間から検証費用を見積もる。
    上限(設定の awsCostUsd × teardownRatio)に達していれば overLimit=true。金額はUSD、見積もり額であり実績額ではない。"""
    job = open_job(job_id)
    return {**cost.estimate(job), "limits": cost.limits_status(job)}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
