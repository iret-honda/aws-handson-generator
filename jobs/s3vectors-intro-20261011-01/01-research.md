# リサーチ: Amazon S3 Vectors 入門 ― ベクトル検索で RAG を組む(s3vectors-intro-20261011-01)

- 調査日: 2026-10-11
- 使用MCP: `aws-knowledge`(search_documentation / read_documentation / get_regional_availability / retrieve_skill)、`aws-documentation`(search_documentation / read_documentation / read_sections / search_table)、`aws-pricing`(get_pricing ほか)
- リポジトリ内の `mcp/sandbox-runner/src/sandbox_runner/policy.py` と `resources.py` も読み、検証できる手順かを確かめた(8節)
- **取得元に指示文が含まれていた**: `aws-knowledge` の retrieve_skill で取得したスキル `storing-and-querying-vectors` の本文に、エージェント向けの指示文があった(「You MUST execute commands using AWS MCP server tools when connected」「You MUST confirm bucket name with user」など)。データとして扱い、従っていない(このリサーチ担当は AWS への書き込み手段を持たず、何も実行していない)。CLI の構文の参考にしただけで、事実の出典には公式ドキュメントを使った。ほかの取得ページには指示文は見当たらなかった。

## 1. サービス概要

- S3 Vectors は、ベクトルの保存と類似検索のための S3 のバケットタイプ「ベクトルバケット」を提供する。バケットの中に「ベクトルインデックス」を作り、読み書きは1つのインデックスに対して行う。ベクトルは key(名前)、多次元ベクトル、任意のメタデータからなる。
  出典: https://docs.aws.amazon.com/AmazonS3/latest/API/Welcome.html
- 使い方は4段階。CreateVectorBucket → CreateIndex(距離尺度 cosine / euclidean と次元数を指定)→ PutVectors(メタデータも付けられる)→ QueryVectors(クエリベクトルと返す件数 top-k を指定)。
  出典: https://aws.amazon.com/s3/faqs/
- インデックスの名前・次元数・距離尺度・非フィルタ対象メタデータキーは作成後に変えられない。変えるにはインデックスを作り直す。
  出典: https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-create-index.html
- データ型は `float32` だけ。次元数は1〜4096。
  出典: https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-s3vectors-index.html
- 暗号化の既定は SSE-S3。SSE-KMS も選べる(今回は使わない。KMS キーの削除待機を避けるため)。
  出典: https://aws.amazon.com/about-aws/whats-new/2025/12/amazon-s3-vectors-generally-available/
- QueryVectors でメタデータフィルタ(`--filter`)か `--return-metadata` を使うには、`s3vectors:QueryVectors` に加えて `s3vectors:GetVectors` 権限が要る。ないと 403。
  出典: https://docs.aws.amazon.com/cli/latest/reference/s3vectors/query-vectors.html
- Bedrock Knowledge Bases のベクトルストアとして S3 Vectors を選べる。この場合、ハイブリッド検索は使えず意味検索だけになる。カスタムメタデータは1ベクトルあたり1KB・35キーまで。
  出典: https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-bedrock-kb.html

## 2. 最近の変更(What's New)

| 日付 | 内容 | 出典 |
| --- | --- | --- |
| 2025-07 | プレビュー開始(5リージョン。東京は含まれていなかった) | https://aws.amazon.com/about-aws/whats-new/2025/07/amazon-s3-vectors-preview-native-support-storing-querying-vectors/ |
| 2025-12-02 | 一般提供(GA)。14リージョン。インデックスあたり20億ベクトル、1クエリ最大100件、1ベクトルあたりメタデータキー50個まで。ベクトルバケットとインデックスへのタグ付け(ABAC、コスト配分)に対応 | https://aws.amazon.com/about-aws/whats-new/2025/12/amazon-s3-vectors-generally-available/ |
| 2026-03 | 17リージョン追加で計31リージョン | https://aws.amazon.com/about-aws/whats-new/2026/03/s3-vectors-expands-17-regions/ |
| 2026-07 | GovCloud (US) で提供開始 | https://aws.amazon.com/about-aws/whats-new/2026/07/s3-vectors-available-aws-govcloud-regions/ |
| 2026-08 | European Sovereign Cloud (Germany) で提供開始 | https://aws.amazon.com/about-aws/whats-new/2026/08/amazon-s3-vectors-european-sovereign-cloud-germany/ |
| 2026-09-30 | メタデータの事前フィルタ(pre-filtering)と `$startsWith` 演算子を追加。新しいベクトルバケットのインデックスは事前フィルタが既定になる。既存インデックスは UpdateIndexMode で切り替える。QueryVectors にクエリごとのモード指定(`--query-mode CLASSIC|ENHANCED`)が付いた。**発表時点で「展開中、数日で完了予定」と書かれている** | https://aws.amazon.com/about-aws/whats-new/2026/09/s3-vectors-introduces-metadata-pre-filtering/ |

