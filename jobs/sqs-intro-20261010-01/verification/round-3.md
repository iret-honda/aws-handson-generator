# 検証記録: sqs-intro-20261010-01 / ラウンド 3

| 項目 | 値 |
| --- | --- |
| 本文 | `handsons/sqs-intro-20261010-01/README.md`(Round 2 から変更なし。`/handson --verify-only` による再検証) |
| プロファイル | default |
| アカウントID | 123456789012 |
| リージョン | ap-northeast-1 |
| IaC | cdk |
| 検証方法 | 自動(handson-verifier / sandbox-runner) |
| 開始時刻 | 2026-10-10T20:16:08+00:00(概算。teardown 時点の経過時間 10.3分から逆算) |
| 終了時刻 | 2026-10-10T20:26:26+00:00(teardown の endedAt) |
| CloudTrail の追跡 | ユーザーエージェントに `handson-sqs-intro-20261010-01` を含む呼び出し |

要手動削除: なし

## 1. 静的チェック

| # | チェック | 方法 | 結果 | 判定 |
| --- | --- | --- | --- | --- |
| S1 | CLIコマンドの構文 | 全ブロックを読み、`run_step` の `bash -n` で確認 | 全40手順のブロックで `syntax-error` なし。クォート外のグロブなし | 合格 |
| S2 | IaCの合成・検証 | `(cd cdk && npm ci && npx tsc --noEmit && npx cdk synth -c jobId=${HANDSON_JOB_ID} > /dev/null)` | exitCode 0(`added 26 packages`、tsc・synth ともエラーなし。feature flags の案内のみ)。コード: `Tags.of(app).add('handson-job-id', jobId)`、`DestroyAspect` で全 CfnResource を DESTROY、キューにも `RemovalPolicy.DESTROY`、Lookup 不使用、ロググループを作るリソースなし | 合格 |
| S3 | 本文とコードのリソース名の一致 | 「構成」の表・コマンドと IaC の物理名・出力名 | キュー `handson-${HANDSON_JOB_ID}-queue` = `queueName: handson-${props.jobId}-queue`、スタック `Handson-${HANDSON_JOB_ID}` = `Handson-${jobId}`、出力 `QueueUrl` / `QueueName` 一致 | 合格 |
| S4 | 全リソースに `handson-job-id` タグ | IaC のタグ付与と CLI 作成コマンド | App 全体にタグ付与。CLI で作るリソースなし。手順4で実際にタグを確認 | 合格 |

## 2. 実行検証

本文のブロックを上から `run_step(block_id=...)` で実行した。本文のコマンドは書き換えていない。事前準備の `export AWS_PROFILE=...` などの行は、ランナーが固定値(上の表)で置き換えた。

