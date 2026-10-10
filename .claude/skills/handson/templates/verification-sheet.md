# 検証シート: {{jobId}} / ラウンド {{n}}

| 項目 | 値 |
| --- | --- |
| 本文 | `handsons/{{jobId}}/README.md` |
| プロファイル | {{profile}} |
| アカウントID | {{accountId}} |
| リージョン | {{region}} |
| IaC | {{iac}} |
| 検証者 | (記入) |
| 開始時刻 | (記入) |
| 終了時刻 | (記入) |

## 実行前の準備

別ターミナルで次を実行してから始める。以降は **本文だけを見て** 実行し、本文に書かれていない操作をした場合は「備考」に必ず書く。

```bash
export AWS_PROFILE={{profile}}
export AWS_REGION={{region}}
export HANDSON_JOB_ID={{jobId}}
export AWS_PAGER=""
```

IaC が Terraform の場合は、AWS プロバイダー(約170MB)の再ダウンロードを避けるため、プラグインキャッシュも設定する。検証環境の都合による設定で結果には影響しないため、「本文にない操作」として備考に書かなくてよい。

```bash
export TF_PLUGIN_CACHE_DIR="$HOME/.terraform.d/plugin-cache"
mkdir -p "$TF_PLUGIN_CACHE_DIR"
```

制限: 開始から {{maxRuntimeMinutes}} 分を超えたら、途中でも後片付けに入る。見積もりが ${{awsCostUsd}} に届きそうな場合も同様。

## 1. 静的チェック

| # | チェック | 方法 | 結果 | 判定 |
| --- | --- | --- | --- | --- |
| S1 | CLIコマンドの構文 | 本文の全コマンドを目視(オーケストレーターが記入) | | |
| S2 | IaCの合成・検証 | CDK: `cd handsons/{{jobId}}/cdk && npm ci && npx cdk synth -c jobId={{jobId}}` / Terraform: `cd handsons/{{jobId}}/terraform && terraform init -backend-config="path=$(git rev-parse --show-toplevel)/jobs/{{jobId}}/terraform.tfstate" && terraform validate` | | |
| S3 | 本文とコードのリソース名の一致 | オーケストレーターが記入 | | |
| S4 | 全リソースに `handson-job-id` タグ | IaCのタグ付与設定と、本文のCLI作成コマンドの `--tags` を確認 | | |

## 2. 実行検証

| 手順 | コマンド(本文から転記) | 確認ポイント(期待結果) | 実際の結果 | 判定 | 備考(CLI代替など) |
| --- | --- | --- | --- | --- | --- |
{{steps}}

## 3. 後片付け検証

| # | チェック | 方法 | 結果 | 判定 |
| --- | --- | --- | --- | --- |
| C1 | 本文のクリーンアップ手順を実行 | 本文どおり | | |
| C2 | タグ付きリソースが0件 | `./scripts/list-tagged.sh {{jobId}} {{profile}} {{region}}` | | |
| C3 | タグを付けられないリソースの残骸なし | `cleanup-checklist` の該当サービス項目 | | |

## 判定(オーケストレーターが記入)

- 結果: 合格 / 不合格
- 失敗した手順:
- エラー出力:
- 直前の状態:
- 実行時間を反映した見積もり: $
