"""実行してよいコマンドかを判定する。

2段で守る。
1. scan_command: run_step に渡されたシェルのコマンド文字列を実行前に検査する。ランナーが固定した環境変数の
   上書き、ガードを迂回する呼び出し(絶対パスでの aws、eval、インタープリター経由など)を拒否する。
2. check_*: PATH の先頭に置いたシム(shims/)から呼ばれ、aws / cdk / npx / npm / terraform の引数を検査する。
   変更系の操作は、対象の識別子にジョブIDが含まれるか、対象に handson-job-id タグが付いていることを確かめる。

どちらも「多層防御の1層」であり、シェルの意味を完全に解釈するものではない。被害範囲の最終的な境界は、
検証専用アカウントと IAM 権限である(設計書「セキュリティとコスト管理」)。
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


class PolicyError(Exception):
    """ポリシー違反。メッセージはそのまま検証担当に返す。"""


@dataclass
class Context:
    job_id: str
    profile: str
    region: str
    tag_key: str
    repo_root: Path
    allowed_roots: list[Path]
    tfstate: Path
    config: dict
    cwd: Path = field(default_factory=Path.cwd)
    env: dict = field(default_factory=dict)
    # ARN または EC2 のリソースIDに、このジョブのタグが付いているか
    has_job_tag: Callable[[str], bool] | None = None

    @property
    def sandbox_cfg(self) -> dict:
        return self.config.get("sandbox", {})


# ---------------------------------------------------------------- 1. コマンド文字列の検査

# 本文の「環境変数を設定する」手順の行。ランナーが固定値を設定済みなので、実行せずに取り除く
SETUP_LINE = re.compile(
    r"^\s*export\s+(AWS_PROFILE|AWS_REGION|AWS_DEFAULT_REGION|HANDSON_JOB_ID|AWS_PAGER)="
    r"(\"[^\"$`]*\"|'[^']*'|<[^>]*>|[\w.-]*)\s*(?:#.*)?$"
)

PROTECTED_VARS = (
    r"PATH|AWS_PROFILE|AWS_DEFAULT_PROFILE|AWS_REGION|AWS_DEFAULT_REGION|AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY"
    r"|AWS_SESSION_TOKEN|AWS_CONFIG_FILE|AWS_SHARED_CREDENTIALS_FILE|AWS_ENDPOINT_URL\w*|AWS_CA_BUNDLE"
    r"|AWS_EXECUTION_ENV|AWS_SDK_UA_APP_ID|HANDSON_JOB_ID|BASH_ENV|ENV|LD_PRELOAD|DYLD_\w+|NODE_OPTIONS"
    r"|CDK_DEFAULT_ACCOUNT|CDK_DEFAULT_REGION|TF_CLI_ARGS\w*|TF_DATA_DIR|PYTHON\w*|HOME"
)
# コマンドの先頭になりうる位置
CMD_POS = r"(?:^|[;&|({`!\n]|\$\(|\b(?:then|do|else|elif|if|while|until|time|xargs)\s)\s*"
FORBIDDEN: list[tuple[re.Pattern, str]] = [
    (re.compile(r"SANDBOX_"), "ランナーの内部変数は参照できません"),
    (re.compile(rf"(?:^|[\s;&|(]|\bexport\s+|\bdeclare\s+-\w+\s+|\breadonly\s+)(?:{PROTECTED_VARS})\+?="),
     "ランナーが固定した環境変数(プロファイル、リージョン、ジョブID、PATH、認証情報など)は変更できません"),
    (re.compile(CMD_POS + r"(?:unset|alias|unalias|hash|enable|builtin|command|exec|eval|source|trap|declare\s+-f|"
                r"env|sudo|su|doas|ssh|scp|docker|podman|nerdctl|finch|uv|uvx|pip3?|pipx|brew|aws-vault|granted|"
                r"tofu|sam|copilot|eb)\b"),
     "ガードを迂回できるコマンド(eval、source、env、sudo、docker など)は使えません"),
    (re.compile(CMD_POS + r"\.\s+\S"), "`.`(source)は使えません"),
    (re.compile(CMD_POS + r"(?:python3?(?!\s+-m\s+json\.tool\b)|perl|ruby|node|deno|bun|php|osascript|pwsh|"
                r"powershell|lua|tclsh|java|go)\b"),
     "インタープリターの直接実行は使えません(`python3 -m json.tool` だけ許可)"),
    (re.compile(CMD_POS + r"(?:ba|z|da|k|c|tc|fi)?sh\s+(?:-\w*c|-s\b|<)"), "`bash -c` などの入れ子のシェルは使えません"),
    (re.compile(r"\|\s*(?:\S*/)?(?:ba|z|da|k|c|tc|fi)?sh\b"), "パイプでシェルに渡す実行は使えません"),
    (re.compile(CMD_POS + r"\\\w"), "`\\aws` のようなエイリアス回避の呼び出しは使えません"),
    (re.compile(r"(?:~|\$HOME|\$\{HOME\})/\.aws\b|\.aws/(?:credentials|config)\b"), "AWS の認証情報ファイルには触れません"),
    (re.compile(CMD_POS + r"rm\b[^;&|\n]*\s(?:/|~|\$HOME|\.\.)"), "`rm` で作業ディレクトリの外は消せません"),
    (re.compile(CMD_POS + r"cd\s+(?:/|~|\$HOME|\$\{HOME\})"), "作業ディレクトリの外(絶対パス、ホーム)には移動できません"),
    (re.compile(CMD_POS + r"(?:chmod|chown|ln|mount|crontab|launchctl|nohup|disown|setsid|screen|tmux)\b"),
     "このコマンドは使えません"),
]
# スラッシュを含むパスで起動されるコマンド(./x.sh、../../../scripts/list-tagged.sh、/usr/local/bin/aws)
PATH_INVOKE = re.compile(CMD_POS + r"((?:\.{1,2}|~)?/?(?:[\w.@+-]+/)+[\w.@+-]+)")
# パス指定で実行してよいリポジトリのスクリプト(読み取り専用のもの)
REPO_SCRIPTS = {"scripts/list-tagged.sh", "scripts/aws-identity.sh"}


def scan_command(command: str, ctx: Context) -> tuple[str, list[str]]:
    """実行前の検査。取り除いた環境変数の設定行などを notes で返す。違反は PolicyError。"""
    notes: list[str] = []
    kept: list[str] = []
    for line in command.splitlines():
        m = SETUP_LINE.match(line)
        if not m:
            kept.append(line)
            continue
        name, value = m.group(1), m.group(2).strip("'\"")
        if name in ("AWS_REGION", "AWS_DEFAULT_REGION") and value != ctx.region:
            raise PolicyError(f"本文のリージョン {value} が、ジョブで固定したリージョン {ctx.region} と違います")
        if name == "HANDSON_JOB_ID" and value != ctx.job_id and not value.startswith("<"):
            notes.append(f"本文の HANDSON_JOB_ID={value} はジョブID {ctx.job_id} と違うため、ジョブIDを使った")
        notes.append(f"`export {name}=...` はランナーの固定値で置き換えた(実行していない)")
    rewritten = "\n".join(kept)

    for pattern, message in FORBIDDEN:
        m = pattern.search(rewritten)
        if m:
            raise PolicyError(f"{message}: `{m.group(0).strip()}`")
    for m in PATH_INVOKE.finditer(rewritten):
        _check_path_invoke(m.group(1), ctx)
    return rewritten, notes


def _check_path_invoke(path: str, ctx: Context) -> None:
    target = (ctx.cwd / Path(path).expanduser()).resolve()
    try:
        rel = target.relative_to(ctx.repo_root.resolve()).as_posix()
    except ValueError:
        rel = None
    if rel not in REPO_SCRIPTS:
        raise PolicyError(
            f"パスを指定したコマンドの実行は、リポジトリの読み取り専用スクリプト({', '.join(sorted(REPO_SCRIPTS))})"
            f"だけ許可しています: `{path}`"
        )


def check_cwd(ctx: Context) -> None:
    cwd = ctx.cwd.resolve()
    if not any(cwd == r or r in cwd.parents for r in ctx.allowed_roots):
        raise PolicyError(f"作業ディレクトリ {cwd} はジョブのディレクトリの外です")


# ---------------------------------------------------------------- 2. aws CLI

AWS_GLOBAL_WITH_VALUE = {
    "--profile", "--region", "--output", "--query", "--endpoint-url", "--color", "--ca-bundle",
    "--cli-read-timeout", "--cli-connect-timeout", "--cli-binary-format",
}
# 値に識別子が入らない(自由記述の)オプション。ジョブIDが入っていても対象の確認には使わない
FREE_TEXT_OPTIONS = {
    "--query", "--output", "--message-body", "--message", "--payload", "--body", "--description", "--comment",
    "--subject", "--cli-binary-format", "--color", "--message-attributes", "--message-group-id",
}
READ_ONLY_OP = re.compile(
    r"^(?:get|list|describe|head|batch-get|scan|query|lookup|search|filter|select|validate|estimate|simulate|"
    r"test|check|preview|detect|tail|wait|help|start-query|stop-query|generate-presigned|presign|ls)(?:-|$)"
)
S3_HIGH_LEVEL = {"cp", "mv", "rm", "sync", "mb", "rb", "ls", "presign", "website"}
ARN = re.compile(r"arn:aws[\w-]*:[\w-]+:[\w-]*:\d{0,12}:[^\s\"',\]\}]+")
EC2_ID = re.compile(r"\b(?:i|vol|sg|subnet|vpc|igw|rtb|eni|snap|ami|eipalloc|nat|vpce|lt|acl|eigw|tgw|pcx|key)-[0-9a-f]{8,17}\b")
DENIED_INSTANCE_FAMILY = re.compile(r"^(?:p|g|inf|trn|x|u-|dl|f|vt)\d|\.metal")


def _split_aws(args: list[str]) -> tuple[list[str], dict[str, list[str]], list[str]]:
    """(位置引数, オプション→値のリスト, 位置引数のうちサービスと操作以降の値) に分ける。"""
    positionals: list[str] = []
    options: dict[str, list[str]] = {}
    i = 0
    current: str | None = None
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            name, eq, value = a.partition("=")
            options.setdefault(name, [])
            if eq:
                options[name].append(value)
                current = None
            elif name in AWS_GLOBAL_WITH_VALUE and i + 1 < len(args):
                options[name].append(args[i + 1])
                i += 1
                current = None
            else:
                current = name
        elif current is not None:
            options[current].append(a)
        else:
            positionals.append(a)
        i += 1
    return positionals[:2], options, positionals[2:]


def check_aws(args: list[str], ctx: Context) -> list[str]:
    positionals, options, rest = _split_aws(args)
    _check_profile_region(options, ctx)
    if "--endpoint-url" in options or "--no-verify-ssl" in options or "--ca-bundle" in options:
        raise PolicyError("--endpoint-url / --no-verify-ssl / --ca-bundle は使えません")
    if not positionals:
        if "--version" in options or not args:
            return args
        raise PolicyError("aws のサービス名がありません")
    service = positionals[0]
    op = positionals[1] if len(positionals) > 1 else ""
    cfg = ctx.sandbox_cfg
    if service in cfg.get("deniedAwsServices", []):
        raise PolicyError(f"aws {service} は使えません(アカウントや請求に関わる操作のため)")
    if f"{service}:{op}" in cfg.get("deniedAwsOperations", []):
        raise PolicyError(f"aws {service} {op} は使えません(権限や監査を変える操作のため)")
    if op in ("help", "") or "help" in rest:
        return args

    if service == "s3" and op in S3_HIGH_LEVEL:
        _check_s3_high_level(op, args, ctx)
        return args
    if READ_ONLY_OP.match(op):
        return args
    if "--cli-input-json" in options or "--cli-input-yaml" in options:
        raise PolicyError("変更系の操作で --cli-input-json / --cli-input-yaml は使えません(対象を確認できないため)")
    if service == "ec2" and op == "run-instances":
        _check_run_instances(options, ctx)

    values = rest + [v for name, vs in options.items() if name not in FREE_TEXT_OPTIONS for v in vs]
    if any(ctx.job_id in v for v in values):
        return args
    targets = sorted({m for v in values for m in ARN.findall(v)} | {m for v in values for m in EC2_ID.findall(v)})
    if targets and ctx.has_job_tag is not None:
        untagged = [t for t in targets if not ctx.has_job_tag(t)]
        if not untagged:
            return args
        raise PolicyError(f"{ctx.tag_key}={ctx.job_id} タグのないリソースは変更できません: {', '.join(untagged)}")
    raise PolicyError(
        f"aws {service} {op} の対象を確認できません。対象の名前・URL・ARN にジョブID({ctx.job_id})が含まれるか、"
        f"{ctx.tag_key} タグが付いたリソースを ARN / ID で指定してください"
    )


def _check_profile_region(options: dict[str, list[str]], ctx: Context) -> None:
    for v in options.get("--profile", []):
        if v != ctx.profile:
            raise PolicyError(f"--profile {v} は使えません(ジョブで固定したプロファイルは {ctx.profile})")
    for v in options.get("--region", []):
        if v != ctx.region:
            raise PolicyError(f"--region {v} は使えません(ジョブで固定したリージョンは {ctx.region})")


def _check_s3_high_level(op: str, args: list[str], ctx: Context) -> None:
    if op in ("ls", "presign"):
        return
    buckets = [a[5:].split("/", 1)[0] for a in args if a.startswith("s3://")]
    if not buckets:
        raise PolicyError(f"aws s3 {op} の対象バケットがありません")
    bad = [b for b in buckets if ctx.job_id not in b]
    if bad:
        raise PolicyError(f"バケット名にジョブID({ctx.job_id})を含まないバケットは操作できません: {', '.join(bad)}")


def _check_run_instances(options: dict[str, list[str]], ctx: Context) -> None:
    allowed = ctx.sandbox_cfg.get("ec2AllowedInstanceTypes", [])
    types = options.get("--instance-type", [])
    if not types or any(t not in allowed or DENIED_INSTANCE_FAMILY.search(t) for t in types):
        raise PolicyError(f"--instance-type は {', '.join(allowed)} のいずれかを指定してください")
    for name in ("--count", "--max-count", "--min-count"):
        for v in options.get(name, []):
            if any(int(n) > 1 for n in re.findall(r"\d+", v)):
                raise PolicyError("インスタンスは1台だけ起動できます")
    specs = " ".join(options.get("--tag-specifications", []))
    if ctx.tag_key not in specs or ctx.job_id not in specs:
        raise PolicyError(f"--tag-specifications で {ctx.tag_key}={ctx.job_id} タグを付けてください")


# ---------------------------------------------------------------- 3. CDK / npx / npm

CDK_ALLOWED = {"synth", "synthesize", "deploy", "destroy", "diff", "ls", "list", "doctor", "notices", "acknowledge", "ack"}
CDK_NEEDS_JOB = {"synth", "synthesize", "deploy", "destroy", "diff", "ls", "list"}
CDK_DENIED_OPTIONS = {"--app", "-a", "--role-arn", "-r", "--toolkit-stack-name", "--plugin", "--output", "-o"}
CDK_APP = re.compile(r"^npx (?:ts-node --prefer-ts-exts|tsx) bin/[\w-]+\.ts$")


def check_cdk(args: list[str], ctx: Context) -> list[str]:
    check_cwd(ctx)
    sub = next((a for a in args if not a.startswith("-")), None)
    if sub is None:
        if any(a in ("--version", "-h", "--help") for a in args):
            return args
        raise PolicyError("cdk のサブコマンドがありません")
    if sub not in CDK_ALLOWED:
        raise PolicyError(f"cdk {sub} は使えません(使えるのは {', '.join(sorted(CDK_ALLOWED))})")
    contexts: list[str] = []
    for i, a in enumerate(args):
        name, eq, value = a.partition("=")
        if name in CDK_DENIED_OPTIONS:
            raise PolicyError(f"cdk の {name} オプションは使えません")
        if name == "--profile":
            v = value if eq else (args[i + 1] if i + 1 < len(args) else "")
            if v != ctx.profile:
                raise PolicyError(f"--profile {v} は使えません(ジョブで固定したプロファイルは {ctx.profile})")
        if a in ("-c", "--context") and i + 1 < len(args):
            contexts.append(args[i + 1])
        elif name in ("-c", "--context") and eq:
            contexts.append(value)
    if sub in CDK_NEEDS_JOB:
        job_ctx = [c.partition("=")[2] for c in contexts if c.startswith("jobId=")]
        if not job_ctx:
            raise PolicyError("cdk には -c jobId=<ジョブID> を指定してください")
        if any(v != ctx.job_id for v in job_ctx):
            raise PolicyError(f"-c jobId の値がジョブID({ctx.job_id})と違います: {', '.join(job_ctx)}")
        _check_cdk_app(ctx)
    return args


def _check_cdk_app(ctx: Context) -> None:
    cdk_json = ctx.cwd / "cdk.json"
    if not cdk_json.is_file():
        raise PolicyError(f"{ctx.cwd} に cdk.json がありません")
    app = json.loads(cdk_json.read_text()).get("app", "")
    if not CDK_APP.match(app):
        raise PolicyError(f"cdk.json の app は `npx ts-node --prefer-ts-exts bin/<名前>.ts` にしてください(現在: {app!r})")


NPX_FLAGS = {"--yes", "-y", "--no", "--no-install", "--quiet", "-q"}


def check_npx(args: list[str], ctx: Context) -> list[str]:
    check_cwd(ctx)
    rest = [a for a in args if a not in NPX_FLAGS]
    if rest in (["--version"], ["-v"]):
        return args
    if not rest:
        raise PolicyError("npx の実行するパッケージがありません")
    pkg = rest[0]
    if pkg.startswith("-"):
        raise PolicyError(f"npx の {pkg} オプションは使えません")
    if pkg in ("cdk", "aws-cdk"):
        check_cdk(rest[1:], ctx)
    elif pkg not in ("tsc", "ts-node", "tsx"):
        raise PolicyError(f"npx {pkg} は使えません(使えるのは cdk / tsc / ts-node / tsx)")
    # プロジェクトに入っていないパッケージをレジストリから取ってこない(npm ci の漏れを検出するため)
    return ["--no"] + rest


NPM_RUN_ALLOWED = {"build", "test"}
NPM_LIFECYCLE = {"preinstall", "install", "postinstall", "prepare", "preprepare", "postprepare"}


def check_npm(args: list[str], ctx: Context) -> list[str]:
    check_cwd(ctx)
    positionals = [a for a in args if not a.startswith("-")]
    if not positionals:
        if any(a in ("--version", "-v") for a in args):
            return args
        raise PolicyError("npm のサブコマンドがありません")
    sub = positionals[0]
    if sub in ("ci", "install", "i"):
        if len(positionals) > 1:
            raise PolicyError("npm install でのパッケージの追加はできません(package.json に書いて npm ci を使う)")
        pkg = ctx.cwd / "package.json"
        if pkg.is_file():
            hooks = NPM_LIFECYCLE & set(json.loads(pkg.read_text()).get("scripts", {}))
            if hooks:
                raise PolicyError(f"package.json のインストール時スクリプトは使えません: {', '.join(sorted(hooks))}")
        return args
    if sub in ("ls", "list", "outdated", "view"):
        return args
    if sub in ("run", "run-script") and len(positionals) > 1 and positionals[1] in NPM_RUN_ALLOWED:
        return args
    raise PolicyError(f"npm {' '.join(positionals[:2])} は使えません(cdk は `npx cdk` で実行する)")


# ---------------------------------------------------------------- 4. Terraform

TF_ALLOWED = {"init", "validate", "fmt", "plan", "apply", "destroy", "output", "show", "version", "providers", "graph", "state"}
TF_STATE_READ = {"list", "show"}
TF_VAR = re.compile(r"^-var=?(.*)$")


def check_terraform(args: list[str], ctx: Context) -> list[str]:
    check_cwd(ctx)
    for a in args:
        if a.startswith("-chdir"):
            raise PolicyError("terraform の -chdir は使えません(作業ディレクトリで実行する)")
    sub = next((a for a in args if not a.startswith("-")), None)
    if sub is None:
        if any(a in ("-version", "--version", "-help", "--help") for a in args):
            return args
        raise PolicyError("terraform のサブコマンドがありません")
    if sub not in TF_ALLOWED:
        raise PolicyError(f"terraform {sub} は使えません(使えるのは {', '.join(sorted(TF_ALLOWED))})")
    idx = args.index(sub)
    rest = args[idx + 1:]
    if sub == "state":
        if not rest or rest[0] not in TF_STATE_READ:
            raise PolicyError("terraform state は list / show だけ使えます")
        return args
    for a in rest:
        if a.startswith(("-state=", "-state-out=", "-backup=")) or a in ("-state", "-state-out"):
            raise PolicyError("terraform の -state / -state-out / -backup は使えません(state はランナーが管理する)")

    env_job = ctx.env.get("TF_VAR_job_id")
    if env_job is not None and env_job != ctx.job_id:
        raise PolicyError(f"TF_VAR_job_id の値がジョブID({ctx.job_id})と違います")
    env_region = ctx.env.get("TF_VAR_region")
    if env_region is not None and env_region != ctx.region:
        raise PolicyError(f"TF_VAR_region の値がジョブのリージョン({ctx.region})と違います")
    for i, a in enumerate(rest):
        m = TF_VAR.match(a)
        if not m:
            continue
        assignment = m.group(1) or (rest[i + 1] if i + 1 < len(rest) else "")
        name, _, value = assignment.partition("=")
        if name == "job_id" and value != ctx.job_id:
            raise PolicyError(f"-var job_id の値がジョブID({ctx.job_id})と違います: {value}")
        if name == "region" and value != ctx.region:
            raise PolicyError(f"-var region の値がジョブのリージョン({ctx.region})と違います: {value}")

    if sub == "init":
        configs = [a for a in rest if a.startswith("-backend-config")]
        wanted = f"-backend-config=path={ctx.tfstate}"
        if not configs:
            # 読者向けの本文は `terraform init` のまま。検証では state をジョブディレクトリに置く(iac-terraform の規約)
            return args[: idx + 1] + [wanted] + rest
        joined = " ".join(configs)
        if str(ctx.tfstate) not in joined:
            raise PolicyError(f"-backend-config の state の置き場所はランナーが決めます({ctx.tfstate})")
    return args


def shell_quote(args: list[str]) -> str:
    return " ".join(shlex.quote(a) for a in args)
