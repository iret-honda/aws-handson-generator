# 検証記録: sqs-intro-20261010-01 / ラウンド 4

| 項目 | 値 |
| --- | --- |
| 本文 | `handsons/sqs-intro-20261010-01/README.md`(Round 3 から変更なし。`/handson --verify-only` による再検証。ランナーの npx 書き換えを `npx --no -- cdk ...` に修正済み) |
| プロファイル | default |
| アカウントID | 123456789012 |
| リージョン | ap-northeast-1 |
| IaC | cdk |
| 検証方法 | 自動(handson-verifier / sandbox-runner) |
| 開始時刻 | 2026-10-10T20:30:02+00:00(概算。teardown 時点の経過時間 9.8分から逆算) |
| 終了時刻 | 2026-10-10T20:39:50+00:00(teardown の endedAt) |
| CloudTrail の追跡 | ユーザーエージェントに `handson-sqs-intro-20261010-01` を含む呼び出し |

要手動削除: なし

## 1. 静的チェック

| # | チェック | 方法 | 結果 | 判定 |
| --- | --- | --- | --- | --- |
| S1 | CLIコマンドの構文 | 全ブロックを読み、`run_step` の `bash -n` で確認 | 全ブロックで `syntax-error` なし | 合格 |
| S2 | IaCの合成・検証 | `(cd cdk && npm ci && npx tsc --noEmit && npx cdk synth -c jobId=${HANDSON_JOB_ID} > /dev/null)` | exitCode 0(`added 26 packages`、tsc・synth エラーなし)。コード: `Tags.of(app).add('handson-job-id', jobId)`、`DestroyAspect`、キューに `RemovalPolicy.DESTROY`、Lookup 不使用、ロググループを作るリソースなし | 合格 |
| S3 | 本文とコードのリソース名の一致 | 本文のコマンドと IaC の物理名・出力名 | キュー `handson-${jobId}-queue`、スタック `Handson-${jobId}`、出力 `QueueUrl` / `QueueName` 一致 | 合格 |
| S4 | 全リソースに `handson-job-id` タグ | IaC のタグ付与と CLI 作成コマンド | App 全体にタグ付与。CLI で作るリソースなし。手順4で実タグを確認 | 合格 |

## 2. 実行検証

本文のブロックを上から `run_step(block_id=...)` で実行した。コマンドの書き換えなし。`export` 行はランナーの固定値で置換。

