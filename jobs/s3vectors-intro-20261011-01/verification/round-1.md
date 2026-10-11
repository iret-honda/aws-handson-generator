# 検証記録: s3vectors-intro-20261011-01 / ラウンド 1

| 項目 | 値 |
| --- | --- |
| 本文 | `handsons/s3vectors-intro-20261011-01/README.md` |
| プロファイル | default |
| アカウントID | 123456789012 |
| リージョン | ap-northeast-1 |
| IaC | cdk |
| 検証方法 | 自動(handson-verifier / sandbox-runner) |
| 開始時刻 | 2026-10-11T15:02:50+00:00(概算。teardown の endedAt とラウンド経過時間 3.3 分から逆算) |
| 終了時刻 | 2026-10-11T15:06:10+00:00 |
| CloudTrail の追跡 | ユーザーエージェントに `handson-s3vectors-intro-20261011-01` を含む呼び出し |

要手動削除のリソース: なし

## 1. 静的チェック

| # | チェック | 方法 | 結果 | 判定 |
| --- | --- | --- | --- | --- |
| S1 | CLIコマンドの構文 | 全ブロックを読み、`run_step` の `bash -n` で確認 | 全41ブロックで `syntax-error` なし | 合格 |
| S2 | IaCの合成・検証 | `(cd cdk && npm ci && npx tsc --noEmit && npx cdk synth -c jobId=${HANDSON_JOB_ID} > /dev/null)` | exitCode 0(added 26 packages、tsc エラーなし、synth 成功)。コード確認: `cdk.Tags.of(app).add('handson-job-id', jobId)`、`DestroyAspect` で全 CfnResource に `RemovalPolicy.DESTROY`、各リソースにも `applyRemovalPolicy(DESTROY)`、Lookup 不使用、Lambda 等がないためロググループの明示作成は不要 | 合格 |
| S3 | 本文とコードのリソース名の一致 | 構成の表・コマンドと IaC の物理名・出力名を突き合わせ | バケット `handson-${jobId}-vectors`、インデックス `handson-${jobId}-docs`、スタック `Handson-${jobId}`、出力 `VectorBucketName` / `VectorBucketArn` / `IndexName` / `IndexArn` が一致。次元 256・cosine・float32・`nonFilterableMetadataKeys: ['source_text']` も本文と一致 | 合格 |
| S4 | 全リソースに `handson-job-id` タグ | IaC のタグ付与と本文の CLI 作成コマンド | App 全体にタグ付与。CLI で作る AWS リソースはなし(put-vectors はインデックス内のデータ)。実行時に step-6 / step-8 でバケット・インデックス双方のタグを確認済み | 合格 |

## 2. 実行検証

本文のブロックを上から `run_step(block_id=...)` で実行した。本文のコマンドは書き換えていない。事前準備の `export AWS_PROFILE=...` などの行は、ランナーが固定値(上の表)で置き換えた(`EMBED_DIM=256` の export は本文どおり実行)。

