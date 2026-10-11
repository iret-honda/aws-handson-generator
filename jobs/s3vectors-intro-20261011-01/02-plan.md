# 構成案: Amazon S3 Vectors 入門 ― ベクトルバケットに文書を入れて、検索結果で答える RAG を CLI で組む

| 項目 | 値 |
| --- | --- |
| ジョブID | s3vectors-intro-20261011-01 |
| AWSプロファイル | default |
| アカウントID | 123456789012 |
| リージョン | ap-northeast-1 |
| IaC | CDK(TypeScript)。スタック名 `Handson-s3vectors-intro-20261011-01` |
| レベル / 所要時間 | 入門 / 60分 |
| 見積もり(検証1回) | $0.1537 / 上限 $1.00(却下ライン $0.80)。4回分の合計 $0.6148 |

> **承認の前に決めてほしいこと(ブロッカー)**: 今の sandbox-runner のポリシーでは、`aws bedrock-runtime invoke-model` と `converse` が「対象を確認できない変更系の操作」として拒否される(01-research.md 8節)。このハンズオンの検証には、この2つを許可する変更が要る。下の「リスク」の R1 と R2 を参照。

## 目的

CDK で S3 Vectors のベクトルバケットとベクトルインデックスを作る。CLI だけで、文書の埋め込み(Bedrock の Titan Text Embeddings V2)→ `put-vectors` での登録 → `query-vectors` での類似検索 → 検索結果をプロンプトに入れて Bedrock の Nova Lite で回答、という RAG の流れを一通り動かす。最後にメタデータフィルタで検索対象を絞り、結果の違いを確かめる。

## 対象者と前提

- 対象者: AWS CLI を日常的に使い、RAG を言葉としては知っているが、ベクトルストアを自分で触ったことがない社内エンジニア
- 前提知識: AWS CLI の基本操作(`--query`、`--output`)、`npx cdk deploy` / `destroy` を実行したことがある程度の CDK の知識、`jq` の基本
- 前提環境: Node.js 22 以上、AWS CLI v2(`aws s3vectors` があるもの。リファレンスは 2.37.12 で確認)、`jq`、対象アカウントで `CDKToolkit` スタック(CDK ブートストラップ)が作成済みであること(ハンズオンでは作らない)。Bedrock の Amazon 製モデル(Titan、Nova)を呼べる権限

## 学べること

- ベクトルバケットとベクトルインデックスの関係。インデックスの次元数・距離尺度・非フィルタ対象メタデータキーは作成後に変えられないこと
- 埋め込みモデルの出力次元とインデックスの次元を合わせる必要があること(Titan V2 の `dimensions: 256` と `Dimension: 256`)
- `put-vectors` でのベクトルとメタデータ(フィルタ対象 `category`、非フィルタ対象 `source_text`)の登録
- `query-vectors` の `--top-k`、`--return-distance`、`--return-metadata` と、cosine 距離の読み方(小さいほど近い)
- RAG の最小構成: 検索で取り出した本文をプロンプトに差し込むと、モデルが知らない社内情報に答えられるようになること
- `--filter` によるメタデータフィルタで、検索対象を絞る方法

## 作るリソース

すべてに `handson-job-id=s3vectors-intro-20261011-01` タグを付ける(`Tags.of(app)`)。

| リソース | 名前 | 作り方 | 課金 | 消し方 |
| --- | --- | --- | --- | --- |
| S3 Vectors ベクトルバケット(`CfnVectorBucket`、SSE-S3 既定。KMS は使わない) | `handson-s3vectors-intro-20261011-01-vectors` | CDK(L1) | 保存量(GB-月)と API リクエスト | `npx cdk destroy`(`RemovalPolicy.DESTROY`) |
| S3 Vectors ベクトルインデックス(`CfnIndex`、float32、256次元、cosine、`nonFilterableMetadataKeys: ["source_text"]`) | `handson-s3vectors-intro-20261011-01-docs` | CDK(L1)。**`vectorBucketArn: bucket.attrVectorBucketArn` で参照し、バケットより先に消えるようにする** | PutVectors の登録バイト、QueryVectors | `npx cdk destroy`(中のベクトルも一緒に消える) |
| ベクトル 8件(社内の架空サービスの FAQ。`category` は2〜3種類) | key `doc-01`〜`doc-08` | CLI(`put-vectors`) | 上記に含む | インデックスの削除で消える(個別の削除は不要) |
| CloudFormation スタック | `Handson-s3vectors-intro-20261011-01` | CDK | なし | `npx cdk destroy` |