| ブロック | コマンド(本文のまま) | 確認ポイント(期待結果) | 実際の結果 | 判定 | 備考 |
| --- | --- | --- | --- | --- | --- |
| prep-1#1 | `export AWS_PROFILE=...` ほか | — | ランナーの固定値で置換 | 合格 | |
| prep-1#2 | `aws sts get-caller-identity --query Account --output text` | アカウントIDが表示される | `123456789012` | 合格 | |
| prep-2#1 | `cd cdk` | エラーなし | cwd が `.../cdk` に | 合格 | |
| prep-3#1 | `npm ci` | `added <数> packages` | `added 26 packages, and audited 47 packages` | 合格 | |
| prep-4#1 | `npx cdk --version` | `2.1145.0` から始まるバージョン | **`10.9.7`**(ランナーは `npx --no cdk --version` として実行) | **不合格** | 下の「判定」参照。表示値は npm のバージョンと思われ、ランナーが挿入した `--no` の影響の可能性が高い |
| prep-5#1 | `aws cloudformation describe-stacks --stack-name CDKToolkit ...` | `CREATE_COMPLETE` または `UPDATE_COMPLETE` | `UPDATE_COMPLETE` | 合格 | |
| step-1#1 | `npx cdk deploy -c jobId=${HANDSON_JOB_ID} --require-approval never` | `✅  Handson-sqs-intro-20261010-01` と `Outputs:`(QueueUrl / QueueName) | `✅  Handson-sqs-intro-20261010-01`、QueueName = `handson-sqs-intro-20261010-01-queue`、QueueUrl = `https://sqs.ap-northeast-1.amazonaws.com/123456789012/handson-sqs-intro-20261010-01-queue`(80.5秒) | 合格 | timeout 1200秒 |
| step-2#1 | `QUEUE_URL=$(aws cloudformation describe-stacks ...)` | — | 出力なし、exit 0 | 合格 | |
| step-2#2 | `echo ${QUEUE_URL}` | `https://sqs.ap-northeast-1.amazonaws.com/` で始まり `/handson-sqs-intro-20261010-01-queue` で終わる | 期待どおりの URL | 合格 | |
| step-3#1 | `aws sqs get-queue-attributes ... VisibilityTimeout SqsManagedSseEnabled` | `"30"` / `"true"` | `"30"` / `"true"` | 合格 | |
| step-4#1 | `aws sqs list-queue-tags ...` | `"handson-job-id": "sqs-intro-20261010-01"` | 一致 | 合格 | |
| step-5#1 | `for i in 1 2 3; do aws sqs send-message ...; done` | メッセージIDが3行 | 3行(`80c93a7e-...`、`08e0c8dc-...`、`ec652eb3-...`) | 合格 | |
| step-6#1 | `aws sqs get-queue-attributes ... ApproximateNumberOfMessages ...` | `"3"` / `"0"`。3未満なら5秒待って再実行 | 1回目 `"0"`/`"0"`、2回目 `"0"`/`"0"`、3回目 `"3"`/`"0"` | 合格 | 本文の指示による再実行2回(各 `sleep 5`) |
| step-7#1 | `aws sqs receive-message ... \| tee -a received-basic.txt` | 1〜3行、3列 | 1回目 1行(order-2)、2回目 1行(order-3)、3回目 1行(order-1)。いずれも3列 | 合格 | 手順8の指示により計3回実行 |
| step-8#1 | `wc -l < received-basic.txt` | `3`。3未満なら手順7→手順8をやり直す | 1回目 `1`、2回目 `2`、3回目 `3` | 合格 | 本文の指示による再実行2回 |
| step-9#1 | `aws sqs get-queue-attributes ...` | `"0"` / `"3"` | `"0"` / `"3"` | 合格 | |
| step-10#1 | `while IFS=$'\t' read -r ...; do aws sqs delete-message ...; done < received-basic.txt` | `deleted: order-1/2/3` の3行、エラーなし | `deleted: order-2` / `order-3` / `order-1` | 合格 | |
| step-11#1 | `aws sqs get-queue-attributes ...` | `"0"` / `"0"` | `"0"` / `"0"` | 合格 | |
| step-12#1 | `MSG_ID=$(aws sqs send-message ... "visibility-test" ...)` | — | exit 0 | 合格 | |
| step-12#2 | `echo ${MSG_ID}` | メッセージID形式 | `<message-id-6>` | 合格 | |
| step-13#1 | `aws sqs receive-message --wait-time-seconds 5 ... ApproximateReceiveCount ...` | MSG_ID と受信回数 `1` | `5467a60e-...\t1` | 合格 | |
| step-14#1 | 同上 | 約5秒後、何も表示されない | 5.7秒、出力なし | 合格 | |
| step-15#1 | `aws sqs get-queue-attributes ...` | 手順13から30秒以内なら `"0"` / `"1"` | 1回目 **`"3"` / `"0"`**(古い概算値)、5秒後の2回目 `"0"` / `"1"` | 合格 | トラブルシューティング表「手順6・9・11などで属性値が期待値にならない → 5秒待って再実行」を適用。手順15の確認ポイント自体には再実行の指示がない(改善提案) |
| step-16#1 | `sleep 30` | 約30秒 | 30.1秒 | 合格 | |
| step-17#1 | `aws sqs receive-message ...` | MSG_ID と `2` | `5467a60e-...\t2` | 合格 | |
| step-18#1 | `npx cdk diff -c jobId=... -c visibilityTimeoutSeconds=10` | `[~] VisibilityTimeout`、`[-] 30`、`[+] 10` | 一致(stderr に出力) | 合格 | |
| step-19#1 | `npx cdk deploy ... -c visibilityTimeoutSeconds=10 --require-approval never` | `✅  Handson-sqs-intro-20261010-01`、QueueUrl が手順1と同じ | 一致。QueueUrl 同一 | 合格 | 80.4秒 |
| step-20#1 | `sleep 60` | 約60秒 | 60.1秒 | 合格 | |
| step-21#1 | `aws sqs get-queue-attributes ... VisibilityTimeout` | `"10"` | `"10"` | 合格 | |
| step-22#1 | `aws sqs receive-message ...` | MSG_ID と `3` | `5467a60e-...\t3` | 合格 | |
| step-23#1 | `sleep 12` | 約12秒 | 12.1秒 | 合格 | |
| step-24#1 | `aws sqs receive-message ... --visibility-timeout 300 ... \| tee received-last.txt` | MSG_ID、`4`、受信ハンドルの1行 | `5467a60e-...\t4\tAQEB+xbM...(省略)` | 合格 | |
| step-25#1 | `RECEIPT_HANDLE=$(cut -f3 received-last.txt)` | — | exit 0 | 合格 | |
| step-25#2 | `echo ${RECEIPT_HANDLE}` | `AQEB` などで始まる長い文字列1行 | `AQEB+xbM...(省略)` | 合格 | |
| step-26#1 | `aws sqs change-message-visibility ... --visibility-timeout 0`(発展) | 出力なし、エラーなし | 出力なし | 合格 | |
| step-27#1 | `aws sqs get-queue-attributes ...`(発展) | `"1"` / `"0"` | `"1"` / `"0"` | 合格 | |
| step-28#1 | `aws sqs receive-message ... \| tee received-last.txt`(発展) | MSG_ID、`5`、受信ハンドルの1行 | `5467a60e-...\t5\tAQEBKHoJ...(省略)` | 合格 | |
| step-29#1 | `RECEIPT_HANDLE=$(cut -f3 received-last.txt)`(発展) | — | exit 0 | 合格 | |
| step-29#2 | `echo ${RECEIPT_HANDLE}`(発展) | 手順25と異なる長い文字列 | `AQEBKHoJ...(省略)`(手順25と異なる) | 合格 | |
| step-30#1 | `aws sqs delete-message ... --receipt-handle "${RECEIPT_HANDLE}"` | 出力なし、エラーなし | 出力なし | 合格 | |
| step-31#1 | `aws sqs get-queue-attributes ...` | `"0"` / `"0"` | 1回目で `"0"` / `"0"` | 合格 | 再実行不要 |