| ブロック | 確認ポイント(期待結果) | 実際の結果 | 判定 | 備考 |
| --- | --- | --- | --- | --- |
| prep-1#1 | — | ランナーの固定値で置換 | 合格 | |
| prep-1#2 | アカウントID | `123456789012` | 合格 | |
| prep-2#1 | エラーなし | cwd `.../cdk` | 合格 | |
| prep-3#1 | `added <数> packages` | `added 26 packages` | 合格 | |
| prep-4#1 | `2.1145.0` から始まる | `2.1145.0 (build 13877dc)`(ランナー: `npx --no -- cdk --version`) | 合格 | Round 3 の不合格は解消 |
| prep-5#1 | `CREATE_COMPLETE` / `UPDATE_COMPLETE` | `UPDATE_COMPLETE` | 合格 | |
| step-1#1 | `✅  Handson-...` と Outputs | 一致。QueueName / QueueUrl に値あり(79.7秒) | 合格 | timeout 1200秒 |
| step-2#1/#2 | 所定形式の URL | `https://sqs.ap-northeast-1.amazonaws.com/123456789012/handson-sqs-intro-20261010-01-queue` | 合格 | |
| step-3#1 | `"30"` / `"true"` | 一致 | 合格 | |
| step-4#1 | `handson-job-id` タグ | 一致 | 合格 | |
| step-5#1 | メッセージID 3行 | 3行 | 合格 | |
| step-6#1 | `"3"` / `"0"` | 1回目で一致 | 合格 | |
| step-7#1 | 1〜3行、3列 | 1回目 order-3、2回目 order-1、3回目 order-2(各1行3列) | 合格 | 手順8の指示により計3回 |
| step-8#1 | `3` | 1回目 `1`、2回目 `2`、3回目 `3` | 合格 | 本文の指示による再実行2回 |
| step-9#1 | `"0"` / `"3"` | 1回目 `"0"`/`"0"`、5秒後 `"0"`/`"3"` | 合格 | 本文の指示による再実行1回 |
| step-10#1 | `deleted: order-1/2/3`、エラーなし | `order-3` / `order-1` / `order-2` | 合格 | |
| step-11#1 | `"0"` / `"0"` | 一致 | 合格 | |
| step-12#1/#2 | メッセージID形式 | `622b2111-...` | 合格 | |
| step-13#1 | MSG_ID と `1` | `622b2111-...\t1` | 合格 | |
| step-14#1 | 約5秒後に出力なし | 5.7秒、出力なし | 合格 | |
| step-15#1 | 手順13から30秒以内なら `"0"` / `"1"` | 1回目 `"0"`/`"0"`(反映遅れ)、5秒後 `"0"`/`"1"`(手順13から約15秒) | 合格 | トラブルシューティング表「手順6・9・11などで属性値が期待値にならない→5秒待って再実行」を適用。Round 3 と同じく手順15自体に再実行の指示がない(改善提案) |
| step-16#1 | 約30秒 | 30.1秒 | 合格 | |
| step-17#1 | MSG_ID と `2` | 一致 | 合格 | |
| step-18#1 | `[~] VisibilityTimeout` / `[-] 30` / `[+] 10` | 一致(stderr) | 合格 | |
| step-19#1 | `✅  Handson-...`、QueueUrl 同一 | 一致(79.4秒) | 合格 | |
| step-20#1 | 約60秒 | 60.0秒 | 合格 | |
| step-21#1 | `"10"` | 一致 | 合格 | |
| step-22#1 | MSG_ID と `3` | 一致 | 合格 | |
| step-23#1 | 約12秒 | 12.1秒 | 合格 | |
| step-24#1 | MSG_ID、`4`、受信ハンドル | `622b2111-...\t4\tAQEBq2pd...(省略)` | 合格 | |
| step-25#1/#2 | `AQEB` で始まる長い文字列 | `AQEBq2pd...(省略)` | 合格 | |
| step-26#1(発展) | 出力なし | 出力なし | 合格 | |
| step-27#1(発展) | `"1"` / `"0"` | 一致 | 合格 | |
| step-28#1(発展) | MSG_ID、`5`、受信ハンドル | `622b2111-...\t5\tAQEBsbgB...(省略)` | 合格 | |
| step-29#1/#2(発展) | 手順25と異なる文字列 | `AQEBsbgB...(省略)` | 合格 | |
| step-30#1 | 出力なし | 出力なし | 合格 | |
| step-31#1 | `"0"` / `"0"` | 1回目 `"1"`/`"0"`、5秒後 `"0"`/`"0"` | 合格 | 本文の指示による再実行1回 |

## 3. 後片付け検証

| # | チェック | 結果 | 判定 |
| --- | --- | --- | --- |
| C1 | 本文のクリーンアップ手順 | cleanup-1 ファイル削除・`ls` 出力なし / cleanup-2#1 `✅  Handson-sqs-intro-20261010-01: destroyed`(72.9秒) / cleanup-2#2 `Stack with id ... does not exist` / cleanup-3#1 `The specified queue does not exist.` / cleanup-4#1 出力なし / cleanup-4#2 3節とも空 | 合格 |
| C2 | タグ付きリソース0件 | `remainingCount: 0`、`pendingPropagation: []`(2026-10-10T20:39:28Z) | 合格 |
| C3 | タグなしの残骸 | name-match なし。DLQ なし。ロググループを作るリソースなし | 合格 |
| C4 | teardown 後の残り | 0。要手動削除なし | — |

## 判定

- 結果: **合格**
- 失敗した手順: なし
- 上限による停止: なし
- 改善提案(不合格理由ではない): 手順15の確認ポイントにも「5秒ほど待って再実行(手順13から30秒以内に)」を明記すると迷わない(Round 3・4 とも1回目は反映遅れ)
- 見積もり(このラウンド): $0.0102(時間課金リソースなし。見積もり額であり実績額ではない)