- `CfnOutput` に `VectorBucketName`、`IndexName`、`VectorBucketArn`、`IndexArn` を出す。本文では、スタックの出力から環境変数に入れる。
- Bedrock 側で作るリソースはない(オンデマンドのモデル呼び出しだけ)。
- 題材の文書は、モデルが一般知識では答えられない架空の社内情報にする(例: 架空の社内システムの申請締め日、問い合わせ窓口の内線番号)。RAG の有無で回答が変わることを確認ポイントにするため。文書ファイル(`data/docs.jsonl` など)は執筆担当が成果物に含める。
- 生成モデルは **Nova Lite(`amazon.nova-lite-v1:0`)をリージョン内で呼ぶ**。推論プロファイルが要らず、SCP で他リージョンを止めているアカウントでも動くため。Nova 2 Lite は東京では `jp.` 推論プロファイル経由になるので、本文の補足で触れるだけにする。
- Bedrock Knowledge Bases は使わない(理由は 01-research.md 9節。応用編の題材に回す)。

## 章立て

| # | 手順 | 確認ポイントの概要 | 目安 | 備考 |
| --- | --- | --- | --- | --- |
| 1 | 事前準備: 環境変数(`AWS_PROFILE`、`AWS_REGION`、`HANDSON_JOB_ID`)を設定し、`aws sts get-caller-identity` でアカウントを確認する。`aws --version`、`aws s3vectors help`、`jq --version` でツールを確認する。`CDKToolkit` スタックの存在を確認し、`npm ci` を実行する。`aws bedrock get-foundation-model` で Titan V2 と Nova Lite が東京で使えることを確認する | `Account` が 123456789012。CLI が v2 で `s3vectors` がある。`CDKToolkit` が `CREATE_COMPLETE` か `UPDATE_COMPLETE`。2つのモデルの `modelLifecycle.status` が `ACTIVE` | 10分 | |
| 2 | 基本リソースを作る: `npx cdk deploy -c jobId=${HANDSON_JOB_ID}` でベクトルバケットとインデックスを作り、出力から `VECTOR_BUCKET`、`INDEX_NAME` を取る | スタックが `CREATE_COMPLETE`。`get-index` で `dimension=256`、`distanceMetric=cosine`、`nonFilterableMetadataKeys` に `source_text`。`list-tags-for-resource` でバケットとインデックスの両方に `handson-job-id` がある | 8分 | deploy は1回だけ(01-research.md 4節。再 deploy はしない) |
| 3-1 | 埋め込みを作る: 1件の文書を `bedrock-runtime invoke-model`(Titan V2、`dimensions: 256`)に渡し、出力ファイルを `jq` で読む | `jq '.embedding | length'` が 256。`inputTextTokenCount` が返る | 5分 | 埋め込みの数値は画面に出さない(出力が長いため) |
| 3-2 | ベクトルを登録する: 8件の文書をループで埋め込み、`put-vectors` で `key`・`data.float32`・`metadata.category`・`metadata.source_text` を登録する | `list-vectors --query 'length(vectors)'` が 8。`get-vectors --keys doc-01 --return-metadata` でメタデータが読める | 8分 | ループは `while read` + `jq -c`。1件ずつ登録する(コマンドラインを短く保つため) |
| 3-3 | 類似検索する: 質問文を同じモデル・同じ次元で埋め込み、`query-vectors --top-k 3 --return-distance --return-metadata` を実行する | 1位の `key` が、質問に対応する文書(本文で期待値を明示)。`distance` が昇順に並ぶ | 6分 | 埋め込みモデルを変えると検索が壊れる(同じモデルを使う理由)ことを本文で説明する |
| 3-4 | RAG で答える: 先に、検索結果なしで質問を `converse`(Nova Lite、`temperature: 0`、`maxTokens: 512`)に投げる。次に、3-3 の `source_text` をプロンプトに入れて同じ質問を投げる | 検索結果なしでは架空の事実(例: 締め日)を答えられない。ありでは回答に期待するキーワードが含まれる(`grep` で判定) | 8分 | 生成は非決定的なので、判定はキーワードの有無だけにする |
| 4 | 設定を変えて違いを見る: 同じ質問ベクトルで `--filter '{"category":{"$eq":"..."}}'` を付けて検索し、フィルタなしと結果を比べる。`--top-k` を 1 と 5 に変えて件数の違いも見る | フィルタありでは、返る全件の `metadata.category` が指定値になる(`jq` で確認)。フィルタなしの1位が別カテゴリの場合、それが消える。`--top-k` どおりの件数が返る | 10分 | インデックスの設定は変えられないので、「変える設定」はクエリ側のオプションにする。`--query-mode` は使わない(2026-09の新機能で展開中だったため) |
| 5 | 後片付け: `npx cdk destroy -c jobId=${HANDSON_JOB_ID} --force`。その後、`aws s3vectors list-vector-buckets --prefix handson-${HANDSON_JOB_ID}` が空、`get-vector-bucket` が `NotFoundException` であることを確かめる。`./scripts/list-tagged.sh` も実行する。作業ディレクトリの埋め込み JSON を消す | スタックが見つからない。ベクトルバケットの一覧が空。`list-tagged.sh` の3節がすべて空 | 5分 | S3 Vectors の確認は必須(sandbox-runner と Tagging API で判定できないため。R2) |

