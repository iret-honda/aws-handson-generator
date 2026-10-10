"""シム(shims/)から呼ばれるガード。引数を検査し、通れば本物のコマンドに置き換わる(exec)。

使い方(シムが呼ぶ): python -I -m sandbox_runner.guard <aws|cdk|npx|npm|terraform> [引数...]
ジョブの情報は、ランナーが設定した SANDBOX_* 環境変数から受け取る。
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

from .policy import (Context, PolicyError, check_aws, check_cdk, check_npm, check_npx, check_terraform,
                     shell_quote)

CHECKS = {"aws": check_aws, "cdk": check_cdk, "npx": check_npx, "npm": check_npm, "terraform": check_terraform}
DENIED_EXIT = 126


def context_from_env(env: dict) -> Context:
    repo = Path(env["SANDBOX_REPO_ROOT"])
    config = json.loads((repo / "config" / "handson.config.json").read_text())
    job_id, profile, region = env["SANDBOX_JOB_ID"], env["SANDBOX_PROFILE"], env["SANDBOX_REGION"]
    tag_key = config["tagging"]["jobTagKey"]

    def has_job_tag(target: str) -> bool:
        from .resources import Aws

        return Aws(profile, region).has_job_tag(target, tag_key, job_id)

    return Context(
        job_id=job_id, profile=profile, region=region, tag_key=tag_key, repo_root=repo,
        allowed_roots=[Path(p) for p in env["SANDBOX_ALLOWED_ROOTS"].split(os.pathsep)],
        tfstate=Path(env["SANDBOX_TFSTATE"]), config=config, cwd=Path.cwd(), env=env,
        has_job_tag=has_job_tag,
    )


def log(env: dict, record: dict) -> None:
    path = env.get("SANDBOX_GUARD_LOG")
    if not path:
        return
    record = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"), **record}
    with open(path, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main(argv: list[str]) -> int:
    env = dict(os.environ)
    tool, args = argv[1], argv[2:]
    if tool not in CHECKS or "SANDBOX_JOB_ID" not in env:
        print(f"sandbox-runner: {tool} はランナーの外では使えません", file=sys.stderr)
        return DENIED_EXIT
    ctx = context_from_env(env)
    try:
        new_args = CHECKS[tool](args, ctx)
    except PolicyError as e:
        log(env, {"tool": tool, "args": args, "cwd": str(ctx.cwd), "decision": "deny", "reason": str(e)})
        print(f"sandbox-runner: 拒否しました: {e}", file=sys.stderr)
        return DENIED_EXIT
    except Exception as e:  # タグ確認の API エラーなど。安全側に倒して拒否する
        log(env, {"tool": tool, "args": args, "cwd": str(ctx.cwd), "decision": "deny", "reason": repr(e)})
        print(f"sandbox-runner: 検査に失敗したため拒否しました: {e}", file=sys.stderr)
        return DENIED_EXIT
    log(env, {"tool": tool, "args": new_args, "cwd": str(ctx.cwd), "decision": "allow"})
    if new_args != args:
        print(f"sandbox-runner: 実行: {tool} {shell_quote(new_args)}", file=sys.stderr)
    real = env.get(f"SANDBOX_REAL_{tool.upper()}")
    if not real:
        print(f"sandbox-runner: {tool} がインストールされていません", file=sys.stderr)
        return 127
    os.execv(real, [real] + new_args)
    return 0  # 到達しない


if __name__ == "__main__":
    sys.exit(main(sys.argv))
