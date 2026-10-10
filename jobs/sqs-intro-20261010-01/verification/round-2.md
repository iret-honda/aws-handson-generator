# 検証シート: sqs-intro-20261010-01 / ラウンド 2(変更箇所のみ)

| 項目 | 値 |
| --- | --- |
| 本文 | `handsons/sqs-intro-20261010-01/README.md`(Round 1 の指摘を修正済み) |
| プロファイル | default |
| アカウントID | 123456789012 |
| リージョン | ap-northeast-1 |
| IaC | cdk |
| 検証者 | (記入) |
| 開始時刻 | (記入) |
| 終了時刻 | (記入) |
| シェル | (記入。`echo $SHELL`。**zsh で実行すること**) |

## この回の範囲

検証者の指示で、Round 1 からの変更箇所だけを検証する。変更は次の2つ。それ以外の手順は Round 1 の結果を使う。

1. 後片付けの確認コマンド: `ls received-*.txt 2>/dev/null` → `ls received-basic.txt received-last.txt 2>/dev/null`(zsh で `no matches found` が出ないこと)
2. 手順31の確認ポイント: 削除直後に `NotVisible` が `"1"` のことがある旨と、再実行の指示を補った(本文どおり再実行して `"0"` になること)

手順31の状態(メッセージ1件を受信して削除した直後)を作るため、手順12・24・25・30・31 を実行する。メッセージの受信回数は Round 1 より少なくなるので、手順24の期待値は `1` に読み替える。

## 実行前の準備

```bash
export AWS_PROFILE=default
export AWS_REGION=ap-northeast-1
export HANDSON_JOB_ID=sqs-intro-20261010-01
export AWS_PAGER=""
```

Round 1 で destroy してから60秒以上経っているので、`QueueDeletedRecently` の心配はない。

## 1. 静的チェック

| # | チェック | 結果 | 判定 |
| --- | --- | --- | --- |
| S1 | 変更したコマンドの構文 | `ls received-basic.txt received-last.txt 2>/dev/null` はグロブを使わないため、zsh でも `no matches found` にならない。ファイルが無いときの `ls` のエラーは `2>/dev/null` で捨てられる。本文の他のコマンドにも、クォートの外のグロブは無い(オーケストレーターが確認) | 合格 |
| S2 | IaC | 変更なし(Round 1 で合格) | 合格 |
| S3 | リソース名の一致 | 変更なし(Round 1 で合格) | 合格 |

## 2. 実行検証

| 手順 | コマンド(本文から転記) | 確認ポイント(期待結果) | 実際の結果 | 判定 | 備考 |
| --- | --- | --- | --- | --- | --- |
| 準備2 | `cd handsons/sqs-intro-20261010-01/cdk` | — | | | |
| 1 | `npx cdk deploy -c jobId=${HANDSON_JOB_ID} --require-approval never` | `✅  Handson-sqs-intro-20261010-01` と `Outputs:` | ✅  Handson-sqs-intro-20261010-01　Handson-sqs-intro-20261010-01.QueueName = handson-sqs-intro-20261010-01-queue　Handson-sqs-intro-20261010-01.QueueUrl = https://sqs.ap-northeast-1.amazonaws.com/123456789012/handson-sqs-intro-20261010-01-queue　| | |
| 2 | ``QUEUE_URL=$(aws cloudformation describe-stacks --stack-name Handson-${HANDSON_JOB_ID} --query "Stacks[0].Outputs[?OutputKey=='QueueUrl'].OutputValue" --output text)`` → `echo ${QUEUE_URL}` | `https://sqs.ap-northeast-1.amazonaws.com/123456789012/handson-sqs-intro-20261010-01-queue` | | | |
| 12 | `MSG_ID=$(aws sqs send-message --queue-url "${QUEUE_URL}" --message-body "visibility-test" --query MessageId --output text)` → `echo ${MSG_ID}` | メッセージIDが表示される |<message-id-4> | <message-id-5>| | |
| 24 | ``aws sqs receive-message --queue-url "${QUEUE_URL}" --wait-time-seconds 5 --visibility-timeout 300 --message-system-attribute-names ApproximateReceiveCount --query 'not_null(Messages, `[]`)[].[MessageId,Attributes.ApproximateReceiveCount,ReceiptHandle]' --output text \| tee received-last.txt`` | `MSG_ID` と同じID、**`1`**、受信ハンドルの1行 | <message-id-5>    1       AQEBR1Kp...(省略)| | 受信回数は読み替え |
| 25 | `RECEIPT_HANDLE=$(cut -f3 received-last.txt)` → `echo ${RECEIPT_HANDLE}` | `AQEB` などで始まる長い文字列1行 | AQEBR1Kp...(省略)| | |
| 30 | `aws sqs delete-message --queue-url "${QUEUE_URL}" --receipt-handle "${RECEIPT_HANDLE}"` | 何も表示されない(エラーなし) |何も表示されない(エラーなし)	 | | | **手順25の直後に実行** |
| 31 | `aws sqs get-queue-attributes --queue-url "${QUEUE_URL}" --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible --query Attributes --output json` | どちらも `"0"`。`NotVisible` が `"1"` なら、本文どおり5秒待って再実行する | "ApproximateNumberOfMessages": "0"　"ApproximateNumberOfMessagesNotVisible": "0"　再実行1回| | 1回目の結果と再実行の回数・結果を両方書く |

