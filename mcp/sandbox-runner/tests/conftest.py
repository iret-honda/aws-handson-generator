"""テスト用の仮リポジトリを作り、SANDBOX_REPO_ROOT で指す。AWS には接続しない。"""

import json
import os
import shutil
import tempfile
from pathlib import Path

REAL_ROOT = Path(__file__).resolve().parents[3]
TMP_ROOT = Path(tempfile.mkdtemp(prefix="sandbox-runner-test-")).resolve()
os.environ["SANDBOX_REPO_ROOT"] = str(TMP_ROOT)

(TMP_ROOT / "config").mkdir()
shutil.copy(REAL_ROOT / "config" / "handson.config.json", TMP_ROOT / "config")
(TMP_ROOT / "scripts").mkdir()
shutil.copy(REAL_ROOT / "scripts" / "report.py", TMP_ROOT / "scripts")
(TMP_ROOT / "scripts" / "list-tagged.sh").write_text("#!/bin/bash\necho listed\n")
(TMP_ROOT / "scripts" / "list-tagged.sh").chmod(0o755)

JOB_ID = "test-intro-20261011-01"
job_dir = TMP_ROOT / "jobs" / JOB_ID
job_dir.mkdir(parents=True)
(job_dir / "phases.jsonl").write_text("")
(job_dir / "input.json").write_text(json.dumps({
    "jobId": JOB_ID, "service": "Test", "iac": "cdk", "profile": "default", "accountId": "123456789012",
    "region": "ap-northeast-1", "createdAt": "2026-10-11T00:00:00+00:00",
}))
(job_dir / "aws-cost.json").write_text(json.dumps({
    "estimatedUsd": 0.05, "items": [{"resource": "x", "usd": 0.05}],
    "hourlyResources": [{"resource": "t3.micro", "unitPriceUsdPerHour": 0.0136}],
}))
handson = TMP_ROOT / "handsons" / JOB_ID
(handson / "cdk").mkdir(parents=True)
(handson / "cdk" / "cdk.json").write_text(json.dumps({"app": "npx ts-node --prefer-ts-exts bin/app.ts"}))
shutil.copy(REAL_ROOT / "handsons" / "sqs-intro-20261010-01" / "README.md", handson / "README.md")