ハンズオンへの影響:
- 事前フィルタは発表から11日しか経っておらず、展開が完了したかを確認できていない。本文では `--query-mode` を指定せず、インデックスの既定の動作に任せる。8件程度のデータではフィルタの方式による違いは出ない(推測)。事前フィルタは題材にしない。

## 3. リージョン提供状況(ap-northeast-1)

| 種別 | 対象 | 状態 | 出典 |
| --- | --- | --- | --- |
| リージョンとエンドポイント | Asia Pacific (Tokyo) `ap-northeast-1`、`s3vectors.ap-northeast-1.api.aws`(HTTPS、SigV4、デュアルスタック) | 提供中 | https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-regions-quotas.html |
| CloudFormation | `AWS::S3Vectors::VectorBucket`、`AWS::S3Vectors::Index`、`AWS::S3Vectors::VectorBucketPolicy` | isAvailableIn | get_regional_availability |
| CloudFormation | `AWS::Bedrock::KnowledgeBase`、`AWS::Bedrock::DataSource` | isAvailableIn | 同上 |
| API | `S3Vectors+CreateVectorBucket` / `CreateIndex` / `PutVectors` / `QueryVectors` / `GetVectors` / `ListVectors` / `DeleteVectors` / `DeleteIndex` / `TagResource` / `ListTagsForResource` | isAvailableIn | 同上 |
| API | `Bedrock Runtime+InvokeModel`、`Bedrock Runtime+Converse`、`Bedrock Agent Runtime+RetrieveAndGenerate`、`Bedrock Agent+StartIngestionJob` | isAvailableIn | 同上 |

S3 Vectors 本体は東京で一般提供されている。プレビューの機能は使わない。

### Bedrock のモデル(ap-northeast-1)

| 用途 | モデル | モデルID | 東京での呼び方 | 出典 |
| --- | --- | --- | --- | --- |
| 埋め込み | Amazon Titan Text Embeddings V2 | `amazon.titan-embed-text-v2:0` | **リージョン内で呼べる**(In-Region ○。Geo / Global の推論プロファイルはなし)。InvokeModel のみ(Converse は非対応)。出力次元は 256 / 512 / 1024 を選べる | https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-titan-text-embeddings-v2.html 、 https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-titan-embed-text.html |
| 生成(推奨) | Amazon Nova Lite | `amazon.nova-lite-v1:0` | **リージョン内で呼べる**(In-Region ○)。Geo は `apac.amazon.nova-lite-v1:0`(送信先に東京・ソウル・大阪・ムンバイ・シンガポール・シドニー)。Converse / Invoke 対応。モデルのライフサイクルは Active | https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-lite.html |
| 生成(代替) | Amazon Nova 2 Lite | `amazon.nova-2-lite-v1:0` | **東京ではリージョン内呼び出し不可**。推論プロファイルが必要: Geo `jp.amazon.nova-2-lite-v1:0`(送信先は東京・大阪)、Global `global.amazon.nova-2-lite-v1:0` | https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-2-lite.html |

- モデルアクセス: 多くのモデルは既定で有効。サードパーティモデルは初回呼び出し時に Marketplace のサブスクリプションが自動で始まり、Anthropic のモデルは初回利用フォーム(FTU)が要る。
  出典: https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html
  - Amazon 製モデル(Titan、Nova)を使えば、Marketplace のサブスクリプションと FTU フォームの手続きは要らない(推測。ドキュメントは「サードパーティモデルは」と書いており、Amazon 製モデルについては書いていない)。sandbox-runner の設定で `marketplace-catalog` を禁止しているので、サードパーティモデル(Anthropic など)は使わない。