| ブロック | コマンド(本文のまま) | 確認ポイント(期待結果) | 実際の結果 | 判定 | 備考 |
| --- | --- | --- | --- | --- | --- |
| prep-1#1 | `export ... EMBED_DIM=256` | — | exit 0 | 合格 | AWS_PROFILE / AWS_REGION / HANDSON_JOB_ID / AWS_PAGER はランナー固定値 |
| prep-1#2 | `aws sts get-caller-identity --query Account --output text` | アカウントIDが表示される | `123456789012` | 合格 | |
| prep-2#1 | `aws --version` | `aws-cli/2.` で始まる | `aws-cli/2.33.6 Python/3.13.11 ...` | 合格 | 本文の例(2.37.12)より古いが s3vectors は使えた |
| prep-3#1 | `aws s3vectors list-vector-buckets --prefix ... --query 'length(vectorBuckets)'` | `0` | `0` | 合格 | |
| prep-4#1 | `jq --version` | jq-1.6 以上 | `jq-1.7.1-apple` | 合格 | |
| prep-5#1 | `aws bedrock get-foundation-model ... titan-embed-text-v2:0 ...` | `ACTIVE` | `ACTIVE` | 合格 | |
| prep-6#1 | `aws bedrock get-foundation-model ... nova-lite-v1:0 ...` | `ACTIVE` | `ACTIVE` | 合格 | |
| prep-7#1 | `cd cdk` | — | cwd が `.../cdk` | 合格 | |
| prep-7#2 | `wc -l < ../data/docs.jsonl` | `8` | `       8` | 合格 | |
| prep-8#1 | `npm ci` | `added <数> packages`、npm error なし | `added 26 packages ... found 0 vulnerabilities` | 合格 | |
| prep-9#1 | `npx cdk --version` | `2.1145.0` で始まる | `2.1145.0 (build 13877dc)` | 合格 | |
| prep-10#1 | `aws cloudformation describe-stacks --stack-name CDKToolkit ...` | CREATE_COMPLETE / UPDATE_COMPLETE | `UPDATE_COMPLETE` | 合格 | |
| prep-11#1 | `mkdir -p work` | — | exit 0 | 合格 | |
| prep-11#2 | `test -d work && echo ok` | `ok` | `ok` | 合格 | |
| step-1#1 | `npx cdk deploy -c jobId=${HANDSON_JOB_ID} --require-approval never` | `✅  Handson-...` と Outputs 4つ | `✅  Handson-s3vectors-intro-20261011-01`、Outputs に IndexArn / IndexName / VectorBucketArn / VectorBucketName の4つ | 合格 | デプロイ 11.2s(本文の「1〜3分」より短い) |
| step-2#1 | `VECTOR_BUCKET=$(aws cloudformation describe-stacks ...)` | — | exit 0 | 合格 | |
| step-2#2 | `echo ${VECTOR_BUCKET}` | `handson-s3vectors-intro-20261011-01-vectors` | 同左 | 合格 | |
| step-3#1 | `INDEX_NAME=$(...)` | — | exit 0 | 合格 | |
| step-3#2 | `echo ${INDEX_NAME}` | `handson-s3vectors-intro-20261011-01-docs` | 同左 | 合格 | |
| step-4#1 | `aws s3vectors get-index ...` | float32 / 256 / cosine / ["source_text"] | 完全一致 | 合格 | |
| step-5#1 | `VECTOR_BUCKET_ARN=$(...)` | — | exit 0 | 合格 | |
| step-5#2 | `echo ${VECTOR_BUCKET_ARN}` | `arn:aws:s3vectors:ap-northeast-1:...:bucket/handson-...-vectors` | `arn:aws:s3vectors:ap-northeast-1:123456789012:bucket/handson-s3vectors-intro-20261011-01-vectors` | 合格 | |
| step-6#1 | `aws s3vectors list-tags-for-resource --resource-arn "${VECTOR_BUCKET_ARN}" ...` | `handson-job-id` を含む | `handson-job-id: s3vectors-intro-20261011-01` + `aws:cloudformation:*` 3件 | 合格 | 本文に「ほかのタグがあってもよい」と明記あり |
| step-7#1 | `INDEX_ARN=$(...)` | — | exit 0 | 合格 | |
| step-7#2 | `echo ${INDEX_ARN}` | `...:bucket/...-vectors/index/...-docs` で終わる | 一致 | 合格 | |
| step-8#1 | `aws s3vectors list-tags-for-resource --resource-arn "${INDEX_ARN}" ...` | `handson-job-id` を含む | 含む(+ `aws:cloudformation:*`) | 合格 | |
| step-9#1 | `jq -r '[.key, .category, .text] \| @tsv' ../data/docs.jsonl` | 8行、カテゴリ構成、1行目に16時30分 | 期待例と完全一致 | 合格 | |
| step-10#1 | `aws bedrock-runtime invoke-model ... work/emb-doc-01.json` | `"contentType": "application/json"` | 一致 | 合格 | |
| step-11#1 | `jq '{dimension: ..., inputTextTokenCount: ...}' work/emb-doc-01.json` | dimension 256、トークン数 ≥1 | `dimension: 256`、`inputTextTokenCount: 90` | 合格 | 例(45)と異なるが本文に「異なることがある」と明記 |
| step-12#1 | `for KEY in ...; do aws bedrock-runtime invoke-model ...; done` | `embedded: doc-01`〜`doc-08`、エラーなし | 8行、stderr 空 | 合格 | |
| step-12#2 | `jq -r '[input_filename, (.embedding \| length)] \| @tsv' work/emb-doc-*.json` | 8ファイルすべて 256 | 一致 | 合格 | |
| step-13#1 | `for KEY in ...; do aws s3vectors put-vectors ...; done` | `put: doc-01`〜`doc-08`、エラーなし | 8行、stderr 空 | 合格 | |
| step-14#1 | `aws s3vectors list-vectors ... --query 'length(vectors)'` | `8` | `8` | 合格 | |
| step-15#1 | `aws s3vectors get-vectors ... --keys doc-01 --return-metadata ...` | category expense、source_text に16時30分 | 一致 | 合格 | |
| step-16#1 | `aws s3vectors list-vectors ... --query 'sort(vectors[].key)' --output text` | doc-01〜doc-08 が1行 | 一致 | 合格 | |
| step-17#1 | `QUESTION="..."` | — | exit 0 | 合格 | |
| step-17#2 | `echo "${QUESTION}"` | 質問文 | 一致 | 合格 | |
| step-18#1 | `aws bedrock-runtime invoke-model ... work/emb-query.json` | `"contentType": "application/json"` | 一致 | 合格 | |
| step-18#2 | `jq '.embedding \| length' work/emb-query.json` | `256` | `256` | 合格 | |
| step-19#1 | `aws s3vectors query-vectors ... --top-k 3 --return-distance --return-metadata ... > work/query-result.json` | — | exit 0 | 合格 | |
| step-19#2 | `jq -r '.vectors[] \| [...] \| @tsv' work/query-result.json` | 3行、1行目 doc-01 / expense、距離が昇順 | `doc-01 0.0450 expense` / `doc-07 0.7469 facility` / `doc-03 0.7602 expense` | 合格 | 2・3行目と距離値は例と異なるが、本文に「異なることがある」と明記。距離は全桁で表示される(例は4桁に丸めた表記) |
| step-20#1 | `aws bedrock-runtime converse --model-id amazon.nova-lite-v1:0 ... \| tee work/answer-norag.txt` | 一般的な説明にとどまる回答 | 「通常、月末の数日前…会社によって異なる」という一般論 | 合格 | |
| step-20#2 | `jq -R -s 'test("16時30分\|16:30\|16時半")' work/answer-norag.txt` | `false` | `false` | 合格 | |
| step-21#1 | `aws bedrock-runtime converse ... --system ... \| tee work/answer-rag.txt` | 23日16時30分が締め切りと述べる回答 | 「ハルニレ精算での経費精算の申請締め切りは、毎月23日の16時30分です。」 | 合格 | |
| step-21#2 | `jq -R -s 'test(...)' work/answer-rag.txt` | `true` | `true` | 合格 | |
| step-22#1 | `aws s3vectors query-vectors ... --top-k 1 ...` | `doc-01` のみ | `doc-01` | 合格 | |
| step-23#1 | `aws s3vectors query-vectors ... --top-k 5 --return-metadata ...` | 5行、1行目 doc-01 expense、it/facility が2行以上 | doc-01 expense / doc-07 facility / doc-03 expense / doc-08 facility / doc-02 expense | 合格 | 順番は例と異なる(本文に明記あり) |
| step-24#1 | `aws s3vectors query-vectors ... --filter '{"category": {"$eq": "expense"}}' ...` | 3行、すべて expense | doc-01 / doc-03 / doc-02 すべて expense | 合格 | |
| step-25#1 | `aws s3vectors query-vectors ... --filter '{"category": {"$eq": "it"}}' ...` | 3行、すべて it、doc-01 を含まない | doc-06 / doc-05 / doc-04 すべて it | 合格 | |

