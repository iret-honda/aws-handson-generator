"""設定とジョブ情報。プロファイルとリージョンはジョブで最初に呼ばれたときに固定し、途中で切り替えない。"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# mcp/sandbox-runner/src/sandbox_runner/job.py → リポジトリのルート
ROOT = Path(os.environ.get("SANDBOX_REPO_ROOT") or Path(__file__).resolve().parents[4])
JOB_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
PLACEHOLDER_ACCOUNT = "123456789012"


class SandboxError(Exception):
    """ツールの呼び出し元に返すエラー(ジョブの状態や入力の不備)。"""


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(t: dt.datetime) -> str:
    return t.isoformat(timespec="seconds")


def parse_iso(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def load_config() -> dict:
    return json.loads((ROOT / "config" / "handson.config.json").read_text())


@dataclass
class Job:
    job_id: str
    profile: str
    region: str
    account_id: str
    iac: str
    created_at: str
    config: dict

    @property
    def job_dir(self) -> Path:
        return ROOT / "jobs" / self.job_id

    @property
    def handson_dir(self) -> Path:
        return ROOT / "handsons" / self.job_id

    @property
    def sandbox_dir(self) -> Path:
        """ランナーの作業領域。生の出力やシェル変数を置くので git には入れない(.gitignore 済み)。"""
        return self.job_dir / "sandbox"

    @property
    def session_file(self) -> Path:
        return self.sandbox_dir / "session.json"

    @property
    def tag_key(self) -> str:
        return self.config["tagging"]["jobTagKey"]

    @property
    def tfstate(self) -> Path:
        return self.job_dir / "terraform.tfstate"

    def allowed_roots(self) -> list[Path]:
        """コマンドの作業ディレクトリとして許す場所。"""
        return [self.handson_dir.resolve(), (self.sandbox_dir / "work").resolve()]

    def load_session(self) -> dict:
        return json.loads(self.session_file.read_text())

    def save_session(self, session: dict) -> None:
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.session_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(session, ensure_ascii=False, indent=2))
        tmp.replace(self.session_file)


def caller_account(profile: str, region: str) -> str:
    import boto3

    return boto3.Session(profile_name=profile, region_name=region).client("sts").get_caller_identity()["Account"]


def open_job(job_id: str, identity: Callable[[str, str], str] = caller_account) -> Job:
    """ジョブを開く。初回は input.json の値でセッションを固定し、以降は固定した値と食い違えば止める。"""
    if not JOB_ID_RE.match(job_id or ""):
        raise SandboxError(f"ジョブIDの形式が不正です: {job_id!r}")
    job_dir = ROOT / "jobs" / job_id
    input_json = job_dir / "input.json"
    if not input_json.is_file():
        raise SandboxError(f"{input_json.relative_to(ROOT)} がありません。/handson でジョブを作ってから呼んでください")
    data = json.loads(input_json.read_text())
    cfg = load_config()
    job = Job(
        job_id=job_id,
        profile=data.get("profile") or cfg["defaults"]["profile"],
        region=data.get("region") or cfg["defaults"]["region"],
        account_id=data.get("accountId") or "",
        iac=data.get("iac") or cfg["defaults"]["iac"],
        created_at=data.get("createdAt") or iso(now()),
        config=cfg,
    )
    if job.iac not in ("cdk", "terraform"):
        raise SandboxError(f"IaC 種別が不正です: {job.iac}")

    if job.session_file.is_file():
        session = job.load_session()
        if (session["profile"], session["region"]) != (job.profile, job.region):
            raise SandboxError(
                "ジョブの途中でプロファイルかリージョンが変わっています"
                f"(固定: {session['profile']} / {session['region']}、input.json: {job.profile} / {job.region})。"
                "切り替えはできません。新しいジョブを作ってください"
            )
        # コミット前のマスキングで input.json のアカウントIDは例示値になるため、実際の値はセッションから取る
        job.account_id = session["accountId"]
        return job

    actual = identity(job.profile, job.region)
    if job.account_id and job.account_id != PLACEHOLDER_ACCOUNT and job.account_id != actual:
        raise SandboxError(
            f"プロファイル {job.profile} のアカウントID({actual})が、構成案で承認されたもの({job.account_id})と違います"
        )
    job.account_id = actual
    job.save_session({
        "jobId": job_id,
        "profile": job.profile,
        "region": job.region,
        "accountId": actual,
        "iac": job.iac,
        "lockedAt": iso(now()),
        "rounds": {},
    })
    return job