- Geo 推論プロファイルを使うには、推論プロファイルと、送信先の全リージョンの基盤モデルへの `bedrock:InvokeModel` 権限が要る。SCP で送信先のリージョンを止めていると失敗する。
  出典: https://docs.aws.amazon.com/bedrock/latest/userguide/geographic-cross-region-inference.html
  → 推奨構成は推論プロファイルが要らない Nova Lite(リージョン内呼び出し)にする。大阪や他の APAC リージョンを SCP で止めていても影響を受けない。

## 4. CloudFormation / CDK の対応とタグ

### CloudFormation リソース

| リソース | 主なプロパティ | タグ | 削除 | 出典 |
| --- | --- | --- | --- | --- |
| `AWS::S3Vectors::VectorBucket` | `VectorBucketName`(3〜63文字、小文字・数字・ハイフン、アカウント×リージョンで一意)、`EncryptionConfiguration`、`Tags` | `Tags` あり(更新は No interruption) | DeletionPolicy で Delete か Retain を選ぶ。**空のバケットしか消せない**(中身があると失敗) | https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-s3vectors-vectorbucket.html |
| `AWS::S3Vectors::Index` | `DataType`(float32)、`Dimension`、`DistanceMetric`、`IndexName`(3〜63文字、小文字・数字・ハイフン・ドット)、`MetadataConfiguration`、`VectorBucketName` か `VectorBucketArn`、`Tags`。Tags 以外はすべて Replacement | `Tags` あり(更新は No interruption) | DeletionPolicy で選ぶ | https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-s3vectors-index.html |
| `AWS::S3Vectors::VectorBucketPolicy` | (今回は使わない) | — | — | https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/AWS_S3Vectors.html |

- 中のベクトルは、インデックスを消せば一緒に消える。「ベクトルが入っていてもインデックスは削除できる。中のベクトルとメタデータは完全に消える」。バケットを消すには、先にインデックスを全部消す必要がある。バケット名は削除後に再利用できる。
  出典: https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-index-delete.html 、 https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-buckets-delete.html
  - 補足: バケット削除のページには「インデックスがあれば、各インデックスのベクトルを消してからインデックスを消す」とも書かれており、インデックス削除のページと書き方が食い違う。インデックス削除のページのほうが具体的(「ベクトルが入っていても削除できる」)なので、そちらを正とする。ベクトルが入ったまま `cdk destroy` で消せるかは、検証で確かめる。
- ドキュメント検索の関連情報に「VectorBucket は Create / Read / Delete に対応し、Update と List には対応しない」とあった(search_documentation の relationships 欄)。一方で、リソースのページには Tags の更新は No interruption とあり、権限の節にも List が載っている。食い違うので、**deploy は1回だけにし、タグやプロパティを変えての再 deploy はしない**構成にする(推測に基づく安全策)。

### CDK

- `aws-cdk-lib/aws-s3vectors` に L1 の `CfnVectorBucket`、`CfnIndex`(と `CfnVectorBucketPolicy`)がある。**L2 はない**。
  出典: https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_s3vectors-readme.html 、 https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_s3vectors.CfnIndex.html
- `CfnIndex` は `ITaggableV2` を実装しているので、`Tags.of(app).add('handson-job-id', jobId)` が効く。`CfnVectorBucket` も `Tags` プロパティがあるので同様と推測する(synth したテンプレートに両方のタグが入ることを静的チェックで確かめる)。
- `CfnIndex` に `vectorBucketName` を文字列で渡すと、CloudFormation 上の依存関係ができない。削除時にバケットを先に消そうとして「空でない」で失敗しうる。**`vectorBucketArn: bucket.attrVectorBucketArn` で参照するか、`index.addDependency(bucket)` を付ける**(執筆担当への申し送り)。
- L1 の既定の DeletionPolicy は Retain ではなく Delete(CloudFormation の既定)。iac-cdk の規約どおり `applyRemovalPolicy(RemovalPolicy.DESTROY)` も明示する。
- CDK のバージョン: 手本(sqs-intro)の aws-cdk-lib 2.273.0 系で L1 は使える(L1 は GA 前のプレビュー時点から生成されていると推測。API ページが存在することは確認した)。

### タグ付けと後片付けの観点(依頼の必須条件)