## 3. 後片付け検証

| ブロック | コマンド(本文のまま) | 確認ポイント | 実際の結果 | 判定 |
| --- | --- | --- | --- | --- |
| cleanup-1#1 | `rm -rf work` | — | exit 0 | 合格 |
| cleanup-1#2 | `test -d work && echo remaining \|\| echo removed` | `removed` | `removed` | 合格 |
| cleanup-2#1 | `npx cdk destroy -c jobId=${HANDSON_JOB_ID} --force` | `✅  Handson-...: destroyed` | Index → VectorBucket の順に DELETE_COMPLETE、`✅  Handson-s3vectors-intro-20261011-01: destroyed` | 合格 |
| cleanup-2#2 | `aws cloudformation describe-stacks --stack-name Handson-${HANDSON_JOB_ID}` | `Stack with id ... does not exist` | `ValidationError ... Stack with id Handson-s3vectors-intro-20261011-01 does not exist`(exit 254、想定どおりのエラー) | 合格 |
| cleanup-3#1 | `aws s3vectors list-vector-buckets --prefix ... --query 'length(vectorBuckets)'` | `0` | `0` | 合格 |
| cleanup-4#1 | `aws s3vectors get-vector-bucket --vector-bucket-name handson-${HANDSON_JOB_ID}-vectors` | `NotFoundException` | `NotFoundException ... The specified vector bucket could not be found`(exit 254、想定どおり) | 合格 |
| cleanup-5#1 | `aws resourcegroupstaggingapi get-resources --tag-filters ...` | 何も表示されない | 空 | 合格 |
| cleanup-5#2 | `../../../scripts/list-tagged.sh ${HANDSON_JOB_ID} ${AWS_PROFILE} ${AWS_REGION}` | 各節が空 | 4つの節(タグ付きリソース / CloudFormation スタック / IAM ロール / S3 Vectors)がすべて空 | 合格 | 