合計 60分。コンソール手順はない(すべて CLI と CDK で完結する)。

## 費用見積もり

`aws-pricing` で取得した ap-northeast-1 の単価(S3 Vectors は effectiveDate 2026-09-01、Bedrock は 2026-10-01)。無料枠は考慮しない。

| リソース | 単価 | 想定量(検証1回) | 金額 |
| --- | --- | --- | --- |
| Titan Text Embeddings V2 入力 | $0.000029 / 1K トークン | 50,000 トークン(文書8件 + 質問、再実行分を上乗せ) | $0.0015 |
| Nova Lite 入力 | $0.000072 / 1K トークン | 80,000 トークン(converse 20回 × 約4,000) | $0.0058 |
| Nova Lite 出力 | $0.000288 / 1K トークン | 20,000 トークン(20回 × maxTokens 512 を上限に、多めに) | $0.0058 |
| S3 Vectors PutVectors | $0.219 / GB | 1 MB(実際は 8件 × 約3KB) | $0.0002 |
| S3 Vectors ストレージ | $0.066 / GB-月 | 1 MB を1か月分(実際は1時間未満) | $0.0001 |
| S3 Vectors QueryVectors | $0.0027 / 1,000 リクエスト | 100 回 | $0.0003 |
| S3 Vectors その他の API(Put / Get / List / Tag、CloudFormation の作成・削除) | $0.06 / 1,000 リクエスト | 500 回 | $0.0300 |
| S3 Vectors クエリ処理・返却バイト | $0.000004278 / GB、$0.01 / GB | 1 GB、10 MB | $0.0001 |
| CloudFormation | 追加料金なし | deploy 1回、destroy 1回 | $0.0000 |
| バッファ: CDK アセットの S3 リクエスト | 単価未取得 | — | $0.0100 |
| バッファ: 生成モデルを Nova 2 Lite(jp.)に替えた場合の差額(約 $0.087)と再実行 | — | — | $0.1000 |
| 合計 | | | **$0.1537** |

- 4回分(初回と修正3回)の合計: $0.6148。sandbox-runner の teardown ライン(全ラウンド合計 $0.90)にも届かない。
- バッファを除いた実質の見積もりは約 $0.044。

時間課金のリソース: なし(S3 Vectors は従量のみで最低料金なし。Bedrock はオンデマンドのトークン課金)。

## リスクと消し忘れポイント