| 確認項目 | 結果 | 出典 |
| --- | --- | --- |
| ベクトルバケットにタグを付けられるか | 付けられる(作成時、または TagResource)。CloudFormation の `Tags` もある | https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-tags.html |
| ベクトルインデックスにタグを付けられるか | 付けられる(作成時、または TagResource)。CloudFormation の `Tags` もある | https://docs.aws.amazon.com/AmazonS3/latest/userguide/vector-index-tagging.html |
| 個々のベクトルにタグを付けられるか | 付けられない(タグの対象は「vector bucket or a vector index」)。ただしベクトルはインデックスの中のデータで、インデックスと一緒に消える | https://docs.aws.amazon.com/sdk-for-ruby/v3/api/Aws/S3Vectors/Client.html |
| CloudFormation で消せるか | 消せる。インデックス → バケットの順に消えるよう依存関係を付ける | 4節の上記 |
| Resource Groups Tagging API(`tag:GetResources`)に出るか | **確認できなかった**。Resource Groups のサポート対象一覧(supported-resources.html)を `S3Vectors` と `Vector` で検索したが該当行がなかった。出る・出ないのどちらとも言えない | https://docs.aws.amazon.com/ARG/latest/userguide/supported-resources.html |

**結論**: タグが付けられないリソースや CloudFormation で消せないリソースはない。ただし、sandbox-runner の棚卸しと teardown がベクトルバケットとインデックスを扱えない(8節)。そのため、本文の後片付けに S3 Vectors 専用の確認コマンドを入れ、sandbox-runner 側にも対応を加えることを提案する(02-plan.md のリスク R2)。

## 5. 関係する CLI コマンドと API

AWS CLI v2 の `aws s3vectors` で、作成から検索・削除まで全部できる。出典の CLI リファレンスは **AWS CLI 2.37.12** のもの。

| 目的 | CLI | 読み取り系か(sandbox-runner の判定) | 出典 |
| --- | --- | --- | --- |
| バケットの確認 | `aws s3vectors get-vector-bucket --vector-bucket-name` | 読み取り(`get`) | https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-buckets-delete.html |
| バケットの一覧 | `aws s3vectors list-vector-buckets --prefix` | 読み取り(`list`) | https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-limitations.html |
| インデックスの確認 | `aws s3vectors get-index --vector-bucket-name --index-name` | 読み取り | https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-index-delete.html |
| ベクトルの登録 | `aws s3vectors put-vectors --vector-bucket-name --index-name --vectors '[{"key":"..","data":{"float32":[..]},"metadata":{..}}]'`(1回500件まで) | 変更系。バケット名にジョブIDを含めれば通る | https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-limitations.html |
| ベクトルの一覧・取得 | `aws s3vectors list-vectors` / `get-vectors --keys` | 読み取り | 同上 |
| 類似検索 | `aws s3vectors query-vectors --vector-bucket-name --index-name --query-vector '{"float32":[..]}' --top-k 3 --return-distance --return-metadata [--filter '{"category":{"$eq":".."}}']` | 読み取り(`query`) | https://docs.aws.amazon.com/cli/latest/reference/s3vectors/query-vectors.html |
| タグの確認 | `aws s3vectors list-tags-for-resource --resource-arn` | 読み取り | https://docs.aws.amazon.com/AmazonS3/latest/userguide/viewing-vector-bucket-tags.html |
| 削除(本文では CDK に任せる) | `aws s3vectors delete-index` / `delete-vector-bucket` | 変更系 | https://docs.aws.amazon.com/cli/latest/reference/s3vectors/delete-vector-bucket.html |
| 埋め込みの生成 | `aws bedrock-runtime invoke-model --model-id amazon.titan-embed-text-v2:0 --cli-binary-format raw-in-base64-out --body '{"inputText":"..","dimensions":256,"normalize":true}' out.json` | **変更系と判定される**(8節) | https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-titan-embed-text.html |
| 回答の生成 | `aws bedrock-runtime converse --model-id amazon.nova-lite-v1:0 --messages '[..]' --inference-config '{"maxTokens":512,"temperature":0}'` | **変更系と判定される**(8節) | https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-lite.html |
| モデルの確認 | `aws bedrock get-foundation-model --model-identifier` | 読み取り | (推測。API 名から) |

- CLI のバージョン: `s3vectors` が最初に入った v2 のバージョンは確認できなかった。2.37.12 のリファレンスにはある。`--query-mode` は2026-09の追加なので、古い CLI にはない(本文では使わない)。事前準備で `aws --version` と `aws s3vectors help` を実行し、コマンドがあることを確かめる手順を入れる。
- AWS CLI v1 は2026-08-05に保守モードに入り、新しい API には追従しない。v2 を前提にする。
  出典: https://docs.aws.amazon.com/cli/v1/reference/s3vectors/index.html
