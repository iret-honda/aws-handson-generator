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
for role in $(aws iam list-roles --profile "$profile" --query 'Roles[].RoleName' --output text); do
  if aws iam list-role-tags --role-name "$role" --profile "$profile" \
      --query "Tags[?Key=='$tag_key' && Value=='$job_id'].Value" --output text | grep -q .; then
    echo "arn:aws:iam::role/$role"
  fi
done
