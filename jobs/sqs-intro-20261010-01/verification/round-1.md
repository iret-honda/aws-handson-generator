# 検証シート: sqs-intro-20261010-01 / ラウンド 1

| 項目 | 値 |
| --- | --- |
| 本文 | `handsons/sqs-intro-20261010-01/README.md` |
| プロファイル | default |
| アカウントID | 123456789012 |
| リージョン | ap-northeast-1 |
| IaC | cdk |
| 検証者 | 検証者A |
| 開始時刻 | 16:16 |
| 終了時刻 | (記入) |

## 実行前の準備

別ターミナルで次を実行してから始める。以降は **本文だけを見て** 実行し、本文に書かれていない操作をした場合は「備考」に必ず書く。

```bash
export AWS_PROFILE=default
export AWS_REGION=ap-northeast-1
export HANDSON_JOB_ID=sqs-intro-20261010-01
export AWS_PAGER=""
```

制限: 開始から 60 分を超えたら、途中でも後片付けに入る。見積もりが $1.00 に届きそうな場合も同様(本構成の見積もりは $0.0102/回で、時間課金なし)。

作業ディレクトリは `handsons/sqs-intro-20261010-01/cdk/`(本文の事前準備2で移動する)。

### 検証時に特に見てほしい点(執筆担当が推測で書いた箇所)

1. 受信コマンドの `--query 'not_null(Messages, `[]`)[]...'` が、空の受信で **何も出力しない** こと(手順14)
2. 手順18の `cdk diff` の表示形式と論理ID `Queue4A7E3555`
3. 後片付けで、キュー削除後の `get-queue-url` のエラー文言に `The specified queue does not exist` が含まれるか
4. 手順13などの `--message-system-attribute-names` が手元の AWS CLI v2 で使えるか(古い v2 には無いオプション。使えなければ `aws --version` を備考に)
5. 手順10の `while read` ループで、ループ内の `aws` が標準入力を読んでしまい、3件のうち1件しか削除されない、ということが起きないか
6. 修正ループで再検証する場合、destroy 後60秒以上空けてから deploy する(`QueueDeletedRecently` 回避)

## 1. 静的チェック

| # | チェック | 方法 | 結果 | 判定 |
| --- | --- | --- | --- | --- |
| S1 | CLIコマンドの構文 | 本文の全コマンドを目視(オーケストレーターが記入) | 全コマンドを目視。サブコマンド・オプション名に誤りは見当たらない。クォートは `--query` を単引用符、変数展開を二重引用符で囲んでおり bash/zsh で問題なし。`--message-system-attribute-names` は比較的新しい CLI v2 のオプションのため、実行時に確認(上記4)。後片付けの `../../../scripts/list-tagged.sh` は `cdk/` から見てリポジトリ直下を指しており正しい | 合格(実行で要確認1点) |
| S2 | IaCの合成・検証 | `cd handsons/sqs-intro-20261010-01/cdk && npm ci && npx cdk synth -c jobId=sqs-intro-20261010-01` | (検証者が記入。オーケストレーターは `cdk` の実行が禁止されているため未実施。執筆担当は手書きテンプレートで cfn-lint エラー0件を確認済み) | 合格 |
| S3 | 本文とコードのリソース名の一致 | オーケストレーターが記入 | キュー名 `handson-${jobId}-queue`(本文 手順1・2・後片付け / `lib/handson-stack.ts`)、スタック名 `Handson-${jobId}`(本文 手順2・後片付け / `bin/app.ts`)、出力 `QueueUrl` / `QueueName`(本文 手順1・2 / `lib/handson-stack.ts`)、context `jobId` / `visibilityTimeoutSeconds`(本文 手順1・18・19 / コード)がすべて一致。付録のコード抜粋も実コードと一致 | 合格 |
| S4 | 全リソースに `handson-job-id` タグ | IaCのタグ付与設定と、本文のCLI作成コマンドの `--tags` を確認 | `bin/app.ts` で `cdk.Tags.of(app).add('handson-job-id', jobId)`(スタックとキューに付く)。`DestroyAspect` + キューの `removalPolicy: DESTROY`。CLI で作るリソースはなし | 合格 |

## 2. 実行検証

コマンドは本文からの転記。長いものは本文からコピーして実行すること(表中の `\|` は本文では `|`)。