## 3. 後片付け検証

| # | チェック | 方法 | 結果 | 判定 |
| --- | --- | --- | --- | --- |
| C1 | 本文のクリーンアップ手順を実行 | 後片付けのブロックを上から `run_step` | cleanup-1#1 `rm -f` 成功 / cleanup-1#2 `ls ... 2>/dev/null` 出力なし(exit 1、ファイルなし) / cleanup-2#1 `✅  Handson-sqs-intro-20261010-01: destroyed`(72.9秒、確認プロンプトなし) / cleanup-2#2 `Stack with id Handson-sqs-intro-20261010-01 does not exist` / cleanup-3#1 `The specified queue does not exist.` / cleanup-4#1 出力なし / cleanup-4#2 `list-tagged.sh` の3節とも空 | 合格 |
| C2 | タグ付きリソースが0件 | `list_tagged_resources` の `remainingCount` | `remainingCount: 0`、`pendingPropagation: []`(2026-10-10T20:26:05Z) | 合格 |
| C3 | タグを付けられないリソースの残骸なし | `name-match` と `cleanup-checklist`(SQS: DLQ の消し忘れ) | name-match なし。DLQ は作っていない。ロググループを作るリソースなし | 合格 |
| C4 | teardown 後の残り | `teardown` の `remainingCount` | 0(cdk destroy はスタックなしで即終了)。要手動削除なし | — |

## 判定

- 結果: **不合格**(prep-4#1 の確認ポイント不一致のみ。他の手順・静的チェック・後片付け検証はすべて合格)
- 失敗した手順: prep-4#1(事前準備の手順4「CDK のバージョンを確認する」)
- エラー出力: エラーではなく出力の不一致。`npx cdk --version` の stdout が `10.9.7`(確認ポイントは `2.1145.0` から始まる)。ランナーの stderr: `sandbox-runner: 実行: npx --no cdk --version`
- 直前の状態: `cdk/` に移動し `npm ci` 済み(`added 26 packages`)。同じ環境で直後の `npx cdk deploy` / `diff` / `destroy` は正常に動いており、CDK CLI 自体はインストールされている
- 原因の見立て(要確認): `10.9.7` は npm のバージョンと思われる。ランナーが `npx cdk` を `npx --no cdk` に書き換えた結果、`--version` が cdk ではなく npm/npx 側の引数として解釈された可能性が高い。Round 1(手動)ではこの手順は合格している。本文の誤りではなくランナーの書き換えの問題であれば、執筆担当ではなく `mcp/sandbox-runner` の修正(または `--version` を含む npx 呼び出しの扱いの見直し)が必要。検証担当は本文外の操作で原因を確かめていない
- 改善提案(不合格理由ではない): 手順15の確認ポイントに再実行の指示がない。今回1回目に古い概算値 `"3"`/`"0"` が返り、トラブルシューティング表の「手順6・9・11など」を適用して再実行した。手順15にも「5秒ほど待ってから再実行(手順13から30秒以内に)」を明記すると迷わない
- 上限による停止: なし
- 見積もり(このラウンド): $0.0102(時間課金リソースなし。見積もり額であり実績額ではない)