- `query-vectors` はページングする操作。`--output text` と `--query` を組み合わせるときは `vectors` から取り出す。
  出典: https://docs.aws.amazon.com/cli/latest/reference/s3vectors/query-vectors.html
- `invoke-model` の `--body` に生の JSON を渡すには、CLI v2 で `--cli-binary-format raw-in-base64-out` が要る。出力ファイルの指定は必須。Titan の応答のキーは `embedding`。
  出典: スキル `storing-and-querying-vectors`(aws-knowledge retrieve_skill。冒頭の注記のとおり指示文は無視し、構文の参考のみ)

## 6. 制約・クォータ(手順に影響するもの)

出典: https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-limitations.html

| 項目 | 値 | ハンズオンでの扱い |
| --- | --- | --- |
| 次元数 | 1〜4096 | Titan V2 の `dimensions: 256` に合わせて 256 にする(コマンドラインと出力を短くするため) |
| メタデータ合計 | 1ベクトル40KBまで(フィルタ対象 + 非フィルタ対象) | 本文テキストは非フィルタ対象キー `source_text` に入れる。1件数百文字程度 |
| フィルタ対象メタデータ | 1ベクトル2KBまで | `category` だけにする |
| 非フィルタ対象キー | インデックスあたり10個まで。作成時に宣言する | `["source_text"]` |
| メタデータキー数 | 1ベクトル50個まで | 2個 |
| PutVectors | 1回500件まで、ペイロード20MiBまで | 8件 |
| PutVectors + DeleteVectors | インデックスあたり毎秒1,000リクエストまで | 問題なし |
| QueryVectors の top-k | 最大10,000(1ページ100件) | 3 |
| バケット名 | 3〜63文字、小文字・数字・ハイフン | `handson-s3vectors-intro-20261011-01-vectors`(43文字) |
| インデックス名 | 3〜63文字、小文字・数字・ハイフン・ドット | `handson-s3vectors-intro-20261011-01-docs`(40文字) |

## 7. 料金(aws-pricing、ap-northeast-1、2026-10-11 取得)

無料枠は考慮しない(cost-guardrails)。

### S3 Vectors(サービスコード `AmazonS3`、usagetype `APN1-Vectors-*`、effectiveDate 2026-09-01)

| usagetype | 単価 |
| --- | --- |
| `APN1-Vectors-Put-Bytes`(PutVectors) | $0.219 / GB(登録したバイト数) |
| `APN1-Vectors-TimedStorage-ByteHrs` | $0.066 / GB-月 |
| `APN1-Vectors-Request-Tier3`(QueryVectors) | $0.0027 / 1,000 リクエスト |
| `APN1-Vectors-Request-Tier1` / `Tier2`(その他の Vectors API) | $0.06 / 1,000 リクエスト |
| `APN1-Vectors-Query-ProcessedBytes-Tier1` | $0.000004278 / GB |
| `APN1-Vectors-Query-ProcessedBytes-Tier2` / `Tier3` | $0.000002139 / GB、$0.000000428 / GB |
| `APN1-Vectors-Query-Returned-Bytes` | $0.01 / GB |

- Tier1 / Tier2 にどの API が入るかは料金データに書かれていない。見積もりでは、QueryVectors 以外の呼び出し(Put / Get / List / Tag 系、CloudFormation による作成・削除)を全部 $0.06 / 1,000 で数える。
- タグの利用自体には追加料金がない(標準の API リクエスト料金のみ)。
  出典: https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-tags.html
- 時間課金や最低料金はない。ストレージは GB-月の従量。

### Bedrock(サービスコード `AmazonBedrock`、オンデマンド、effectiveDate 2026-10-01)

| usagetype | モデル | 単価 |
| --- | --- | --- |
| `APN1-TitanEmbeddingV2-Text-input-tokens` | Titan Text Embeddings V2 | $0.000029 / 1K 入力トークン |
| `APN1-NovaLite-input-tokens` | Nova Lite | $0.000072 / 1K 入力トークン |
| `APN1-NovaLite-output-tokens` | Nova Lite | $0.000288 / 1K 出力トークン |
| `APN1-Nova2.0Lite-input-tokens` | Nova 2 Lite | $0.000396 / 1K 入力トークン |
| `APN1-Nova2.0Lite-output-tokens` | Nova 2 Lite | $0.003311 / 1K 出力トークン |
| `APN1-NovaMicro-input-tokens` / `output-tokens` | Nova Micro | $0.000042 / $0.000168 / 1K トークン |