| 手順 | コマンド(本文から転記) | 確認ポイント(期待結果) | 実際の結果 | 判定 | 備考(CLI代替など) |
| --- | --- | --- | --- | --- | --- |
| 準備1 | `aws sts get-caller-identity --query Account --output text` | `123456789012` | 123456789012 | | |
| 準備2 | `cd cdk` → `npm ci` → `npx cdk --version` | `2.1145.0` で始まる | 2.1145.0 (build 13877dc)| | |
| 準備3 | `aws cloudformation describe-stacks --stack-name CDKToolkit --query 'Stacks[0].StackStatus' --output text` | `CREATE_COMPLETE` か `UPDATE_COMPLETE` | UPDATE_COMPLETE| | |
| 1 | `npx cdk deploy -c jobId=${HANDSON_JOB_ID} --require-approval never` | `✅  Handson-sqs-intro-20261010-01` と `Outputs:` に `QueueUrl` / `QueueName` | ✅  Handson-sqs-intro-20261010-01/Handson-sqs-intro-20261010-01.QueueName = handson-sqs-intro-20261010-01-queue/Handson-sqs-intro-20261010-01.QueueUrl = https://sqs.ap-northeast-1.amazonaws.com/123456789012/handson-sqs-intro-20261010-01-queue/✨  Deployment time: 67.56s| | 所要時間も記録 |
| 2 | ``QUEUE_URL=$(aws cloudformation describe-stacks --stack-name Handson-${HANDSON_JOB_ID} --query "Stacks[0].Outputs[?OutputKey=='QueueUrl'].OutputValue" --output text)`` → `echo ${QUEUE_URL}` | `https://sqs.ap-northeast-1.amazonaws.com/123456789012/handson-sqs-intro-20261010-01-queue` | https://sqs.ap-northeast-1.amazonaws.com/123456789012/handson-sqs-intro-20261010-01-queue| | |
| 3 | `aws sqs get-queue-attributes --queue-url "${QUEUE_URL}" --attribute-names VisibilityTimeout SqsManagedSseEnabled --query Attributes --output json` | `VisibilityTimeout` `"30"`、`SqsManagedSseEnabled` `"true"` |{"VisibilityTimeout":"30","SqsManagedSseEnabled": "true"} | | |
| 4 | `aws sqs list-queue-tags --queue-url "${QUEUE_URL}" --query Tags --output json` | `"handson-job-id": "sqs-intro-20261010-01"` を含む | "handson-job-id": "sqs-intro-20261010-01"| | 他のタグが付いていれば備考に |
| 5 | `for i in 1 2 3; do aws sqs send-message --queue-url "${QUEUE_URL}" --message-body "order-${i}" --query MessageId --output text; done` | メッセージIDが3行 |<message-id-1>/<message-id-2>/<message-id-3> | | |
| 6 | `aws sqs get-queue-attributes --queue-url "${QUEUE_URL}" --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible --query Attributes --output json` | `"3"` / `"0"`(小さければ5秒後に再実行) |     "ApproximateNumberOfMessages": "3","ApproximateNumberOfMessagesNotVisible": "0"| | |
| 7 | ``aws sqs receive-message --queue-url "${QUEUE_URL}" --max-number-of-messages 10 --wait-time-seconds 10 --visibility-timeout 300 --query 'not_null(Messages, `[]`)[].[MessageId,Body,ReceiptHandle]' --output text \| tee -a received-basic.txt`` | 1〜3行、各行「ID / 本文 / 受信ハンドル」の3列 | <message-id-3>    order-3 AQEBeDIV...(省略)　3回実行| | 再実行した回数を記録 |
| 8 | `wc -l < received-basic.txt` | `3`(未満なら手順7を再実行) |3 | | |
| 9 | `aws sqs get-queue-attributes --queue-url "${QUEUE_URL}" --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible --query Attributes --output json` | `"0"` / `"3"` |     "ApproximateNumberOfMessages": "0","ApproximateNumberOfMessagesNotVisible": "3"| | |
| 10 | ``while IFS=$'\t' read -r MESSAGE_ID BODY HANDLE; do aws sqs delete-message --queue-url "${QUEUE_URL}" --receipt-handle "${HANDLE}"; echo "deleted: ${BODY}"; done < received-basic.txt`` | `deleted: order-1/2/3` の3行、エラーなし | deleted: order-3 deleted: order-1 deleted: order-2| | 3行出るか要確認(上記5) |
| 11 | `aws sqs get-queue-attributes --queue-url "${QUEUE_URL}" --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible --query Attributes --output json` | `"0"` / `"0"` |     "ApproximateNumberOfMessages": "0", "ApproximateNumberOfMessagesNotVisible": "0"| | |
| 12 | `MSG_ID=$(aws sqs send-message --queue-url "${QUEUE_URL}" --message-body "visibility-test" --query MessageId --output text)` → `echo ${MSG_ID}` | メッセージIDが表示される |<message-id-4> | | **ここから手順15までは30秒以内** |
| 13 | ``aws sqs receive-message --queue-url "${QUEUE_URL}" --wait-time-seconds 5 --message-system-attribute-names ApproximateReceiveCount --query 'not_null(Messages, `[]`)[].[MessageId,Attributes.ApproximateReceiveCount]' --output text`` | `MSG_ID` と同じIDと `1` |<message-id-4>    1 | | 受信時刻を記録 |
| 14 | 手順13と同じコマンド | 約5秒後、何も表示されずに戻る | 約5秒後、何も表示されずに戻る	| | 上記1を確認。手順13からの経過秒 |
| 15 | `aws sqs get-queue-attributes --queue-url "${QUEUE_URL}" --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible --query Attributes --output json` | `"0"` / `"1"` |"ApproximateNumberOfMessages": "0","ApproximateNumberOfMessagesNotVisible": "1" | | |
| 16 | `sleep 30` | 約30秒後に戻る | 約30秒後に戻る| | |
| 17 | 手順13と同じコマンド | `MSG_ID` と同じIDと `2` |<message-id-4>    2 | | |
| 18 | `npx cdk diff -c jobId=${HANDSON_JOB_ID} -c visibilityTimeoutSeconds=10` | `[~] AWS::SQS::Queue` が1つ、`VisibilityTimeout` 30 → 10 | [~] VisibilityTimeout[-] 30[+] 10| | 上記2。実際の出力を貼る |
| 19 | `npx cdk deploy -c jobId=${HANDSON_JOB_ID} -c visibilityTimeoutSeconds=10 --require-approval never` | `✅  Handson-sqs-intro-20261010-01`、`QueueUrl` は手順1と同じ | ✅  Handson-sqs-intro-20261010-01 Handson-sqs-intro-20261010-01.QueueUrl = https://sqs.ap-northeast-1.amazonaws.com/123456789012/handson-sqs-intro-20261010-01-queue| | |
| 20 | `sleep 60` | 約60秒後に戻る | 約60秒後に戻る| | |
| 21 | `aws sqs get-queue-attributes --queue-url "${QUEUE_URL}" --attribute-names VisibilityTimeout --query Attributes --output json` | `"10"` | "VisibilityTimeout": "10"| | |
| 22 | 手順13と同じコマンド | `MSG_ID` と同じIDと `3` |<message-id-4>    3 | | |
| 23 | `sleep 12` | 約12秒後に戻る | 約12秒後に戻る| | |
| 24 | ``aws sqs receive-message --queue-url "${QUEUE_URL}" --wait-time-seconds 5 --visibility-timeout 300 --message-system-attribute-names ApproximateReceiveCount --query 'not_null(Messages, `[]`)[].[MessageId,Attributes.ApproximateReceiveCount,ReceiptHandle]' --output text \| tee received-last.txt`` | `MSG_ID` と同じID、`4`、受信ハンドルの1行 | <message-id-4>    4       AQEBPvmU...(省略)| | |
| 25 | `RECEIPT_HANDLE=$(cut -f3 received-last.txt)` → `echo ${RECEIPT_HANDLE}` | `AQEB` などで始まる長い文字列1行 | AQEBPvmU...(省略)| | |
| 26(発展) | `aws sqs change-message-visibility --queue-url "${QUEUE_URL}" --receipt-handle "${RECEIPT_HANDLE}" --visibility-timeout 0` | 何も表示されない(エラーなし) |何も表示されない(エラーなし) | | 発展手順も実施する |
| 27(発展) | `aws sqs get-queue-attributes --queue-url "${QUEUE_URL}" --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible --query Attributes --output json` | `"1"` / `"0"` |     "ApproximateNumberOfMessages": "1","ApproximateNumberOfMessagesNotVisible": "0"| | |
| 28(発展) | 手順24と同じコマンド | `MSG_ID` と同じID、`5`、受信ハンドルの1行 | <message-id-4>    5       AQEBT//T...(省略)| | |
| 29(発展) | `RECEIPT_HANDLE=$(cut -f3 received-last.txt)` → `echo ${RECEIPT_HANDLE}` | 手順25と異なる文字列 | AQEBT//T...(省略)| | |
| 30 | `aws sqs delete-message --queue-url "${QUEUE_URL}" --receipt-handle "${RECEIPT_HANDLE}"` | 何も表示されない(エラーなし) |何も表示されない(エラーなし)	 | | |
| 31 | `aws sqs get-queue-attributes --queue-url "${QUEUE_URL}" --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible --query Attributes --output json` | `"0"` / `"0"` |     "ApproximateNumberOfMessages": "0","ApproximateNumberOfMessagesNotVisible": "1"| | |

