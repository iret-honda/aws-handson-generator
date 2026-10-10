#!/usr/bin/env bash
# handson-job-id タグが付いたリソースを一覧する(読み取りのみ)。後片付け検証では0件で合格。
# Resource Groups Tagging API が扱えないリソース(IAMロールなど)は個別に確認する。
# 使い方: ./scripts/list-tagged.sh <job-id> <profile> <region>
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 <job-id> <profile> <region>" >&2
  exit 1
fi

job_id=$1 profile=$2 region=$3
tag_key=handson-job-id

echo "## リージョン $region のタグ付きリソース"
aws resourcegroupstaggingapi get-resources \
  --tag-filters "Key=$tag_key,Values=$job_id" \
  --profile "$profile" --region "$region" \
  --query 'ResourceTagMappingList[].ResourceARN' --output text | tr '\t' '\n' | sed '/^$/d'

echo "## CloudFormation スタック(DELETE_COMPLETE 以外)"
aws cloudformation describe-stacks --profile "$profile" --region "$region" \
  --query "Stacks[?Tags[?Key=='$tag_key' && Value=='$job_id']].[StackName,StackStatus]" \
  --output text

echo "## IAM ロール(グローバル)"
# list-role-tags をロールごとに順番に呼ぶと遅いので、次の2つで速くする。
# 1. ジョブ開始(input.json の createdAt)の1時間前より後に作られたロールだけを候補にする。
#    ジョブのタグが付くロールはジョブ開始後に作られるため。input.json がなければジョブIDの日付
#    (<slug>-<level>-YYYYMMDD-NN)の前日 00:00 UTC 以降、日付も読めなければ全ロールが候補。
# 2. 候補のタグ確認を並列で実行する(IAM API のスロットリングは CLI の既定リトライに任せる)。
#    全ロールを確認すると aws コマンドの起動が CPU を使い切るため、並列でも数分かかる。
input_json="$(dirname "$0")/../jobs/$job_id/input.json"
cutoff=""
if [[ -f "$input_json" ]]; then
  cutoff=$(python3 -c '
import json, sys
from datetime import datetime, timedelta, timezone
t = datetime.fromisoformat(json.load(open(sys.argv[1]))["createdAt"])
print((t - timedelta(hours=1)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"))
' "$input_json")
  echo "(候補: $cutoff UTC 以降に作成されたロール)" >&2
elif [[ $job_id =~ -([0-9]{8})-[0-9]+$ ]]; then
  cutoff=$(python3 -c '
import sys
from datetime import datetime, timedelta
print((datetime.strptime(sys.argv[1], "%Y%m%d") - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00"))
' "${BASH_REMATCH[1]}")
  echo "(候補: $cutoff UTC 以降に作成されたロール。$input_json がないためジョブIDの日付から決めた)" >&2
else
  echo "(候補: 全ロール。$input_json がなく、ジョブIDから日付も読めないため)" >&2
fi

# 出力は「ロール名<TAB>ARN<TAB>作成日時(UTC の ISO 8601)」。作成日時は文字列のまま比べる
aws iam list-roles --profile "$profile" \
  --query 'Roles[].[RoleName,Arn,CreateDate]' --output text \
  | awk -F'\t' -v cutoff="$cutoff" 'cutoff == "" || substr($3, 1, 19) >= cutoff { print $1 "\t" $2 }' \
  | xargs -P 8 -L 1 bash -c '
      if aws iam list-role-tags --role-name "$3" --profile "$1" --query "$2" --output text | grep -q .; then
        echo "$4"
      fi' _ "$profile" "Tags[?Key=='$tag_key' && Value=='$job_id'].Value"
