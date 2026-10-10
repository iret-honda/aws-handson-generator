#!/usr/bin/env bash
# 使用するプロファイルのアカウントIDを確認する(読み取りのみ)。構成案の冒頭に記載するために使う。
# 使い方: ./scripts/aws-identity.sh <profile> <region>
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <profile> <region>" >&2
  exit 1
fi

aws sts get-caller-identity --profile "$1" --region "$2" --output json
