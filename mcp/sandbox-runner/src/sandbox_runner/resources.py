"""タグ付きリソースの棚卸し、タグの確認、削除。

触れてよいのは handson-job-id タグが付いたリソースだけ。削除の直前にもう一度タグを確かめる。
対応していない種類のリソースは消さずに「要手動削除」として返す。
"""

from __future__ import annotations

import datetime as dt
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Callable

import boto3
from botocore.exceptions import ClientError

EC2_ID_PREFIX = {
    "i": "instance", "vol": "volume", "sg": "security-group", "subnet": "subnet", "vpc": "vpc",
    "igw": "internet-gateway", "rtb": "route-table", "eni": "network-interface", "snap": "snapshot",
    "ami": "image", "eipalloc": "elastic-ip", "nat": "natgateway", "vpce": "vpc-endpoint",
    "lt": "launch-template", "acl": "network-acl", "eigw": "egress-only-internet-gateway",
    "tgw": "transit-gateway", "pcx": "vpc-peering-connection", "key": "key-pair",
}
NOT_FOUND = {
    "ResourceNotFoundException", "NoSuchEntity", "NoSuchBucket", "AWS.SimpleQueueService.NonExistentQueue",
    "QueueDoesNotExist", "NotFound", "NotFoundException", "ParameterNotFound", "RepositoryNotFoundException",
    "StateMachineDoesNotExist", "InvalidInstanceID.NotFound", "InvalidGroup.NotFound", "InvalidVolume.NotFound",
    "InvalidSnapshot.NotFound", "InvalidVpcID.NotFound", "InvalidSubnetID.NotFound",
    "InvalidInternetGatewayID.NotFound", "InvalidRouteTableID.NotFound", "InvalidAllocationID.NotFound",
    "InvalidNetworkInterfaceID.NotFound", "InvalidKeyPair.NotFound",
}


def error_code(e: ClientError) -> str:
    return e.response.get("Error", {}).get("Code", "")


@dataclass
class Resource:
    arn: str
    kind: str  # 例: sqs:queue / cloudformation:stack / iam:role / logs:log-group(名前一致)
    source: str  # tagging-api / cloudformation / iam / name-match
    exists: bool | None = None  # None = 実在を確かめる手段がない種類
    created_at: str | None = None
    note: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v not in (None, "")}


@dataclass
class Inventory:
    resources: list[Resource] = field(default_factory=list)

    @property
    def remaining(self) -> list[Resource]:
        """実在する(または確かめられない)もの。タグ API の反映待ちで残っている削除済みのものは除く。"""
        return [r for r in self.resources if r.exists is not False]

    def to_dict(self) -> dict:
        return {
            "remainingCount": len(self.remaining),
            "remaining": [r.to_dict() for r in self.remaining],
            "pendingPropagation": [r.to_dict() for r in self.resources if r.exists is False],
        }


def parse_arn(arn: str) -> dict:
    parts = arn.split(":", 5)
    service, region, account, resource = parts[2], parts[3], parts[4], parts[5]
    rtype, _, rid = resource.partition("/") if "/" in resource.split(":")[0] else resource.partition(":")
    return {"service": service, "region": region, "account": account, "type": rtype, "id": rid, "resource": resource}


def kind_of(arn: str) -> str:
    a = parse_arn(arn)
    if a["service"] in ("sqs", "sns", "s3"):
        return {"sqs": "sqs:queue", "sns": "sns:topic", "s3": "s3:bucket"}[a["service"]]
    if a["service"] == "s3vectors":
        # arn:aws:s3vectors:<region>:<account>:bucket/<bucket>[/index/<index>]
        return "s3vectors:index" if "/index/" in a["id"] else "s3vectors:bucket"
    return f"{a['service']}:{a['type']}"


