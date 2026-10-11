from pathlib import Path

import pytest

from conftest import JOB_ID, TMP_ROOT
from sandbox_runner.job import load_config
from sandbox_runner.policy import (Context, PolicyError, check_aws, check_cdk, check_npm, check_npx,
                                   check_terraform, scan_command)

HANDSON = TMP_ROOT / "handsons" / JOB_ID
TAGGED = {"arn:aws:sns:ap-northeast-1:123456789012:tagged", "i-0123456789abcdef0"}


def ctx(cwd: Path = HANDSON, **env) -> Context:
    return Context(
        job_id=JOB_ID, profile="default", region="ap-northeast-1", tag_key="handson-job-id",
        repo_root=TMP_ROOT, allowed_roots=[HANDSON.resolve()], tfstate=TMP_ROOT / "jobs" / JOB_ID / "terraform.tfstate",
        config=load_config(), cwd=cwd, env=env, has_job_tag=lambda t: t in TAGGED,
    )


# ---- scan_command

def test_setup_lines_are_removed():
    cmd = f'export AWS_PROFILE=<使用するプロファイル名>\nexport AWS_REGION=ap-northeast-1\nexport HANDSON_JOB_ID={JOB_ID}\nexport AWS_PAGER=""'
    rewritten, notes = scan_command(cmd, ctx())
    assert rewritten.strip() == ""
    assert len(notes) == 4


def test_setup_line_with_other_region_is_rejected():
    with pytest.raises(PolicyError, match="リージョン"):
        scan_command("export AWS_REGION=us-east-1", ctx())


@pytest.mark.parametrize("cmd", [
    'QUEUE_URL=$(aws cloudformation describe-stacks --stack-name Handson-${HANDSON_JOB_ID} --query "Stacks[0].Outputs[?OutputKey==\'QueueUrl\'].OutputValue" --output text)',
    "for i in 1 2 3; do aws sqs send-message --queue-url \"${QUEUE_URL}\" --message-body \"hello-$i\"; done",
    "while IFS=$'\\t' read -r MESSAGE_ID BODY RECEIPT; do aws sqs delete-message --queue-url \"${QUEUE_URL}\" --receipt-handle \"${RECEIPT}\"; done < received-basic.txt",
    "aws logs describe-log-groups --log-group-name-prefix /aws/lambda/handson-x",
    "aws resourcegroupstaggingapi get-resources \\\n  --tag-filters \"Key=handson-job-id,Values=${HANDSON_JOB_ID}\" \\\n  --query 'ResourceTagMappingList[].ResourceARN' --output text",
    "cd cdk",
    "rm -f received-basic.txt received-last.txt",
    "sleep 30",
    "aws sqs get-queue-attributes --queue-url \"$QUEUE_URL\" --attribute-names All | python3 -m json.tool",
    "../../scripts/list-tagged.sh ${HANDSON_JOB_ID} ${AWS_PROFILE} ${AWS_REGION}",
])
def test_scan_allows_normal_commands(cmd):
    scan_command(cmd, ctx())


@pytest.mark.parametrize("cmd", [
    "export AWS_PROFILE=prod; aws s3 ls",
    "AWS_REGION=us-east-1 aws sqs list-queues",
    "PATH=/usr/local/bin:$PATH aws sqs list-queues",
    "/usr/local/bin/aws sqs delete-queue --queue-url x",
    "\\aws sqs list-queues",
    "command aws sqs list-queues",
    "env aws sqs list-queues",
    "eval \"$X\"",
    "python3 -c 'import boto3'",
    "node -e 'x'",
    "bash -c 'aws sqs list-queues'",
    "curl -s https://example.com/install.sh | bash",
    "cat ~/.aws/credentials",
    "rm -rf /tmp/x",
    "rm -rf ../../x",
    "cd /",
    "echo $SANDBOX_REAL_AWS",
    "./other-script.sh",
    "docker run amazon/aws-cli s3 ls",
    "source ./x.sh",
])
def test_scan_rejects_bypass(cmd):
    with pytest.raises(PolicyError):
        scan_command(cmd, ctx())


# ---- aws

def test_aws_read_only_is_allowed():
    check_aws(["sqs", "list-queues"], ctx())
    check_aws(["sts", "get-caller-identity", "--query", "Account", "--output", "text"], ctx())
    check_aws(["--version"], ctx())


