"""1手順ぶんのコマンドを bash で実行する。

本文の手順は「QUEUE_URL=$(...) で変数に入れ、後の手順で使う」「cd cdk してから以降を実行する」のように
状態を引き継ぐ。手順ごとに新しい bash を起動し、前の手順までのシェル変数(vars.sh)と作業ディレクトリ(cwd)を
復元してから実行する。ファイルに残すので、MCP サーバーが再起動しても続きから実行できる。
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .job import ROOT, Job

SHIMS = Path(__file__).resolve().parents[2] / "shims"
GUARDED = ("aws", "cdk", "npx", "npm", "terraform")
# 呼び出し元の環境から引き継ぐ変数(認証情報やプロファイルの指定は引き継がない)
PASSTHROUGH = ("HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TMPDIR", "SHELL", "SSL_CERT_FILE", "NODE_EXTRA_CA_CERTS")

# macOS 標準の bash 3.2 でも動くよう、連想配列を使わずに書く
PROLOGUE = r"""
__sr_base=" $(compgen -v | tr '\n' ' ') "
__sr_save() {
  local __sr_rc=$? __sr_v
  pwd > "$__SR_DIR/cwd.next"
  : > "$__SR_DIR/vars.next"
  for __sr_v in $(compgen -v); do
    case "$__sr_v" in
      __sr_*|__SR_*|BASH*|PIPESTATUS|FUNCNAME|LINENO|SECONDS|RANDOM|SHLVL|PWD|OLDPWD|_|COLUMNS|LINES) continue ;;
    esac
    [[ "$__sr_base" == *" $__sr_v "* ]] && continue
    declare -p "$__sr_v" >> "$__SR_DIR/vars.next" 2>/dev/null
  done
  exit $__sr_rc
}
trap __sr_save EXIT
[[ -f "$__SR_DIR/vars.sh" ]] && source "$__SR_DIR/vars.sh"
cd "$(cat "$__SR_DIR/cwd")" || exit 97
# ---- ここから本文のコマンド ----
"""


@dataclass
class Result:
    exit_code: int
    stdout: str
    stderr: str
    duration_sec: float
    cwd: str
    timed_out: bool


def real_binaries() -> dict[str, str]:
    """シムを除いた PATH で本物のコマンドを探す。"""
    path = os.pathsep.join(p for p in os.environ.get("PATH", "").split(os.pathsep)
                           if p and Path(p).resolve() != SHIMS.resolve())
    found = {}
    for tool in GUARDED:
        exe = shutil.which(tool, path=path)
        if exe:
            found[f"SANDBOX_REAL_{tool.upper()}"] = exe
    return found


def base_env(job: Job) -> dict[str, str]:
    path = os.environ.get("PATH", "")
    plugin_cache = Path.home() / ".terraform.d" / "plugin-cache"
    plugin_cache.mkdir(parents=True, exist_ok=True)
    env = {k: os.environ[k] for k in PASSTHROUGH if k in os.environ}
    env.update({
        "PATH": f"{SHIMS}{os.pathsep}{path}",
        "TERM": "dumb",
        "NO_COLOR": "1",
        "FORCE_COLOR": "0",
        "AWS_PROFILE": job.profile,
        "AWS_REGION": job.region,
        "AWS_DEFAULT_REGION": job.region,
        "AWS_PAGER": "",
        "HANDSON_JOB_ID": job.job_id,
        # CloudTrail の userAgent にジョブIDを残し、検証レポートから追跡できるようにする
        "AWS_SDK_UA_APP_ID": f"handson-{job.job_id}"[:50],
        "AWS_EXECUTION_ENV": f"handson-sandbox-runner/{job.job_id}",
        # Terraform のプロバイダーを毎回ダウンロードしない(検証環境の都合。結果には影響しない)
        "TF_PLUGIN_CACHE_DIR": str(plugin_cache),
        "TF_IN_AUTOMATION": "1",
        "SANDBOX_PYTHON": sys.executable,
        "SANDBOX_REPO_ROOT": str(ROOT),
        "SANDBOX_JOB_ID": job.job_id,
        "SANDBOX_PROFILE": job.profile,
        "SANDBOX_REGION": job.region,
        "SANDBOX_ALLOWED_ROOTS": os.pathsep.join(str(p) for p in job.allowed_roots()),
        "SANDBOX_TFSTATE": str(job.tfstate),
        "SANDBOX_GUARD_LOG": str(job.sandbox_dir / "guard.jsonl"),
    })
    env.update(real_binaries())
    return env


def shell_dir(job: Job) -> Path:
    d = job.sandbox_dir / "shell"
    if not (d / "cwd").is_file():
        d.mkdir(parents=True, exist_ok=True)
        (job.sandbox_dir / "work").mkdir(parents=True, exist_ok=True)
        # 本文は README.md のあるディレクトリ(handsons/<job-id>/)から始める前提で書かれている
        (d / "cwd").write_text(str(job.handson_dir))
    return d


def current_cwd(job: Job) -> Path:
    return Path(shell_dir(job).joinpath("cwd").read_text().strip())


def reset(job: Job) -> None:
    """シェルの状態(変数と作業ディレクトリ)を初期化する。新しいラウンドの最初に呼ぶ。"""
    d = job.sandbox_dir / "shell"
    if d.exists():
        shutil.rmtree(d)
    shell_dir(job)


def run(job: Job, command: str, timeout: int) -> Result:
    d = shell_dir(job)
    script = d / "step.sh"
    script.write_text(PROLOGUE + command + "\n")
    env = base_env(job) | {"__SR_DIR": str(d)}
    for f in ("cwd.next", "vars.next"):
        (d / f).unlink(missing_ok=True)

    start = time.monotonic()
    proc = subprocess.Popen(
        ["bash", "--noprofile", "--norc", str(script)],
        cwd=current_cwd(job), env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace",
        start_new_session=True,
    )
    timed_out = False
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            out, err = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            out, err = proc.communicate()
    duration = time.monotonic() - start

    # 正常に終わったときだけ状態を進める(タイムアウトで途中の状態を残さない)
    if not timed_out and (d / "cwd.next").is_file():
        (d / "cwd.next").replace(d / "cwd")
        if (d / "vars.next").is_file():
            (d / "vars.next").replace(d / "vars.sh")
    return Result(proc.returncode if not timed_out else 124, out, err, round(duration, 1),
                  str(current_cwd(job)), timed_out)


def syntax_error(command: str) -> str | None:
    """bash -n で構文だけ確かめる。問題なければ None。"""
    p = subprocess.run(["bash", "-n"], input=command, capture_output=True, text=True)
    return p.stderr.strip() or None if p.returncode else None