class Aws:
    """ジョブで固定したプロファイル・リージョンの boto3 クライアントをまとめる。"""

    def __init__(self, profile: str, region: str, session: boto3.Session | None = None):
        self.session = session or boto3.Session(profile_name=profile, region_name=region)
        self.region = region
        self._clients: dict[str, object] = {}

    def client(self, name: str):
        if name not in self._clients:
            self._clients[name] = self.session.client(name, region_name=self.region)
        return self._clients[name]

    # ------------------------------------------------------------ タグの確認

    def has_job_tag(self, target: str, tag_key: str, job_id: str) -> bool:
        if target.startswith("arn:"):
            a = parse_arn(target)
            if a["service"] == "iam":
                tags = self._iam_tags(a["type"], a["id"].split("/")[-1], target)
                return tags.get(tag_key) == job_id
            if a["service"] == "s3vectors":
                return self._s3vectors_tags(target).get(tag_key) == job_id
            res = self.client("resourcegroupstaggingapi").get_resources(ResourceARNList=[target])
            for m in res.get("ResourceTagMappingList", []):
                if {t["Key"]: t["Value"] for t in m.get("Tags", [])}.get(tag_key) == job_id:
                    return True
            return False
        prefix = target.split("-", 1)[0]
        if prefix in EC2_ID_PREFIX:
            res = self.client("ec2").describe_tags(Filters=[
                {"Name": "resource-id", "Values": [target]},
                {"Name": "key", "Values": [tag_key]},
            ])
            return any(t["Value"] == job_id for t in res.get("Tags", []))
        return False

    def _iam_tags(self, rtype: str, name: str, arn: str) -> dict:
        iam = self.client("iam")
        try:
            if rtype == "role":
                tags = iam.list_role_tags(RoleName=name)["Tags"]
            elif rtype == "policy":
                tags = iam.list_policy_tags(PolicyArn=arn)["Tags"]
            elif rtype == "instance-profile":
                tags = iam.list_instance_profile_tags(InstanceProfileName=name)["Tags"]
            else:
                return {}
        except ClientError as e:
            if error_code(e) in NOT_FOUND:
                return {}
            raise
        return {t["Key"]: t["Value"] for t in tags}

    def _s3vectors_tags(self, arn: str) -> dict:
        try:
            return self.client("s3vectors").list_tags_for_resource(resourceArn=arn).get("tags", {})
        except ClientError as e:
            if error_code(e) in NOT_FOUND:
                return {}
            raise

    def _s3vectors_inventory(self, tag_key: str, job_id: str, any_value: bool, seen: set[str]) -> list[Resource]:
        """Tagging API に出るか確かめられないため、S3 Vectors はバケットとインデックスのタグを直接見る。"""
        found: list[Resource] = []
        v = self.client("s3vectors")

        def add(arn: str) -> None:
            tags = self._s3vectors_tags(arn)
            if arn not in seen and tag_key in tags and (any_value or tags[tag_key] == job_id):
                seen.add(arn)
                found.append(Resource(arn, kind_of(arn), "s3vectors", note=_job_note(tags, tag_key, any_value).strip()))

        for page in v.get_paginator("list_vector_buckets").paginate():
            for b in page.get("vectorBuckets", []):
                add(b["vectorBucketArn"])
                for ipage in v.get_paginator("list_indexes").paginate(vectorBucketArn=b["vectorBucketArn"]):
                    for ix in ipage.get("indexes", []):
                        add(ix["indexArn"])
        return found

    # ------------------------------------------------------------ 棚卸し

    def inventory(self, tag_key: str, job_id: str, created_after: dt.datetime | None = None,
                  any_value: bool = False) -> Inventory:
        """タグ付きリソースを集める。any_value=True ならジョブを問わず handson-job-id タグの付いたもの全部。"""
        inv = Inventory()
        seen: set[str] = set()
        tag_filter = {"Key": tag_key} if any_value else {"Key": tag_key, "Values": [job_id]}

        for page in self.client("resourcegroupstaggingapi").get_paginator("get_resources").paginate(
                TagFilters=[tag_filter]):
            for m in page.get("ResourceTagMappingList", []):
                arn = m["ResourceARN"]
                seen.add(arn)
                r = Resource(arn, kind_of(arn), "tagging-api")
                r.note = _job_note({t["Key"]: t["Value"] for t in m.get("Tags", [])}, tag_key, any_value)
                inv.resources.append(r)

        for page in self.client("cloudformation").get_paginator("describe_stacks").paginate():
            for s in page.get("Stacks", []):
                tags = {t["Key"]: t["Value"] for t in s.get("Tags", [])}
                if tag_key not in tags or (not any_value and tags[tag_key] != job_id):
                    continue
                if s["StackId"] not in seen and s["StackStatus"] != "DELETE_COMPLETE":
                    inv.resources.append(Resource(s["StackId"], "cloudformation:stack", "cloudformation",
                                                  note=f"{s['StackStatus']}{_job_note(tags, tag_key, any_value)}"))

        iam = self.client("iam")
        for page in iam.get_paginator("list_roles").paginate():
            for role in page["Roles"]:
                if created_after and role["CreateDate"] < created_after:
                    continue
                tags = self._iam_tags("role", role["RoleName"], role["Arn"])
                if tag_key in tags and (any_value or tags[tag_key] == job_id):
                    inv.resources.append(Resource(role["Arn"], "iam:role", "iam",
                                                  note=_job_note(tags, tag_key, any_value).strip()))
        for page in iam.get_paginator("list_policies").paginate(Scope="Local"):
            for pol in page["Policies"]:
                if created_after and pol["CreateDate"] < created_after:
                    continue
                tags = self._iam_tags("policy", pol["PolicyName"], pol["Arn"])
                if tag_key in tags and (any_value or tags[tag_key] == job_id):
                    inv.resources.append(Resource(pol["Arn"], "iam:policy", "iam",
                                                  note=_job_note(tags, tag_key, any_value).strip()))

        inv.resources.extend(self._s3vectors_inventory(tag_key, job_id, any_value, seen))

        if not any_value:
            # タグが付かずに残りやすい、自動作成のロググループ(cleanup-checklist の共通の落とし穴)
            logs = self.client("logs")
            for page in logs.get_paginator("describe_log_groups").paginate(logGroupNamePattern=job_id):
                for g in page.get("logGroups", []):
                    arn = g["arn"].removesuffix(":*")
                    if arn not in seen:
                        inv.resources.append(Resource(arn, "logs:log-group", "name-match",
                                                      note="名前にジョブIDを含むロググループ(タグなし)"))

        for r in inv.resources:
            r.exists, r.created_at = self.describe(r.arn)
        return inv

    # ------------------------------------------------------------ 実在の確認と作成日時

    def describe(self, arn: str) -> tuple[bool | None, str | None]:
        """(実在するか, 作成日時) を返す。確かめる手段がない種類は (None, None)。"""
        fn = DESCRIBERS.get(kind_of(arn))
        if fn is None:
            return None, None
        try:
            created = fn(self, parse_arn(arn), arn)
            return True, _iso(created)
        except ClientError as e:
            if error_code(e) in NOT_FOUND:
                return False, None
            raise
        except LookupError:
            return False, None

    # ------------------------------------------------------------ 削除

    def delete(self, arn: str, tag_key: str, job_id: str, by_name: bool = False) -> str:
        """1件削除して結果の説明を返す。タグがなければ消さない(by_name は名前一致のロググループだけ)。"""
        kind = kind_of(arn)
        fn = DELETERS.get(kind)
        if fn is None:
            return f"skip: {kind} の自動削除には対応していない(要手動削除)"
        if by_name:
            if kind != "logs:log-group" or job_id not in arn:
                return "skip: タグがなく、名前一致で消せる種類でもない"
        elif not self.has_job_tag(arn, tag_key, job_id):
            return f"skip: {tag_key}={job_id} タグを確認できなかった"
        try:
            fn(self, parse_arn(arn), arn)
            return "deleted"
        except ClientError as e:
            if error_code(e) in NOT_FOUND:
                return "deleted (既に存在しない)"
            return f"error: {error_code(e)}: {e}"

    def delete_stack(self, stack: str, wait_seconds: int) -> str:
        cfn = self.client("cloudformation")
        cfn.delete_stack(StackName=stack)
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            try:
                status = cfn.describe_stacks(StackName=stack)["Stacks"][0]["StackStatus"]
            except ClientError as e:
                if "does not exist" in str(e):
                    return "deleted"
                raise
            if status == "DELETE_COMPLETE":
                return "deleted"
            if status == "DELETE_FAILED":
                return "error: DELETE_FAILED(原因のリソースを確認すること)"
            time.sleep(10)
        return "error: 削除の完了待ちがタイムアウトした"