## 3. 後片付け検証

| # | チェック | 方法 | 結果 | 判定 |
| --- | --- | --- | --- | --- |
| C1-1 | ローカルファイル削除 | `rm -f received-basic.txt received-last.txt` → `ls received-*.txt 2>/dev/null` が何も表示しない | zsh: no matches found: received-*.txt| |
| C1-2 | スタック削除 | `npx cdk destroy -c jobId=${HANDSON_JOB_ID} --force` → `✅  Handson-sqs-intro-20261010-01: destroyed` | Are you sure you want to delete: Handson-sqs-intro-20261010-01 (y/n) y ✅  Handson-sqs-intro-20261010-01: destroyed| |
| C1-3 | スタックが無い | `aws cloudformation describe-stacks --stack-name Handson-${HANDSON_JOB_ID}` → `Stack with id Handson-sqs-intro-20261010-01 does not exist` |An error occurred (ValidationError) when calling the DescribeStacks operation: Stack with id Handson-sqs-intro-20261010-01 does not exist | |
| C1-4 | キューが無い | `aws sqs get-queue-url --queue-name handson-${HANDSON_JOB_ID}-queue` → `The specified queue does not exist` を含むエラー(上記3。実際の文言を貼る) | An error occurred (AWS.SimpleQueueService.NonExistentQueue) when calling the GetQueueUrl operation: The specified queue does not exist.| |
| C1-5 | タグ検索 | `aws resourcegroupstaggingapi get-resources --tag-filters "Key=handson-job-id,Values=${HANDSON_JOB_ID}" --query 'ResourceTagMappingList[].ResourceARN' --output text` → 何も表示されない |何も表示されない| |
| C2 | タグ付きリソースが0件 | `./scripts/list-tagged.sh sqs-intro-20261010-01 default ap-northeast-1`(本文では `cdk/` から `../../../scripts/list-tagged.sh`)。3節とも空 | オーケストレーターが 2026-10-10 に実行。リージョンのタグ付きリソース・CloudFormation スタック・IAM ロールの3節とも0件 | 合格 |
| C3 | タグを付けられないリソースの残骸なし | `cleanup-checklist` の SQS 項目: DLQ は作っていないため対象外。ロググループ・IAM ロールも作らない。CDKToolkit は対象外(削除しない) | 該当なし(オーケストレーター記入) | 合格 |

