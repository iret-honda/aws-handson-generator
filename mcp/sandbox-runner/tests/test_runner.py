"""シェルの状態の引き継ぎ、シムによる拒否、run_step の流れ。AWS には接続しない。"""

import json

import pytest

from conftest import JOB_ID, TMP_ROOT
from sandbox_runner import cost, server, shell
from sandbox_runner.job import SandboxError, open_job


class FakeAws:
    def __init__(self, *a, **k):
        pass

    def has_job_tag(self, *a):
        return False


@pytest.fixture
def job(monkeypatch):
    session = TMP_ROOT / "jobs" / JOB_ID / "sandbox"
    if session.exists():
        import shutil
        shutil.rmtree(session)
    monkeypatch.setattr(server, "open_job", lambda j: open_job(j, identity=lambda p, r: "123456789012"))
    monkeypatch.setattr(server, "Aws", FakeAws)
    monkeypatch.setattr(cost, "token_check", lambda job: (False, "token cost: $0 / limit $10"))
    return server.open_job(JOB_ID)


def test_session_locks_account(job):
    assert job.account_id == "123456789012"
    data = json.loads(job.session_file.read_text())
    assert (data["profile"], data["region"]) == ("default", "ap-northeast-1")


def test_variables_and_cwd_persist_between_steps(job):
    r1 = server.run_step(JOB_ID, 1, command="QUEUE_URL=https://example/q\nexport FOO=bar\ncd cdk", note="test")
    assert r1["exitCode"] == 0, r1
    r2 = server.run_step(JOB_ID, 1, command='echo "$QUEUE_URL $FOO $HANDSON_JOB_ID $AWS_REGION"; pwd', note="test")
    out = r2["stdout"].splitlines()
    assert out[0] == f"https://example/q bar {JOB_ID} ap-northeast-1"
    assert out[1].endswith(f"handsons/{JOB_ID}/cdk")


def test_block_from_readme_is_run_verbatim(job):
    r = server.run_step(JOB_ID, 1, block_id="step-16#1", timeout_seconds=1)
    assert r["executed"] and r["timedOut"] and r["command"] == "sleep 30"
    assert r["checks"] is not None


def test_setup_block_is_rewritten(job):
    r = server.run_step(JOB_ID, 1, block_id="prep-1#1")
    assert r["exitCode"] == 0 and len(r["notes"]) == 5  # 4行の置き換え + 本文のジョブIDとの違い


def test_policy_violation_is_not_executed(job):
    r = server.run_step(JOB_ID, 1, command="AWS_REGION=us-east-1 aws sqs list-queues", note="test")
    assert r["executed"] is False and r["result"] == "denied"


def test_syntax_error(job):
    r = server.run_step(JOB_ID, 1, command="if then fi (", note="test")
    assert r["result"] == "syntax-error"


def test_shim_denies_untagged_mutation(job):
    r = server.run_step(JOB_ID, 1, command="aws sqs delete-queue --queue-url https://sqs.ap-northeast-1.amazonaws.com/1/other", note="test")
    assert r["exitCode"] == 126 and "拒否しました" in r["stderr"]
    r = server.run_step(JOB_ID, 1, command="aws --profile prod sts get-caller-identity", note="test")
    assert r["exitCode"] == 126
    guard_log = (TMP_ROOT / "jobs" / JOB_ID / "sandbox" / "guard.jsonl").read_text().splitlines()
    assert all(json.loads(l)["decision"] == "deny" for l in guard_log)


def test_repo_script_can_be_run(job):
    server.run_step(JOB_ID, 1, command="cd cdk", note="test")
    r = server.run_step(JOB_ID, 1, command="../../../scripts/list-tagged.sh x y z", note="test")
    assert r["exitCode"] == 0 and r["stdout"].strip() == "listed"


def test_free_command_needs_note(job):
    with pytest.raises(SandboxError, match="note"):
        server.run_step(JOB_ID, 1, command="echo hi")


def test_new_round_requires_teardown(job):
    server.run_step(JOB_ID, 1, command="X=1", note="test")
    with pytest.raises(SandboxError, match="teardown"):
        server.run_step(JOB_ID, 2, command="echo $X", note="test")
    session = job.load_session()
    session["rounds"]["1"]["endedAt"] = session["rounds"]["1"]["startedAt"]
    job.save_session(session)
    r = server.run_step(JOB_ID, 2, command='echo "[$X]"', note="test")
    assert r["stdout"].strip() == "[]"  # 新しいラウンドでは変数が初期化される
    with pytest.raises(SandboxError, match="teardown 済み"):
        server.run_step(JOB_ID, 1, command="echo", note="test")


def test_limits_stop_execution(job, monkeypatch):
    server.run_step(JOB_ID, 1, command="true", note="test")
    session = job.load_session()
    session["rounds"]["1"]["startedAt"] = "2026-10-01T00:00:00+00:00"  # 60分を大きく超えた状態
    job.save_session(session)
    r = server.run_step(JOB_ID, 1, command="true", note="test")
    assert r["executed"] is False and r["action"] == "teardown"
    assert any("実行時間" in x for x in r["limits"]["reasons"])


def test_estimate(job):
    server.run_step(JOB_ID, 1, command="true", note="test")
    est = cost.estimate(job)
    assert est["rounds"][0]["fixedUsd"] == 0.05
    assert est["overLimit"] is False