def _job_note(tags: dict, tag_key: str, any_value: bool) -> str:
    return f" job={tags.get(tag_key)}" if any_value else ""


def _iso(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        # ミリ秒か秒の UNIX 時刻
        v = dt.datetime.fromtimestamp(v / 1000 if v > 1e11 else v, dt.timezone.utc)
    if isinstance(v, str):
        # Lambda の LastModified は "2026-10-10T06:00:00.000+0000" 形式
        v = dt.datetime.fromisoformat(re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", v.replace("Z", "+00:00")))
    if v.tzinfo is None:
        v = v.replace(tzinfo=dt.timezone.utc)
    return v.isoformat(timespec="seconds")


def _queue_url(aws: Aws, a: dict) -> str:
    return aws.client("sqs").get_queue_url(QueueName=a["resource"], QueueOwnerAWSAccountId=a["account"])["QueueUrl"]


def _iam_name(a: dict) -> str:
    return a["id"].split("/")[-1]


# ---------------------------------------------------------------- 種類ごとの実在確認(作成日時を返す)

def _d_sqs(aws, a, arn):
    url = _queue_url(aws, a)
    return int(aws.client("sqs").get_queue_attributes(QueueUrl=url, AttributeNames=["CreatedTimestamp"])
               ["Attributes"]["CreatedTimestamp"])


def _d_sns(aws, a, arn):
    aws.client("sns").get_topic_attributes(TopicArn=arn)
    return None


def _d_s3(aws, a, arn):
    aws.client("s3").head_bucket(Bucket=a["resource"])
    for b in aws.client("s3").list_buckets(Prefix=a["resource"]).get("Buckets", []):
        if b["Name"] == a["resource"]:
            return b["CreationDate"]
    return None


def _d_lambda(aws, a, arn):
    return aws.client("lambda").get_function(FunctionName=arn)["Configuration"]["LastModified"]


def _d_logs(aws, a, arn):
    name = a["resource"].removeprefix("log-group:").removesuffix(":*")
    for g in aws.client("logs").describe_log_groups(logGroupNamePrefix=name).get("logGroups", []):
        if g["logGroupName"] == name:
            return g["creationTime"]
    raise LookupError(name)


def _d_dynamodb(aws, a, arn):
    return aws.client("dynamodb").describe_table(TableName=a["id"])["Table"]["CreationDateTime"]


def _d_cfn(aws, a, arn):
    try:
        s = aws.client("cloudformation").describe_stacks(StackName=arn)["Stacks"][0]
    except ClientError as e:
        if "does not exist" in str(e):
            raise LookupError(arn) from e
        raise
    if s["StackStatus"] == "DELETE_COMPLETE":
        raise LookupError(arn)
    return s["CreationTime"]


def _d_iam_role(aws, a, arn):
    return aws.client("iam").get_role(RoleName=_iam_name(a))["Role"]["CreateDate"]


def _d_iam_policy(aws, a, arn):
    return aws.client("iam").get_policy(PolicyArn=arn)["Policy"]["CreateDate"]


def _d_ecr(aws, a, arn):
    return aws.client("ecr").describe_repositories(repositoryNames=[a["id"]])["repositories"][0]["createdAt"]


def _d_secret(aws, a, arn):
    d = aws.client("secretsmanager").describe_secret(SecretId=arn)
    if d.get("DeletedDate"):
        raise LookupError(arn)
    return d.get("CreatedDate")


def _d_ssm(aws, a, arn):
    name = "/" + a["id"] if not a["id"].startswith("/") else a["id"]
    p = aws.client("ssm").get_parameter(Name=name)["Parameter"]
    return p.get("LastModifiedDate")


def _d_states(aws, a, arn):
    return aws.client("stepfunctions").describe_state_machine(stateMachineArn=arn)["creationDate"]


def _d_events(aws, a, arn):
    aws.client("events").describe_rule(Name=a["id"].split("/")[-1])
    return None


def _d_ec2_instance(aws, a, arn):
    res = aws.client("ec2").describe_instances(InstanceIds=[a["id"]])["Reservations"]
    inst = res[0]["Instances"][0] if res else None
    if not inst or inst["State"]["Name"] == "terminated":
        raise LookupError(arn)
    return inst["LaunchTime"]


def _d_ec2_sg(aws, a, arn):
    aws.client("ec2").describe_security_groups(GroupIds=[a["id"]])
    return None


def _d_ec2_volume(aws, a, arn):
    return aws.client("ec2").describe_volumes(VolumeIds=[a["id"]])["Volumes"][0]["CreateTime"]


def _d_s3vectors_bucket(aws, a, arn):
    return aws.client("s3vectors").get_vector_bucket(vectorBucketArn=arn)["vectorBucket"].get("creationTime")


def _d_s3vectors_index(aws, a, arn):
    return aws.client("s3vectors").get_index(indexArn=arn)["index"].get("creationTime")


DESCRIBERS: dict[str, Callable] = {
    "sqs:queue": _d_sqs, "sns:topic": _d_sns, "s3:bucket": _d_s3, "lambda:function": _d_lambda,
    "logs:log-group": _d_logs, "dynamodb:table": _d_dynamodb, "cloudformation:stack": _d_cfn,
    "iam:role": _d_iam_role, "iam:policy": _d_iam_policy, "ecr:repository": _d_ecr,
    "secretsmanager:secret": _d_secret, "ssm:parameter": _d_ssm, "states:stateMachine": _d_states,
    "events:rule": _d_events, "ec2:instance": _d_ec2_instance, "ec2:security-group": _d_ec2_sg,
    "ec2:volume": _d_ec2_volume, "s3vectors:bucket": _d_s3vectors_bucket, "s3vectors:index": _d_s3vectors_index,
}


# ---------------------------------------------------------------- 種類ごとの削除

def _x_sqs(aws, a, arn):
    aws.client("sqs").delete_queue(QueueUrl=_queue_url(aws, a))


def _x_sns(aws, a, arn):
    aws.client("sns").delete_topic(TopicArn=arn)


def _x_s3(aws, a, arn):
    s3 = aws.client("s3")
    bucket = a["resource"]
    for page in s3.get_paginator("list_object_versions").paginate(Bucket=bucket):
        objs = [{"Key": o["Key"], "VersionId": o["VersionId"]}
                for o in page.get("Versions", []) + page.get("DeleteMarkers", [])]
        if objs:
            s3.delete_objects(Bucket=bucket, Delete={"Objects": objs, "Quiet": True})
    s3.delete_bucket(Bucket=bucket)


def _x_lambda(aws, a, arn):
    aws.client("lambda").delete_function(FunctionName=arn)


def _x_logs(aws, a, arn):
    aws.client("logs").delete_log_group(logGroupName=a["resource"].removeprefix("log-group:").removesuffix(":*"))


def _x_dynamodb(aws, a, arn):
    ddb = aws.client("dynamodb")
    ddb.update_table(TableName=a["id"], DeletionProtectionEnabled=False)
    ddb.delete_table(TableName=a["id"])


def _x_iam_role(aws, a, arn):
    iam = aws.client("iam")
    name = _iam_name(a)
    for p in iam.list_attached_role_policies(RoleName=name)["AttachedPolicies"]:
        iam.detach_role_policy(RoleName=name, PolicyArn=p["PolicyArn"])
    for p in iam.list_role_policies(RoleName=name)["PolicyNames"]:
        iam.delete_role_policy(RoleName=name, PolicyName=p)
    for ip in iam.list_instance_profiles_for_role(RoleName=name)["InstanceProfiles"]:
        iam.remove_role_from_instance_profile(InstanceProfileName=ip["InstanceProfileName"], RoleName=name)
    iam.delete_role(RoleName=name)


def _x_iam_policy(aws, a, arn):
    iam = aws.client("iam")
    for v in iam.list_policy_versions(PolicyArn=arn)["Versions"]:
        if not v["IsDefaultVersion"]:
            iam.delete_policy_version(PolicyArn=arn, VersionId=v["VersionId"])
    iam.delete_policy(PolicyArn=arn)


def _x_ecr(aws, a, arn):
    aws.client("ecr").delete_repository(repositoryName=a["id"], force=True)


def _x_secret(aws, a, arn):
    aws.client("secretsmanager").delete_secret(SecretId=arn, ForceDeleteWithoutRecovery=True)


def _x_ssm(aws, a, arn):
    name = "/" + a["id"] if not a["id"].startswith("/") else a["id"]
    aws.client("ssm").delete_parameter(Name=name)


def _x_states(aws, a, arn):
    aws.client("stepfunctions").delete_state_machine(stateMachineArn=arn)


def _x_events(aws, a, arn):
    ev = aws.client("events")
    name = a["id"].split("/")[-1]
    ids = [t["Id"] for t in ev.list_targets_by_rule(Rule=name).get("Targets", [])]
    if ids:
        ev.remove_targets(Rule=name, Ids=ids, Force=True)
    ev.delete_rule(Name=name, Force=True)


def _x_ec2_instance(aws, a, arn):
    aws.client("ec2").terminate_instances(InstanceIds=[a["id"]])


def _x_ec2_sg(aws, a, arn):
    aws.client("ec2").delete_security_group(GroupId=a["id"])


def _x_ec2_volume(aws, a, arn):
    aws.client("ec2").delete_volume(VolumeId=a["id"])


def _x_cfn(aws, a, arn):
    aws.client("cloudformation").delete_stack(StackName=arn)


def _x_s3vectors_index(aws, a, arn):
    # インデックスを消すと中のベクトルも消える
    aws.client("s3vectors").delete_index(indexArn=arn)


def _x_s3vectors_bucket(aws, a, arn):
    # 空でないバケットは消せないので、先に中のインデックスを消す
    v = aws.client("s3vectors")
    for page in v.get_paginator("list_indexes").paginate(vectorBucketArn=arn):
        for ix in page.get("indexes", []):
            v.delete_index(indexArn=ix["indexArn"])
    v.delete_vector_bucket(vectorBucketArn=arn)


DELETERS: dict[str, Callable] = {
    "sqs:queue": _x_sqs, "sns:topic": _x_sns, "s3:bucket": _x_s3, "lambda:function": _x_lambda,
    "logs:log-group": _x_logs, "dynamodb:table": _x_dynamodb, "iam:role": _x_iam_role,
    "iam:policy": _x_iam_policy, "ecr:repository": _x_ecr, "secretsmanager:secret": _x_secret,
    "ssm:parameter": _x_ssm, "states:stateMachine": _x_states, "events:rule": _x_events,
    "ec2:instance": _x_ec2_instance, "ec2:security-group": _x_ec2_sg, "ec2:volume": _x_ec2_volume,
    "cloudformation:stack": _x_cfn, "s3vectors:index": _x_s3vectors_index, "s3vectors:bucket": _x_s3vectors_bucket,
}

# 依存関係のため、先に消すほうから並べる(インスタンス → ボリューム・SG、ロール → ポリシー)
DELETE_ORDER = [
    "cloudformation:stack", "ec2:instance", "lambda:function", "states:stateMachine", "events:rule",
    "sns:topic", "sqs:queue", "dynamodb:table", "s3:bucket", "s3vectors:index", "s3vectors:bucket", "ecr:repository", "secretsmanager:secret",
    "ssm:parameter", "ec2:volume", "ec2:security-group", "iam:role", "iam:policy", "logs:log-group",
]


def delete_rank(kind: str) -> int:
    return DELETE_ORDER.index(kind) if kind in DELETE_ORDER else len(DELETE_ORDER)


STACK_ARN = re.compile(r"^arn:aws[\w-]*:cloudformation:[\w-]+:\d{12}:stack/([^/]+)/")


def stack_name(arn: str) -> str:
    m = STACK_ARN.match(arn)
    return m.group(1) if m else arn