## 3. 後片付け検証

| # | チェック | 方法 | 結果 | 判定 |
| --- | --- | --- | --- | --- |
| C1-1 | ローカルファイル削除 | `rm -f received-basic.txt received-last.txt` → `ls received-basic.txt received-last.txt 2>/dev/null` が **zsh で** 何も表示しない |何も表示しない | |
| C1-2 | スタック削除 | `npx cdk destroy -c jobId=${HANDSON_JOB_ID} --force`(**`--force` を付ける**)→ 確認プロンプトなしで `✅  Handson-sqs-intro-20261010-01: destroyed` | ✅  Handson-sqs-intro-20261010-01: destroyed　確認プロンプトなし| |
| C1-3 | スタックが無い | `aws cloudformation describe-stacks --stack-name Handson-${HANDSON_JOB_ID}` → `does not exist` |An error occurred (ValidationError) when calling the DescribeStacks operation: Stack with id Handson-sqs-intro-20261010-01 does not exist| |
| C1-4 | キューが無い | `aws sqs get-queue-url --queue-name handson-${HANDSON_JOB_ID}-queue` → `The specified queue does not exist` | An error occurred (AWS.SimpleQueueService.NonExistentQueue) when calling the GetQueueUrl operation: The specified queue does not exist.| |
| C2 | タグ付きリソースが0件 | `./scripts/list-tagged.sh sqs-intro-20261010-01 default ap-northeast-1`(オーケストレーターも実行する) | (検証者)## リージョン ap-northeast-1 のタグ付きリソース ## CloudFormation スタック(DELETE_COMPLETE 以外) ## IAM ロール(グローバル) (候補: 2026-10-10T05:11:52 UTC 以降に作成されたロール)。オーケストレーターも 2026-10-10 に実行し、3節とも0件 | 合格 |

## 判定(オーケストレーターが記入)

- 結果: **合格**(Round 1 の結果と合わせて、ハンズオン全体を合格とする)
- Round 1 の指摘への対応:
  - C1-1: 修正後の `ls received-basic.txt received-last.txt 2>/dev/null` は何も表示しなかった(合格)。シェル欄は空欄だが、Round 1 で zsh の `no matches found` が出たのと同じ環境(macOS / zsh)で実行したとみなす
  - 手順31: 本文どおり再実行し、1回の再実行で `"0"` / `"0"` になった(合格)。1回目の値は記録されていない
  - C1-2: `--force` を付けたところ、確認プロンプトは出なかった(合格)
- 記録上の注意:
  - 手順12: 「実際の結果」欄に Round 1 のID(`<message-id-4>`)が、「判定」欄に今回のID(`<message-id-5>`)が入っている。手順24で受信したIDと一致するのは `<message-id-5>` なので、こちらを今回の結果とみなす
  - 手順2の結果は空欄だが、後続の手順が `QUEUE_URL` を使って成功しているため、設定はされていたとみなす
  - 検証者・開始時刻・終了時刻・シェルは未記入
- 実行時間を反映した見積もり: $0.0102(時間課金リソースなし。Round 2 の SQS リクエストは10件未満。見積もり額であり実績額ではない)
- 修正ループ: 1回で合格 / 上限3回