| # | チェック | 方法 | 結果 | 判定 |
| --- | --- | --- | --- | --- |
| C1 | 本文のクリーンアップ手順を実行 | 後片付けのブロックを上から `run_step` | 全ブロックが確認ポイントどおり | 合格 |
| C2 | タグ付きリソースが0件 | `list_tagged_resources` の `remainingCount` | `remainingCount: 0`、`pendingPropagation: []`(2026-10-11T15:05:47Z) | 合格 |
| C3 | タグを付けられないリソースの残骸なし | `name-match` と `cleanup-checklist` の該当項目 | name-match のロググループなし。S3 Vectors はバケット・インデックスとも API で不在を確認(cleanup-3 / cleanup-4)。ロググループ・IAM ロール・KMS キーを作らない構成 | 合格 |
| C4 | teardown 後の残り | `teardown` の `remainingCount` | `0`(cdk destroy は対象スタックなしで正常終了) | — |

## 判定

- 結果: **合格**
- 失敗した手順: なし
- エラー出力: なし(cleanup-2#2 と cleanup-4#1 の exit 254 は確認ポイントで期待されたエラー)
- 直前の状態: —
- 上限による停止: なし
- 見積もり(このラウンド): $0.1536(ラウンド経過 3.3 分、時間課金なし)

### 執筆担当への参考(不合格理由ではない軽微な指摘)

1. 後片付けの本文は `list-tagged.sh` について「3つの節(タグ付きリソース / CloudFormation スタック / IAM ロール)がすべて空であれば完了」と書いているが、実際の出力は「S3 Vectors のベクトルバケットとインデックス」を含む4節だった。記述を4節に合わせると読者が迷わない。
2. 手順19の出力例は距離を4桁(`0.2618`)で示しているが、実際は `0.045043349266052246` のように全桁で表示される。例を実際の表示形式に近づけるとよい。
3. 手順1の「完了まで1〜3分」に対し、実測はデプロイ 11 秒・全体 23 秒だった(問題なし)。
