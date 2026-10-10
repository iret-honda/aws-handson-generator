---
name: iac-terraform
description: ハンズオン用 Terraform コードの規約。バージョンとプロバイダーの固定、default_tags での handson-job-id タグ付与、state のローカル保存。IaC種別がTerraformのハンズオンでIaCを書くときに使う。
---

# Terraform の規約

## バージョン

| 対象 | バージョン |
| --- | --- |
| Terraform | 1.9.0 以上(`versions.tf` の `required_version`) |
| hashicorp/aws プロバイダー | 6.68.0 に固定(`versions.tf`) |

プロバイダーは範囲指定(`~>`)にせず固定する。初回の `terraform init` で生成される `.terraform.lock.hcl` もコミットする。

## ディレクトリ構成

`templates/` を `handsons/<job-id>/terraform/` にそのままコピーして始める。

```
terraform/
├── versions.tf    # Terraform とプロバイダーの固定、local backend(変更しない)
├── providers.tf   # default_tags で handson-job-id を付与(変更しない)
├── variables.tf   # job_id と region
├── main.tf        # ハンズオンのリソース定義(ここを書く)
└── outputs.tf     # 後続手順で使う値
```

ファイルが大きくなる場合は `main.tf` を役割ごと(`sqs.tf`、`iam.tf` など)に分けてよい。

## 必須ルール

1. **タグは `default_tags`**: `providers.tf` で全リソースに `handson-job-id = var.job_id` を付ける。`default_tags` が効かないもの(`aws_autoscaling_group` の伝播タグ、起動テンプレートから作られるインスタンスやボリュームなど)は、個別に `tags` / `tag_specifications` を書く。
2. **state はローカル**: リモート backend を使わない。読者は `terraform init` のままで `terraform/terraform.tfstate` に保存される。検証時は次のようにジョブディレクトリに保存する。
   ```bash
   terraform init -backend-config="path=$(git rev-parse --show-toplevel)/jobs/<job-id>/terraform.tfstate"
   ```
3. **destroy で消し切れるように書く**:
   - S3: `force_destroy = true`
   - ECR: `force_delete = true`
   - RDS: `skip_final_snapshot = true`、`deletion_protection = false`
   - Secrets Manager: `recovery_window_in_days = 0`
   - `lifecycle { prevent_destroy = true }` は使わない
4. **ロググループは明示的に作る**: Lambda などが自動作成するロググループはタグが付かず、`terraform destroy` 後に残る。`aws_cloudwatch_log_group` を `/aws/lambda/<関数名>` で先に定義し、`retention_in_days = 1` を付け、関数から `depends_on` で参照する。
5. **命名**: `local.name_prefix`(`handson-${var.job_id}`)に役割を付ける。本文のリソース名と一致させる。
6. **ハードコードしない**: アカウントIDは `data "aws_caller_identity"`、リージョンは `var.region` を使う。
7. **認証情報は書かない**: provider に `profile` やキーを書かない。`AWS_PROFILE` 環境変数で切り替える。
8. **モジュールは使わない**: 読者がコードを読んで理解できるよう、レジストリのモジュールではなくリソースを直接書く。

## 静的チェック

検証の静的チェックでは、人が次を実行する。AWS プロバイダーは約170MBあり、ジョブごとにダウンロードし直さないよう、プラグインキャッシュを使う。

```bash
export TF_PLUGIN_CACHE_DIR="$HOME/.terraform.d/plugin-cache"
mkdir -p "$TF_PLUGIN_CACHE_DIR"
terraform init -backend-config="path=$(git rev-parse --show-toplevel)/jobs/<job-id>/terraform.tfstate"
terraform fmt -check
terraform validate
terraform plan -var "job_id=<job-id>"
```

キャッシュは `.terraform.lock.hcl` のハッシュと一致したときだけ使われる。テンプレートの lockfile と異なるプラットフォームで初めて実行した場合はダウンロードが発生し、lockfile にそのプラットフォームのハッシュが追記される。追記された lockfile はコミットしてよい。

読者向けの本文にはキャッシュの設定を書かない(手順を増やさないため)。

## 調べるとき

リソースの引数やベストプラクティスは `aws-terraform` MCP で、プロバイダー 6.68.0 のドキュメントを確認する。
