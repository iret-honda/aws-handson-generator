# 検証記録: {{jobId}} / ラウンド {{n}}

| 項目 | 値 |
| --- | --- |
| 本文 | `handsons/{{jobId}}/README.md` |
| プロファイル | {{profile}} |
| アカウントID | {{accountId}} |
| リージョン | {{region}} |
| IaC | {{iac}} |
| 検証方法 | 自動(handson-verifier / sandbox-runner) |
| 開始時刻 | {{最初の run_step の時刻}} |
| 終了時刻 | {{teardown の endedAt}} |
| CloudTrail の追跡 | ユーザーエージェントに `handson-{{jobId}}` を含む呼び出し |

{{要手動削除のリソースがあれば、ここに **要手動削除** として ARN を列挙する}}

## 1. 静的チェック

| # | チェック | 方法 | 結果 | 判定 |
| --- | --- | --- | --- | --- |
| S1 | CLIコマンドの構文 | 全ブロックを読み、`run_step` の `bash -n` で確認 | | |
| S2 | IaCの合成・検証 | CDK: `(cd cdk && npm ci && npx tsc --noEmit && npx cdk synth -c jobId=${HANDSON_JOB_ID} > /dev/null)` / Terraform: `(cd terraform && terraform init && terraform fmt -check && terraform validate)` | | |
| S3 | 本文とコードのリソース名の一致 | 本文の「構成」の表・コマンドと、IaC の物理名・出力名を突き合わせる | | |
| S4 | 全リソースに `handson-job-id` タグ | IaCのタグ付与設定と、本文のCLI作成コマンドの `--tags` | | |

## 2. 実行検証

本文のブロックを上から `run_step(block_id=...)` で実行した。本文のコマンドは書き換えていない。事前準備の `export AWS_PROFILE=...` などの行は、ランナーが固定値(上の表)で置き換えた。

| ブロック | コマンド(本文のまま) | 確認ポイント(期待結果) | 実際の結果 | 判定 | 備考(CLI代替、本文の指示による再実行など) |
| --- | --- | --- | --- | --- | --- |
{{steps}}

## 3. 後片付け検証

| # | チェック | 方法 | 結果 | 判定 |
| --- | --- | --- | --- | --- |
| C1 | 本文のクリーンアップ手順を実行 | 後片付けのブロックを上から `run_step` | | |
| C2 | タグ付きリソースが0件 | `list_tagged_resources` の `remainingCount`(`pendingPropagation` は数えない) | | |
| C3 | タグを付けられないリソースの残骸なし | `list_tagged_resources` の `name-match` と、`cleanup-checklist` の該当サービス項目 | | |
| C4 | teardown 後の残り | `teardown` の `remainingCount`(判定には使わず、要手動削除の有無を記録する) | | — |

## 判定

- 結果: 合格 / 不合格
- 失敗した手順:
- エラー出力:
- 直前の状態:
- 上限による停止: なし / あり(理由)
- 見積もり(このラウンド): $