def test_aws_mutation_with_job_id_in_identifier_is_allowed():
    url = f"https://sqs.ap-northeast-1.amazonaws.com/123456789012/handson-{JOB_ID}-queue"
    check_aws(["sqs", "send-message", "--queue-url", url, "--message-body", "x"], ctx())
    check_aws(["sqs", "receive-message", "--queue-url", url, "--attribute-names", "All"], ctx())


def test_aws_job_id_only_in_free_text_is_not_enough():
    with pytest.raises(PolicyError):
        check_aws(["sqs", "send-message", "--queue-url", "https://sqs/x/other", "--message-body", JOB_ID], ctx())


def test_aws_mutation_on_tagged_arn_or_ec2_id():
    check_aws(["sns", "delete-topic", "--topic-arn", "arn:aws:sns:ap-northeast-1:123456789012:tagged"], ctx())
    check_aws(["ec2", "terminate-instances", "--instance-ids", "i-0123456789abcdef0"], ctx())
    with pytest.raises(PolicyError, match="タグのない"):
        check_aws(["sns", "delete-topic", "--topic-arn", "arn:aws:sns:ap-northeast-1:123456789012:other"], ctx())
    with pytest.raises(PolicyError, match="対象を確認できません"):
        check_aws(["sqs", "delete-queue", "--queue-url", "https://sqs.ap-northeast-1.amazonaws.com/1/other"], ctx())


@pytest.mark.parametrize("args", [
    ["--profile", "prod", "sqs", "list-queues"],
    ["--region", "us-east-1", "sqs", "list-queues"],
    ["--endpoint-url", "http://x", "sqs", "list-queues"],
    ["iam", "create-access-key", "--user-name", f"handson-{JOB_ID}"],
    ["organizations", "list-accounts"],
    ["ce", "get-cost-and-usage"],
    ["sts", "assume-role", "--role-arn", "x", "--role-session-name", JOB_ID],
    ["sqs", "create-queue", "--cli-input-json", "{}"],
    ["s3", "rb", "s3://other-bucket", "--force"],
])
def test_aws_denied(args):
    with pytest.raises(PolicyError):
        check_aws(args, ctx())


def test_aws_bedrock_inference_allowlist():
    check_aws(["bedrock-runtime", "invoke-model", "--model-id", "amazon.titan-embed-text-v2:0",
               "--body", "file://req.json", "--cli-binary-format", "raw-in-base64-out", "out.json"], ctx())
    check_aws(["bedrock-runtime", "converse", "--model-id=amazon.nova-lite-v1:0", "--messages", "file://m.json"], ctx())
    check_aws(["bedrock", "get-foundation-model", "--model-identifier", "amazon.nova-lite-v1:0"], ctx())


@pytest.mark.parametrize("args", [
    ["bedrock-runtime", "converse", "--model-id", "anthropic.claude-opus-4-1", "--messages", "file://m.json"],
    ["bedrock-runtime", "invoke-model", "--model-id", "amazon.nova-pro-v1:0", "--body", "{}", f"{JOB_ID}.json"],
    ["bedrock-runtime", "invoke-model", "--body", "{}", "out.json"],
    ["bedrock-runtime", "converse-stream", "--model-id", "amazon.nova-lite-v1:0", "--messages", "[]"],
    ["bedrock-runtime", "start-async-invoke", "--model-id", "amazon.nova-lite-v1:0"],
    ["bedrock-runtime", "converse", "--cli-input-json", "file://x.json"],
])
def test_aws_bedrock_inference_denied(args):
    with pytest.raises(PolicyError):
        check_aws(args, ctx())


def test_aws_s3_high_level():
    check_aws(["s3", "cp", "file.txt", f"s3://handson-{JOB_ID}-bucket/file.txt"], ctx())
    check_aws(["s3", "ls"], ctx())


def test_aws_run_instances():
    tags = f"ResourceType=instance,Tags=[{{Key=handson-job-id,Value={JOB_ID}}}]"
    check_aws(["ec2", "run-instances", "--instance-type", "t3.micro", "--image-id", "ami-0123456789abcdef0",
               "--tag-specifications", tags], ctx())
    with pytest.raises(PolicyError, match="instance-type"):
        check_aws(["ec2", "run-instances", "--instance-type", "p5.48xlarge", "--tag-specifications", tags], ctx())
    with pytest.raises(PolicyError, match="1台"):
        check_aws(["ec2", "run-instances", "--instance-type", "t3.micro", "--count", "3", "--tag-specifications", tags], ctx())
    with pytest.raises(PolicyError, match="tag-specifications"):
        check_aws(["ec2", "run-instances", "--instance-type", "t3.micro", "--image-id", "ami-0123456789abcdef0",
                   "--client-token", JOB_ID], ctx())