- Nova 2 Lite の Geo(`jp.`)推論プロファイルが上の APN1 単価で課金されるかは確認できなかった。料金データには `-cross-region-global` 付きの usagetype が別にある。代替案に切り替えた場合も収まるよう、見積もりにバッファを入れた(aws-cost.json)。
- クロスリージョン推論には経路やデータ転送の追加料金がない、という記述はソリューションのコストページにある(Bedrock 本体のページではない)。
  出典: https://docs.aws.amazon.com/solutions/latest/generative-ai-application-builder-on-aws/cost.html
- Bedrock Knowledge Bases は、S3 Vectors をベクトルストアにすれば OpenSearch Serverless の最低 OCU 課金はかからない。ただし Knowledge Bases のデータソース用に別の S3 バケット(汎用)と IAM ロールが要る(9節)。

## 8. sandbox-runner で検証できるか(リポジトリのコードを読んだ結果)

`mcp/sandbox-runner/src/sandbox_runner/policy.py`:

- `aws` の変更系の操作(`get|list|describe|query|...` で始まらないもの)は、引数にジョブIDを含むか、ARN の対象に `handson-job-id` タグが付いていないと拒否される(`check_aws`)。
  - `aws s3vectors put-vectors --vector-bucket-name handson-s3vectors-intro-20261011-01-vectors ...` → バケット名にジョブIDがあるので**通る**。
  - `aws s3vectors query-vectors` / `get-*` / `list-*` → 読み取り系なので**通る**。
  - `aws bedrock-runtime invoke-model` / `converse` → 操作名が読み取り系に当たらず、引数にジョブIDも ARN もないので**拒否される**。`--body` は自由記述扱い(FREE_TEXT_OPTIONS)で判定に使われず、`--messages` も同じく対象の特定に使えない。
  - (b 案)`aws bedrock-agent start-ingestion-job`、`aws bedrock-agent-runtime retrieve-and-generate` も同じ理由で拒否される。
  - 出力ファイル名にジョブIDを入れれば通ってしまうが、これはガードの意図(作成・変更する対象を確かめる)を迂回するので使わない。
- インタープリターの直接実行は禁止(`python3 -m json.tool` だけ許可)。`npx tsx` / `ts-node` は通るが、スクリプトから SDK で AWS を呼ぶとシムのガードを通らないので、本文の手順には使わない。JSON の加工は `jq` と CLI の `--query` で行う。`jq` は禁止リストにない。
- `jq` が検証環境に入っているかは確認していない(macOS 15 以降は `/usr/bin/jq` が標準で入っていると推測)。

`mcp/sandbox-runner/src/sandbox_runner/resources.py`:

- 棚卸し(`inventory`)は Tagging API、CloudFormation スタック、IAM、名前一致のロググループを見る。S3 Vectors 専用の確認はない。
- `kind_of()` はベクトルバケットの ARN(`arn:aws:s3vectors:...:bucket/<名前>`)もインデックスの ARN(`.../bucket/<名前>/index/<名前>`)も `s3vectors:bucket` と判定する。`DESCRIBERS` と `DELETERS` に `s3vectors:*` はない。
  - Tagging API に s3vectors が**出る場合**: 実在の確認ができず(`exists=None`)、削除済みでも Tagging API の反映待ちの間は「残っている」と数えられる。teardown は「要手動削除」を返す。
  - Tagging API に s3vectors が**出ない場合**: 棚卸しに出てこないので、バケットが残っても `remainingCount=0` で合格してしまう。
  - どちらの場合も、後片付け検証が S3 Vectors を正しく判定できない。

## 9. RAG の組み方の比較