- **R1(ブロッカー): sandbox-runner が Bedrock の呼び出しを拒否する。** `policy.check_aws` は、読み取り系でない操作で、引数にジョブIDも ARN もないものを拒否する。`bedrock-runtime invoke-model` と `converse` がこれに当たる。案: `policy.py` に「リソースを作らない推論呼び出し」として `bedrock-runtime:invoke-model` と `bedrock-runtime:converse` を、モデルIDの許可リスト(`amazon.titan-embed-text-v2:0`、`amazon.nova-lite-v1:0`)付きで許可する。費用は `estimate_job_cost` の見積もりで抑える。出力ファイル名にジョブIDを入れればガードを通ってしまうが、ガードの迂回になるので使わない。**承認時に、ポリシーを変えるか(人の判断)を決めてほしい。** 変えない場合は、このハンズオンは自動検証できない。
- **R2: sandbox-runner と Tagging API で S3 Vectors の後片付けを判定できない。** `resources.py` の `DESCRIBERS` / `DELETERS` に `s3vectors` がなく、`kind_of()` はインデックスの ARN もバケットとして扱う。S3 Vectors が Resource Groups Tagging API に出るかもドキュメントで確認できなかった。出なければ残骸があっても `remainingCount=0` で合格し、出れば削除後も反映待ちの間「残っている」と数えられ、teardown は「要手動削除」を返す。対策: (1) 本文の後片付けに `list-vector-buckets --prefix` と `get-vector-bucket` での確認を入れる(この構成案に含めた)。(2) `resources.py` に、`s3vectors:bucket` / `s3vectors:index` の判定、`get_vector_bucket` / `get_index` での実在確認、`delete_index` → `delete_vector_bucket` の順の削除、`list_vector_buckets(prefix=ジョブID)` による名前一致の棚卸しを足すことを提案する(人の承認後に実装)。`scripts/list-tagged.sh` と `cleanup-stale.sh` にも同じ確認が要る。
- **CloudFormation の削除順**: インデックスがバケットを文字列の名前で参照すると依存関係ができず、バケットを先に消そうとして「空でない」で `DELETE_FAILED` になりうる。`vectorBucketArn: bucket.attrVectorBucketArn` で参照する(静的チェックで、synth したテンプレートの `Fn::GetAtt` を確かめる)。
- **再 deploy をしない**: VectorBucket は Update ハンドラーがないという情報があり、ドキュメントと食い違う(01-research.md 4節)。タグやプロパティを変える再 deploy は避け、deploy は1回だけにする。修正ループでは destroy してから deploy し直す(バケット名は削除後に再利用できる)。
- **インデックスの設定は変えられない**: 次元数を変える手順を入れない。Titan V2 の `dimensions` とインデックスの 256 がずれると `put-vectors` が失敗する。本文で同じ値を環境変数(`EMBED_DIM=256`)から使い、ずれないようにする。
- **`jq` が要る**: インタープリターの直接実行が禁止なので、JSON の加工は `jq` と `--query` だけで行う。検証環境に `jq` があるかは未確認。事前準備で `jq --version` を確認する。
- **出力の長さ**: 埋め込みは256個の数値で、そのまま表示すると sandbox-runner の出力上限(12,000文字)に近づく。埋め込みはファイルに書き、画面には件数と key と距離だけを出す。
- **生成の非決定性**: Nova Lite の回答は実行ごとに変わりうる。`temperature: 0` にし、確認はキーワードの有無だけで判定する。検索結果なしの回答で「架空の事実を答えられない」ことの判定は、キーワードが含まれないことで見る(偶然一致しない固有の値を題材にする)。
- **メタデータの権限**: `--return-metadata` と `--filter` には `s3vectors:GetVectors` 権限も要る。default プロファイルの権限が絞られている場合は 403 になる。
- **事前フィルタの展開**: 2026-09-30 発表の事前フィルタは「展開中」とされていた。本文では `--query-mode` を指定しない。8件のデータでは結果に差は出ないと推測している。
- **モデルのライフサイクル**: Nova Lite は Active だが、2024年12月公開のモデルで旧ライフサイクルポリシーの対象。Legacy になったら Nova 2 Lite(`jp.amazon.nova-2-lite-v1:0`)に切り替える。その場合は推論プロファイルと送信先リージョン(東京・大阪)の権限が要り、費用は1回あたり約 $0.087 増える(バッファの範囲内)。
- **消し忘れ**: AWS 上に作るのはバケットとインデックスだけで、ベクトルはインデックスと一緒に消える。CLI で作る AWS リソースはない。手元の埋め込み JSON は後片付けで消す。`CDKToolkit` とそのアセットはアカウント共通なので対象外。

## 参照ドキュメント

- https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-regions-quotas.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-limitations.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-create-index.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-index-delete.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-buckets-delete.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-tags.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/vector-index-tagging.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-bedrock-kb.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-s3vectors-vectorbucket.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-s3vectors-index.html
- https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_s3vectors-readme.html
- https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_s3vectors.CfnIndex.html
- https://docs.aws.amazon.com/cli/latest/reference/s3vectors/query-vectors.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-titan-text-embeddings-v2.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-titan-embed-text.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-lite.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-2-lite.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/geographic-cross-region-inference.html
- https://docs.aws.amazon.com/ARG/latest/userguide/supported-resources.html
- https://aws.amazon.com/about-aws/whats-new/2025/12/amazon-s3-vectors-generally-available/
- https://aws.amazon.com/about-aws/whats-new/2026/09/s3-vectors-introduces-metadata-pre-filtering/