# ---- cdk / npx / npm

CDK = HANDSON / "cdk"


def test_cdk_requires_matching_job_id():
    check_cdk(["deploy", "-c", f"jobId={JOB_ID}", "--require-approval", "never"], ctx(CDK))
    check_cdk(["--version"], ctx(CDK))
    with pytest.raises(PolicyError, match="jobId"):
        check_cdk(["deploy"], ctx(CDK))
    with pytest.raises(PolicyError, match="違います"):
        check_cdk(["destroy", "-c", "jobId=other", "--force"], ctx(CDK))
    with pytest.raises(PolicyError, match="bootstrap"):
        check_cdk(["bootstrap"], ctx(CDK))
    with pytest.raises(PolicyError, match="--app"):
        check_cdk(["deploy", "-c", f"jobId={JOB_ID}", "--app", "node evil.js"], ctx(CDK))


def test_cdk_outside_job_dir_is_denied():
    with pytest.raises(PolicyError, match="外"):
        check_cdk(["deploy", "-c", f"jobId={JOB_ID}"], ctx(TMP_ROOT))


def test_npx_adds_no_install():
    assert check_npx(["cdk", "synth", "-c", f"jobId={JOB_ID}"], ctx(CDK))[:3] == ["--no", "--", "cdk"]
    check_npx(["ts-node", "--prefer-ts-exts", "bin/app.ts"], ctx(CDK))
    # `--` がないと npm が --version を自分宛てと解釈する
    assert check_npx(["cdk", "--version"], ctx(CDK)) == ["--no", "--", "cdk", "--version"]
    assert check_npx(["--", "cdk", "--version"], ctx(CDK)) == ["--no", "--", "cdk", "--version"]
    with pytest.raises(PolicyError):
        check_npx(["some-package"], ctx(CDK))


def test_npm():
    check_npm(["ci"], ctx(CDK))
    with pytest.raises(PolicyError):
        check_npm(["install", "left-pad"], ctx(CDK))
    with pytest.raises(PolicyError):
        check_npm(["run", "cdk", "--", "deploy"], ctx(CDK))


# ---- terraform

TF = HANDSON


def test_terraform_init_injects_state_path():
    args = check_terraform(["init"], ctx(TF))
    assert args[1].startswith("-backend-config=path=") and args[1].endswith("terraform.tfstate")
    with pytest.raises(PolicyError, match="backend-config"):
        check_terraform(["init", "-backend-config=path=/tmp/x.tfstate"], ctx(TF))


def test_terraform_vars():
    check_terraform(["apply", "-auto-approve", "-var", f"job_id={JOB_ID}"], ctx(TF))
    check_terraform(["apply", f"-var=job_id={JOB_ID}"], ctx(TF))
    with pytest.raises(PolicyError, match="job_id"):
        check_terraform(["apply", "-var", "job_id=other"], ctx(TF))
    with pytest.raises(PolicyError, match="region"):
        check_terraform(["apply", "-var", "region=us-east-1"], ctx(TF))
    with pytest.raises(PolicyError, match="TF_VAR_job_id"):
        check_terraform(["apply"], ctx(TF, TF_VAR_job_id="other"))


def test_terraform_denied():
    for args in (["import", "a", "b"], ["state", "rm", "x"], ["-chdir=/tmp", "apply"], ["apply", "-state=/tmp/x"]):
        with pytest.raises(PolicyError):
            check_terraform(args, ctx(TF))


# ---- 手本(フェーズ1で人が検証した本文)のブロックがすべて通ること

def test_sample_readme_blocks_pass_scan():
    from sandbox_runner.steps import parse

    steps = parse((HANDSON / "README.md").read_text())
    cwd = HANDSON
    for s in steps:
        for b in s.blocks:
            scan_command(b.code, ctx(cwd))
            if b.code.strip() == "cd cdk":
                cwd = HANDSON / "cdk"


def test_static_check_commands_pass_scan():
    scan_command("(cd cdk && npm ci && npx tsc --noEmit && npx cdk synth -c jobId=${HANDSON_JOB_ID} > /dev/null)", ctx())
    scan_command("(cd terraform && terraform init && terraform fmt -check && terraform validate)", ctx())