| 観点 | a: 自前で組む(Titan 埋め込み + S3 Vectors query-vectors + Nova Lite converse を CLI で) | b: Bedrock Knowledge Bases のベクトルストアに S3 Vectors |
| --- | --- | --- |
| 学べること | S3 Vectors の API そのもの(put / query / filter / メタデータ)と RAG の流れ(埋め込み → 検索 → プロンプトに差し込む → 生成)が全部見える。題材(S3 Vectors)の中心を学べる | S3 Vectors は KB の裏方になり、ベクトルを直接触る場面が減る。学ぶのは主に KB |
| 作るリソース | ベクトルバケット、インデックス(+CloudFormation スタック) | 上記 + データソース用 S3 バケット(汎用)、KB 用 IAM ロール、Knowledge Base、データソース。S3 の `autoDeleteObjects` を使うとカスタムリソースの Lambda とロググループも増える |
| タグ | 全リソースに付けられる | `AWS::Bedrock::DataSource` に `Tags` プロパティがない(KB の削除で消える)。IAM ロールは Tagging API に出ない |
| 待ち時間 | deploy は短い(推測で1〜2分) | 取り込みジョブ(StartIngestionJob)が非同期で数分。KB の作成・削除も加わる |
| 60分に収まるか | 収まる | 取り込み待ちと IAM の説明が入り、S3 Vectors の操作を見せる時間が減る |
| 費用 | 埋め込み数千トークン、生成数十回で数セント | 同程度(KB 自体の料金は見積もり外。取り込み時の埋め込みトークン課金あり) |
| 後片付け | `cdk destroy` でインデックス → バケットの2つ。KB 側の残りが出ない | KB 削除時のデータ削除ポリシー(`DataDeletionPolicy`)を誤ると、KB が作ったベクトルが残る・バケットが空にならず削除失敗する余地がある(推測) |
| sandbox-runner | `invoke-model` / `converse` の許可が要る | `start-ingestion-job` / `retrieve-and-generate`(と同等の操作)の許可が要る。許可する操作が増える |
| 外部依存 | なし | なし |

**推奨は a**。理由: 入門60分で S3 Vectors の操作そのものを見せられること、作るリソースが2つでタグと削除が確実なこと、待ち時間がないこと。b は「応用」で KB を題材にするときに回す。

## 10. 消し忘れやすいリソース

| 対象 | 内容 | 対策 |
| --- | --- | --- |
| ベクトルバケット | 中にインデックスが残っていると削除に失敗する(`DELETE_FAILED`) | CDK でインデックスにバケットへの依存を付ける。後片付けで `list-vector-buckets --prefix` が空であることを確かめる |
| ベクトルインデックス | 中のベクトルはインデックスと一緒に消える | CDK で作り、DESTROY |
| CLI で登録したベクトル | IaC の外で作るデータだが、インデックスの削除で消える | 個別の削除手順は不要。後片付けの確認だけ入れる |
| sandbox-runner の棚卸し | s3vectors を判定できない(8節) | 本文に S3 Vectors 専用の確認を入れる。sandbox-runner への対応追加を提案 |
| 手元のファイル | 埋め込み結果の JSON(out.json など)が作業ディレクトリに残る | AWS のリソースではない。本文の後片付けで `rm` を案内する(作業ディレクトリ内のみ) |
| Bedrock のモデル呼び出しログ | アカウント設定でモデル呼び出しログを有効にしている場合、ログが既存の送り先に溜まる | アカウント共通の設定なのでハンズオンでは変更しない。CloudWatch Logs の確認は後片付けの対象外 |
| CDKToolkit / アセット | アカウント共通 | 対象外(作らない、消さない) |

cleanup-checklist の表に「S3 Vectors」の行を足す提案(人の承認後): 「ベクトルバケットはインデックスが残ると削除できない。Tagging API と sandbox-runner の棚卸しで扱えないため、`aws s3vectors list-vector-buckets --prefix handson-<job-id>` で確認する」。

## 11. 推測として扱っている点

- Amazon 製モデル(Titan、Nova)は Marketplace のサブスクリプションと FTU フォームなしで呼べる。
- Nova 2 Lite の `jp.` 推論プロファイルは APN1 の単価で課金される。
- `CfnVectorBucket` も `Tags.of()` でタグが付く。
- deploy の所要時間は1〜2分程度。
- ベクトルが入ったままのインデックスとバケットも `cdk destroy` で消える(インデックス削除のページの記述にもとづく。検証で確かめる)。
- 8件程度のデータでは、事前フィルタ(ENHANCED)と従来方式(CLASSIC)で結果は変わらない。
- 検証環境に `jq` がある。