## 判定(オーケストレーターが記入)

- 結果: **不合格**(本文の不具合1件。リソースの作成・操作・削除はすべて期待どおりで、後片付け後のタグ付きリソースは0件)
- 失敗した手順: 後片付け C1-1(ローカルファイル削除の確認)
- エラー出力: `zsh: no matches found: received-*.txt`
- 直前の状態: `rm -f received-basic.txt received-last.txt` の実行後。ファイルは消えている。zsh(macOS の既定シェル)では、マッチしないグロブを zsh 自身がエラーにする。このエラーは `ls` の標準エラーではないため `2>/dev/null` で消えず、確認ポイントの「何も表示されない」と食い違う。bash なら何も出ない
- 本文の不具合ではないと判断したもの:
  - 手順31: `ApproximateNumberOfMessagesNotVisible` が `"1"` だった。検証者は本文にある「5秒待って再実行」をせずに後片付けへ進んでいる(検証者に確認済み)。手順30の削除はエラーなしで、値は概算で反映が遅れることがあるため、本文の不具合とはしない。次のラウンドで、本文どおり再実行したときに `"0"` になるかを確認する
  - C1-2: 確認プロンプト(y/n)が出たのは、検証者が `--force` を付けずに実行したため(検証者に確認済み)。削除自体は成功
- 執筆担当が推測で書いた6点の結果:
  1. 手順14: 空の受信で何も出力されないことを確認(OK)
  2. 手順18: `[~] VisibilityTimeout [-] 30 [+] 10` を確認。リソース行(`[~] AWS::SQS::Queue Queue4A7E3555`)は貼られておらず未確認
  3. C1-4: 文言 `The specified queue does not exist.` を確認(OK)
  4. `--message-system-attribute-names`: 手元の CLI で使えた(OK)
  5. 手順10: 3件とも削除された(OK)
  6. 再デプロイ: 該当なし(Round 1 では destroy 後の deploy をしていない)
- 記入漏れ(次のラウンドで記録): 終了時刻、手順14の手順13からの経過秒、手順7は3回実行
- 実行時間を反映した見積もり: $0.0102(時間課金リソースなし。SQS リクエストは約30件で、見積もりの500件以内。見積もり額であり実績額ではない)
- 修正ループ: 1回目 / 上限3回
