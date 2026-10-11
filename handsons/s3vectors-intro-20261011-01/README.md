# Amazon S3 Vectors に社内文書を登録し、検索結果を使って答える RAG を CLI で組む

<!-- job: s3vectors-intro-20261011-01 / iac: cdk / 検証リージョン: ap-northeast-1 -->

## このハンズオンで学べること

- Amazon S3 Vectors の「ベクトルバケット」と「ベクトルインデックス」の関係。インデックスの次元数・距離尺度・フィルタ対象外のメタデータキーは、作成後に変えられないこと
- 埋め込みモデルの出力次元とインデックスの次元数をそろえる必要があること(Amazon Titan Text Embeddings V2 の `dimensions: 256` と、インデックスの次元数 256)
- `put-vectors` で、ベクトルとメタデータ(フィルタに使う `category`、フィルタに使わない `source_text`)を登録する方法
- `query-vectors` の `--top-k`、`--return-distance`、`--return-metadata` の使い方と、cosine 距離の読み方(小さいほど近い)
- 検索拡張生成(Retrieval-Augmented Generation、RAG)の最小構成。検索で取り出した本文をプロンプトに入れると、モデルが知らない社内情報に答えられるようになること
- `--filter` によるメタデータフィルタで、検索対象を絞る方法

## 対象者と前提

- 対象者: AWS CLI を日常的に使い、RAG を言葉としては知っているが、ベクトルストアを自分で触ったことがない社内エンジニア
- 前提知識: AWS CLI の基本操作(`--query`、`--output`)、`npx cdk deploy` / `destroy` を実行したことがある程度の AWS CDK の知識、`jq` の基本
- 必要な環境:
  - AWS CLI v2(`aws --version` で `aws-cli/2.` と表示される)。`aws s3vectors` コマンドが入っている必要があります。入った最低バージョンは確認できていないため、しばらく更新していない場合は最新版に更新してから始めてください(このハンズオンの CLI の記述は、AWS CLI 2.37.12 のリファレンスで確認しています)。AWS CLI 2.33.6 で動作を確認しています。
  - `jq`(JSON の加工に使います。`jq --version` で `jq-1.6` 以上)
  - Node.js 22 以上(`node --version` で `v22.` 以上)
  - このディレクトリ(`handsons/s3vectors-intro-20261011-01/`)の `cdk/` と `data/`(AWS CDK は `npx` でプロジェクト内のバージョンを使います)
  - 対象のアカウント・リージョンで CDK のブートストラップが済んでいること(事前準備で確認します)
  - シェルは bash または zsh(手順中で `for`、`tee`、`$( )` を使います)
- AWSアカウント: 検証用アカウントのプロファイル。次の権限が必要です
  - CloudFormation スタックの作成・削除と、CDK ブートストラップのロールの引き受け(`sts:AssumeRole`)
  - S3 Vectors の操作(`s3vectors:PutVectors`、`QueryVectors`、`GetVectors`、`ListVectors`、`GetIndex`、`GetVectorBucket`、`ListVectorBuckets`、`ListTagsForResource`)
  - Amazon Bedrock のモデル呼び出し(`bedrock:InvokeModel`)と、モデル情報の参照(`bedrock:GetFoundationModel`)。対象は `amazon.titan-embed-text-v2:0` と `amazon.nova-lite-v1:0` の2つで、どちらも東京リージョン内で呼び出します

## 所要時間と想定コスト

- 所要時間: 約60分
- 想定コスト: 約 $0.16(USD、ap-northeast-1、所要時間ぶん。無料枠は考慮していません)。余裕分を除いた実質は約 $0.04 です

| リソース | 単価 | 本ハンズオンでの量 | 想定コスト |
| --- | --- | --- | --- |
| Titan Text Embeddings V2 入力 | $0.000029 / 1K トークン | 50,000 トークン(文書8件と質問。再実行を多めに見込んだ量) | $0.0015 |
| Amazon Nova Lite 入力 | $0.000072 / 1K トークン | 80,000 トークン(20回 × 約4,000) | $0.0058 |
| Amazon Nova Lite 出力 | $0.000288 / 1K トークン | 20,000 トークン(多めに見込んだ量) | $0.0058 |
| S3 Vectors PutVectors(登録したデータ量) | $0.219 / GB | 1 MB(実際は 8件 × 約3 KB) | $0.0002 |
| S3 Vectors ストレージ | $0.066 / GB-月 | 1 MB を1か月分(実際は1時間未満) | $0.0001 |
| S3 Vectors QueryVectors | $0.0027 / 1,000 リクエスト | 100 回 | $0.0003 |
| S3 Vectors その他の API(Get / List / Tag、CloudFormation による作成・削除) | $0.06 / 1,000 リクエスト | 500 回 | $0.0300 |
| S3 Vectors クエリの処理・返却データ量 | $0.000004278 / GB、$0.01 / GB | 1 GB、10 MB | $0.0001 |
| AWS CloudFormation(`AWS::*` リソースのみ) | 追加料金なし | 1スタック(デプロイ1回、削除1回) | $0.0000 |
| 余裕分(CDK アセットの S3 リクエスト) | — | — | $0.0100 |
| 余裕分(生成モデルを Amazon Nova 2 Lite に替えた場合の差額と再実行) | — | — | $0.1000 |
| 合計 | | | **$0.1537** |

- 単価は AWS Price List API(ap-northeast-1。S3 Vectors は 2026-09-01、Bedrock は 2026-10-01 時点)の値です。
- S3 Vectors と Bedrock のオンデマンド呼び出しには、時間課金や最低料金はありません。データ量・リクエスト数・トークン数に応じた従量課金だけです。
- 正確な料金は [Amazon S3 の料金](https://aws.amazon.com/s3/pricing/) と [Amazon Bedrock の料金](https://aws.amazon.com/bedrock/pricing/) で確認してください。

## 構成

CDK で S3 Vectors のベクトルバケットを1つと、その中にベクトルインデックスを1つ作ります。社内の架空サービスの FAQ 8件(`data/docs.jsonl`)を、Amazon Bedrock の Titan Text Embeddings V2 で256次元のベクトル(埋め込み)にし、AWS CLI でインデックスに登録します。質問文も同じモデルでベクトルにして類似検索し、見つかった文書の本文をプロンプトに入れて Amazon Nova Lite に回答させます。

```text
data/docs.jsonl --(bedrock-runtime invoke-model: Titan V2)--> 埋め込み(work/*.json)
埋め込み --(s3vectors put-vectors)--> ベクトルインデックス(ベクトルバケットの中)
質問文 --(invoke-model: Titan V2)--> 質問の埋め込み --(s3vectors query-vectors)--> 近い文書3件
近い文書3件 + 質問文 --(bedrock-runtime converse: Nova Lite)--> 回答
ターミナル(npx cdk) --deploy / destroy--> CloudFormation スタック --> ベクトルバケット / ベクトルインデックス
```

| リソース | 名前 | 作り方 |
| --- | --- | --- |
| S3 Vectors ベクトルバケット(暗号化は既定の SSE-S3) | `handson-${HANDSON_JOB_ID}-vectors` | IaC(CDK) |
| S3 Vectors ベクトルインデックス(float32、256次元、cosine) | `handson-${HANDSON_JOB_ID}-docs` | IaC(CDK) |
| ベクトル 8件 | key `doc-01` 〜 `doc-08` | CLI(`put-vectors`)。インデックスの中のデータで、インデックスと一緒に削除されます |
| CloudFormation スタック | `Handson-${HANDSON_JOB_ID}` | IaC(CDK) |

ベクトルバケットとインデックスには `handson-job-id` タグが付きます。個々のベクトルはタグを付ける対象ではありません。Bedrock 側で作るリソースはありません(モデルを呼び出すだけです)。CLI で作る AWS リソースもありません。

## 事前準備

### 1. 環境変数を設定する

以降の手順はすべて、このターミナルで実行します。この README があるディレクトリ(`handsons/s3vectors-intro-20261011-01/`)から始めてください。

```bash
export AWS_PROFILE=<使用するプロファイル名>
export AWS_REGION=ap-northeast-1
export HANDSON_JOB_ID=s3vectors-intro-20261011-01
export AWS_PAGER=""
export EMBED_DIM=256
```

`HANDSON_JOB_ID` は、作成するリソースの名前とタグ(`handson-job-id`)に使います。同じアカウントで他の人も同時に実施する場合は、バケット名が重ならないよう、英小文字・数字・ハイフンで40文字以内の別の値(例: `s3vectors-intro-yamada`)に変えてください。後片付けでの確認にも使うので、ターミナルを開き直した場合は再設定してください。

`AWS_PAGER=""` は、AWS CLI の出力がページャー(`less` など)で止まらないようにする設定です。`EMBED_DIM=256` は、埋め込みモデルに指定する出力次元です。CDK で作るインデックスの次元数(256)と同じ値にしてあります。変えないでください。

**確認ポイント**: 次のコマンドで、使用するアカウントIDが表示される。

```bash
aws sts get-caller-identity --query Account --output text
```

```text
123456789012
```

### 2. AWS CLI のバージョンを確認する

```bash
aws --version
```

**確認ポイント**: `aws-cli/2.` で始まるバージョンが表示される。

```text
aws-cli/2.37.12 Python/3.13.7 Darwin/25.5.0 source/arm64
```

### 3. S3 Vectors のコマンドが使えることを確認する

これから作るベクトルバケットと同じ名前で始まるバケットを一覧します。コマンドがあることと、まだバケットがないことを同時に確かめます。

```bash
aws s3vectors list-vector-buckets --prefix handson-${HANDSON_JOB_ID} --query 'length(vectorBuckets)'
```

**確認ポイント**: `0` と表示される。

```text
0
```

`aws: error: argument command: Invalid choice` と表示された場合は、AWS CLI が古く `s3vectors` コマンドがありません。AWS CLI v2 を最新版に更新してから、この手順をやり直してください。

### 4. jq を確認する

```bash
jq --version
```

**確認ポイント**: `jq-1.6` 以上のバージョンが表示される。

```text
jq-1.7.1
```

`command not found` と表示された場合は、`jq` をインストールしてください(macOS は Homebrew の `jq`、Amazon Linux は `sudo dnf install jq` など)。

### 5. 埋め込みモデルが使えることを確認する

Titan Text Embeddings V2 が、このリージョンで使える状態かを確認します。

```bash
aws bedrock get-foundation-model --model-identifier amazon.titan-embed-text-v2:0 --query 'modelDetails.modelLifecycle.status' --output text
```

**確認ポイント**: `ACTIVE` と表示される。

```text
ACTIVE
```

### 6. 生成モデルが使えることを確認する

Nova Lite が、このリージョンで使える状態かを確認します。

```bash
aws bedrock get-foundation-model --model-identifier amazon.nova-lite-v1:0 --query 'modelDetails.modelLifecycle.status' --output text
```

**確認ポイント**: `ACTIVE` と表示される。

```text
ACTIVE
```

`LEGACY` と表示された場合でも、このハンズオンは実施できます。トラブルシューティングの「Nova Lite が使えない」を参照してください。

### 7. `cdk/` に移動する

この README があるディレクトリ(`handsons/s3vectors-intro-20261011-01/`)で、`cdk/` に移動します。以降の手順はすべて `cdk/` で実行します。文書ファイルは `../data/docs.jsonl` として参照します。

```bash
cd cdk
```

**確認ポイント**: 次のコマンドで、`data/docs.jsonl` の行数 `8` が表示される。

```bash
wc -l < ../data/docs.jsonl
```

```text
       8
```

`no such file or directory` と表示された場合は、この README があるディレクトリにいるかを確かめてから、この手順をやり直してください。

### 8. 依存パッケージをインストールする

`cdk/package-lock.json` に固定されたバージョンの AWS CDK と依存パッケージを、`cdk/node_modules/` にインストールします。

```bash
npm ci
```

**確認ポイント**: 最後に `added <数> packages` を含む行が表示され、`npm error`(古い npm では `npm ERR!`)で終わっていない。

### 9. CDK のバージョンを確認する

```bash
npx cdk --version
```

**確認ポイント**: `2.1145.0` から始まるバージョンが表示される。

```text
2.1145.0 (build xxxxxxx)
```

### 10. CDK のブートストラップを確認する

```bash
aws cloudformation describe-stacks --stack-name CDKToolkit --query 'Stacks[0].StackStatus' --output text
```

**確認ポイント**: `CREATE_COMPLETE` または `UPDATE_COMPLETE` と表示される。

`Stack with id CDKToolkit does not exist` と表示された場合は、アカウントの管理者にブートストラップを依頼してください。ブートストラップで作られるリソースはアカウント共通のもので、このハンズオンの後片付けの対象外です。

### 11. 作業用のディレクトリを作る

埋め込み・検索結果・回答を保存するディレクトリ `cdk/work/` を作ります。埋め込みは256個の数値の並びで画面に出すと長いため、ファイルに保存して、画面には件数や key だけを表示します。

```bash
mkdir -p work
```

**確認ポイント**: 次のコマンドで `ok` と表示される。

```bash
test -d work && echo ok
```

```text
ok
```

## 手順

### 1. ベクトルバケットとインデックスを作成する

#### 手順1: CDK でベクトルバケットとインデックスをデプロイする

`cdk/lib/handson-stack.ts` に定義したベクトルバケットとベクトルインデックスを作成します。`-c jobId=...` で渡した値が、リソース名と `handson-job-id` タグに使われます。

```bash
npx cdk deploy -c jobId=${HANDSON_JOB_ID} --require-approval never
```

CDK は既定で、IAM の権限やセキュリティグループのルールを広げる変更があると、デプロイ前に承認の確認プロンプトを出します。`--require-approval never` は、この確認プロンプトを出さないオプションです。ハンズオンの手順を止めないために付けています(このスタックは IAM リソースもセキュリティグループも作りません)。完了まで数十秒〜3分かかります。

このスタックのデプロイは、このハンズオンでは1回だけです。設定を変えて再デプロイする手順はありません(インデックスの設定は作成後に変えられないため)。

**確認ポイント**: 最後に `✅  Handson-s3vectors-intro-20261011-01` と `Outputs:` が表示され、`VectorBucketName`、`VectorBucketArn`、`IndexName`、`IndexArn` の4つに値が入っている。

```text
 ✅  Handson-s3vectors-intro-20261011-01

Outputs:
Handson-s3vectors-intro-20261011-01.IndexArn = arn:aws:s3vectors:ap-northeast-1:123456789012:bucket/handson-s3vectors-intro-20261011-01-vectors/index/handson-s3vectors-intro-20261011-01-docs
Handson-s3vectors-intro-20261011-01.IndexName = handson-s3vectors-intro-20261011-01-docs
Handson-s3vectors-intro-20261011-01.VectorBucketArn = arn:aws:s3vectors:ap-northeast-1:123456789012:bucket/handson-s3vectors-intro-20261011-01-vectors
Handson-s3vectors-intro-20261011-01.VectorBucketName = handson-s3vectors-intro-20261011-01-vectors
```

#### 手順2: ベクトルバケット名を変数に入れる

以降の S3 Vectors の操作では、ベクトルバケット名とインデックス名を指定します。スタックの出力 `VectorBucketName` を変数 `VECTOR_BUCKET` に入れます。

```bash
VECTOR_BUCKET=$(aws cloudformation describe-stacks --stack-name Handson-${HANDSON_JOB_ID} --query "Stacks[0].Outputs[?OutputKey=='VectorBucketName'].OutputValue" --output text)
```

**確認ポイント**: 次のコマンドで `handson-s3vectors-intro-20261011-01-vectors` が表示される(`HANDSON_JOB_ID` を変えた場合は `handson-<その値>-vectors`)。

```bash
echo ${VECTOR_BUCKET}
```

```text
handson-s3vectors-intro-20261011-01-vectors
```

#### 手順3: インデックス名を変数に入れる

```bash
INDEX_NAME=$(aws cloudformation describe-stacks --stack-name Handson-${HANDSON_JOB_ID} --query "Stacks[0].Outputs[?OutputKey=='IndexName'].OutputValue" --output text)
```

**確認ポイント**: 次のコマンドで `handson-s3vectors-intro-20261011-01-docs` が表示される。

```bash
echo ${INDEX_NAME}
```

```text
handson-s3vectors-intro-20261011-01-docs
```

ターミナルを開き直した場合は、事前準備の手順1(環境変数)、事前準備の手順7(`cdk/` への移動)、手順2、手順3の順にやり直してください。手順17の `QUESTION` も同様に再設定が必要です。

#### 手順4: インデックスの設定を確認する

```bash
aws s3vectors get-index --vector-bucket-name "${VECTOR_BUCKET}" --index-name "${INDEX_NAME}" --query 'index.{dataType: dataType, dimension: dimension, distanceMetric: distanceMetric, nonFilterableMetadataKeys: metadataConfiguration.nonFilterableMetadataKeys}' --output json
```

**確認ポイント**: `dataType` が `"float32"`、`dimension` が `256`、`distanceMetric` が `"cosine"`、`nonFilterableMetadataKeys` が `["source_text"]` と表示される。

```json
{
    "dataType": "float32",
    "dimension": 256,
    "distanceMetric": "cosine",
    "nonFilterableMetadataKeys": [
        "source_text"
    ]
}
```

> **解説**: ベクトルインデックスは、同じ次元数のベクトルを集めて類似検索するための入れ物です。次元数(`dimension`)、距離尺度(`distanceMetric`)、フィルタに使わないメタデータキー(`nonFilterableMetadataKeys`)は作成後に変えられません。変えるにはインデックスを作り直します。`source_text` はフィルタに使わないキーとして宣言したので、検索結果として返すだけの長い本文を入れられます(フィルタ対象のメタデータは1ベクトルあたり2 KB まで、メタデータの合計は40 KB までです)。

#### 手順5: ベクトルバケットの ARN を変数に入れる

タグの確認では ARN を指定します。スタックの出力 `VectorBucketArn` を変数 `VECTOR_BUCKET_ARN` に入れます。

```bash
VECTOR_BUCKET_ARN=$(aws cloudformation describe-stacks --stack-name Handson-${HANDSON_JOB_ID} --query "Stacks[0].Outputs[?OutputKey=='VectorBucketArn'].OutputValue" --output text)
```

**確認ポイント**: 次のコマンドで、`arn:aws:s3vectors:ap-northeast-1:` で始まり `:bucket/handson-s3vectors-intro-20261011-01-vectors` で終わる ARN が表示される。

```bash
echo ${VECTOR_BUCKET_ARN}
```

```text
arn:aws:s3vectors:ap-northeast-1:123456789012:bucket/handson-s3vectors-intro-20261011-01-vectors
```

#### 手順6: ベクトルバケットのタグを確認する

```bash
aws s3vectors list-tags-for-resource --resource-arn "${VECTOR_BUCKET_ARN}" --query tags --output json
```

**確認ポイント**: `"handson-job-id": "s3vectors-intro-20261011-01"` が含まれている(`HANDSON_JOB_ID` を変えた場合はその値)。ほかのタグが含まれていてもかまいません。

```json
{
    "handson-job-id": "s3vectors-intro-20261011-01"
}
```

#### 手順7: インデックスの ARN を変数に入れる

```bash
INDEX_ARN=$(aws cloudformation describe-stacks --stack-name Handson-${HANDSON_JOB_ID} --query "Stacks[0].Outputs[?OutputKey=='IndexArn'].OutputValue" --output text)
```

**確認ポイント**: 次のコマンドで、`:bucket/handson-s3vectors-intro-20261011-01-vectors/index/handson-s3vectors-intro-20261011-01-docs` で終わる ARN が表示される。

```bash
echo ${INDEX_ARN}
```

```text
arn:aws:s3vectors:ap-northeast-1:123456789012:bucket/handson-s3vectors-intro-20261011-01-vectors/index/handson-s3vectors-intro-20261011-01-docs
```

#### 手順8: インデックスのタグを確認する

```bash
aws s3vectors list-tags-for-resource --resource-arn "${INDEX_ARN}" --query tags --output json
```

**確認ポイント**: `"handson-job-id": "s3vectors-intro-20261011-01"` が含まれている。ほかのタグが含まれていてもかまいません。

```json
{
    "handson-job-id": "s3vectors-intro-20261011-01"
}
```

### 2. 文書をベクトルにして登録する

#### 手順9: 登録する文書を確認する

`data/docs.jsonl` は、1行に1件の文書を JSON で書いたファイルです。`key`(ベクトルの名前)、`category`(分類)、`text`(本文)を持ちます。内容は架空の会社の社内 FAQ で、モデルが一般知識では答えられない値(締め切りの日時、内線番号など)を含めてあります。

```bash
jq -r '[.key, .category, .text] | @tsv' ../data/docs.jsonl
```

**確認ポイント**: 8行表示され、1列目が `doc-01` 〜 `doc-08`、2列目が `expense`(経費、3件)、`it`(IT、3件)、`facility`(施設、2件)のいずれかになっている。1行目の本文に `16時30分` が含まれている。

```text
doc-01	expense	社内経費システム「ハルニレ精算」での経費精算の申請締め切りは、毎月23日の16時30分です。締め切りを過ぎた申請は、翌月の処理に回ります。
doc-02	expense	出張の宿泊費は、1泊あたり東京都内で14,800円、それ以外の地域で11,600円が上限です。上限を超える場合は、事前に部長の承認を受けてください。
doc-03	expense	紙の領収書の原本は、申請から10営業日以内に、本社7階の経理部「青ポスト」に投函してください。電子領収書の場合は投函は不要です。
doc-04	it	社内ヘルプデスク「ツバメ窓口」の内線番号は4127です。受付時間は平日の9時から18時までです。
doc-05	it	社内システムのパスワードは90日ごとに変更が必要です。変更は社内ポータル「ミズナラ」の「アカウント設定」から行います。
doc-06	it	貸与PCの交換は、社内ポータル「ミズナラ」の「機器申請」から申し込みます。申し込みから受け取りまで、通常5営業日かかります。
doc-07	facility	本社の会議室「カエデ」と「クヌギ」は、利用日の14日前から予約できます。予約は社内ポータル「ミズナラ」の「施設予約」から行います。
doc-08	facility	本社の入館証をなくした場合は、総務部(内線3360)に連絡してください。再発行には手数料1,000円がかかります。
```

#### 手順10: 1件の文書を埋め込みにする

まず `doc-01` の本文1件を Titan Text Embeddings V2 に渡し、256次元の埋め込みをファイル `work/emb-doc-01.json` に保存します。

```bash
aws bedrock-runtime invoke-model --model-id amazon.titan-embed-text-v2:0 --cli-binary-format raw-in-base64-out --content-type application/json --accept application/json --body "$(jq -c --argjson d "${EMBED_DIM}" 'select(.key == "doc-01") | {inputText: .text, dimensions: $d, normalize: true}' ../data/docs.jsonl)" work/emb-doc-01.json
```

**確認ポイント**: `"contentType": "application/json"` を含む JSON が表示される。

```json
{
    "contentType": "application/json"
}
```

> **解説**: `--body` に渡しているのは、`jq` で組み立てた `{"inputText": "<本文>", "dimensions": 256, "normalize": true}` という JSON です。`dimensions` は出力するベクトルの次元数で、Titan V2 では 256 / 512 / 1024 から選べます。`normalize: true` はベクトルの長さを1にそろえる指定です。`--cli-binary-format raw-in-base64-out` は、`--body` に JSON をそのまま渡すための AWS CLI v2 のオプションです。最後の引数 `work/emb-doc-01.json` は、モデルの応答を書き出すファイルです。

#### 手順11: 埋め込みの次元数を確認する

```bash
jq '{dimension: (.embedding | length), inputTextTokenCount: .inputTextTokenCount}' work/emb-doc-01.json
```

**確認ポイント**: `dimension` が `256` と表示され、`inputTextTokenCount` に1以上の整数が表示される。

```json
{
  "dimension": 256,
  "inputTextTokenCount": 45
}
```

`inputTextTokenCount` は課金の対象になる入力トークン数です。値は上の例と異なることがあります。

#### 手順12: 8件すべての文書を埋め込みにする

`data/docs.jsonl` の8件を1件ずつ埋め込みにし、`work/emb-doc-01.json` 〜 `work/emb-doc-08.json` に保存します(`doc-01` は上書きされます)。

```bash
for KEY in $(jq -r .key ../data/docs.jsonl); do aws bedrock-runtime invoke-model --model-id amazon.titan-embed-text-v2:0 --cli-binary-format raw-in-base64-out --content-type application/json --accept application/json --body "$(jq -c --arg k "${KEY}" --argjson d "${EMBED_DIM}" 'select(.key == $k) | {inputText: .text, dimensions: $d, normalize: true}' ../data/docs.jsonl)" "work/emb-${KEY}.json" > /dev/null; echo "embedded: ${KEY}"; done
```

**確認ポイント**: `embedded: doc-01` 〜 `embedded: doc-08` の8行が表示され、エラー(`An error occurred` など)が表示されない。

```text
embedded: doc-01
embedded: doc-02
embedded: doc-03
embedded: doc-04
embedded: doc-05
embedded: doc-06
embedded: doc-07
embedded: doc-08
```

次のコマンドで、8つのファイルすべての次元数が `256` であることも確認します。

```bash
jq -r '[input_filename, (.embedding | length)] | @tsv' work/emb-doc-*.json
```

```text
work/emb-doc-01.json	256
work/emb-doc-02.json	256
work/emb-doc-03.json	256
work/emb-doc-04.json	256
work/emb-doc-05.json	256
work/emb-doc-06.json	256
work/emb-doc-07.json	256
work/emb-doc-08.json	256
```

#### 手順13: ベクトルをインデックスに登録する

8件の埋め込みを、メタデータと一緒に `put-vectors` で1件ずつ登録します。メタデータには、フィルタに使う `category` と、検索結果として返す本文 `source_text` を入れます。

```bash
for KEY in $(jq -r .key ../data/docs.jsonl); do aws s3vectors put-vectors --vector-bucket-name "${VECTOR_BUCKET}" --index-name "${INDEX_NAME}" --vectors "$(jq -c --arg k "${KEY}" --slurpfile e "work/emb-${KEY}.json" 'select(.key == $k) | [{key: .key, data: {float32: $e[0].embedding}, metadata: {category: .category, source_text: .text}}]' ../data/docs.jsonl)"; echo "put: ${KEY}"; done
```

**確認ポイント**: `put: doc-01` 〜 `put: doc-08` の8行が表示され、エラー(`An error occurred` など)が表示されない。

```text
put: doc-01
put: doc-02
put: doc-03
put: doc-04
put: doc-05
put: doc-06
put: doc-07
put: doc-08
```

> **解説**: `--vectors` に渡しているのは、`[{"key": "doc-01", "data": {"float32": [256個の数値]}, "metadata": {"category": "expense", "source_text": "<本文>"}}]` という形の JSON です。1回の `put-vectors` で500件まで登録できますが、ここではコマンドラインを短く保つため1件ずつ登録しています。同じ key で登録し直すと上書きになります。

#### 手順14: 登録した件数を確認する

```bash
aws s3vectors list-vectors --vector-bucket-name "${VECTOR_BUCKET}" --index-name "${INDEX_NAME}" --query 'length(vectors)'
```

**確認ポイント**: `8` と表示される。

```text
8
```

#### 手順15: 登録したメタデータを確認する

```bash
aws s3vectors get-vectors --vector-bucket-name "${VECTOR_BUCKET}" --index-name "${INDEX_NAME}" --keys doc-01 --return-metadata --query 'vectors[0].metadata' --output json
```

**確認ポイント**: `category` が `"expense"` で、`source_text` に `doc-01` の本文(`16時30分` を含む文)が表示される。

```json
{
    "category": "expense",
    "source_text": "社内経費システム「ハルニレ精算」での経費精算の申請締め切りは、毎月23日の16時30分です。締め切りを過ぎた申請は、翌月の処理に回ります。"
}
```

### 3. 質問に近い文書を検索する

#### 手順16: ベクトルの数値を表示せずにキーだけ一覧する

登録したベクトルの key を一覧します。`list-vectors` は既定ではベクトルの数値を返しません。

```bash
aws s3vectors list-vectors --vector-bucket-name "${VECTOR_BUCKET}" --index-name "${INDEX_NAME}" --query 'sort(vectors[].key)' --output text
```

**確認ポイント**: `doc-01` 〜 `doc-08` の8つの key が1行に表示される。

```text
doc-01	doc-02	doc-03	doc-04	doc-05	doc-06	doc-07	doc-08
```

#### 手順17: 質問文を変数に入れる

以降の検索と回答で使う質問文を、変数 `QUESTION` に入れます。

```bash
QUESTION="ハルニレ精算での経費精算の申請締め切りはいつですか?"
```

**確認ポイント**: 次のコマンドで、質問文が表示される。

```bash
echo "${QUESTION}"
```

```text
ハルニレ精算での経費精算の申請締め切りはいつですか?
```

#### 手順18: 質問文を埋め込みにする

質問文を、文書と**同じモデル・同じ次元数**で埋め込みにし、`work/emb-query.json` に保存します。

```bash
aws bedrock-runtime invoke-model --model-id amazon.titan-embed-text-v2:0 --cli-binary-format raw-in-base64-out --content-type application/json --accept application/json --body "$(jq -nc --arg t "${QUESTION}" --argjson d "${EMBED_DIM}" '{inputText: $t, dimensions: $d, normalize: true}')" work/emb-query.json
```

**確認ポイント**: `"contentType": "application/json"` を含む JSON が表示され、次のコマンドで `256` と表示される。

```bash
jq '.embedding | length' work/emb-query.json
```

```text
256
```

> **解説**: 類似検索は、質問のベクトルと文書のベクトルの距離を比べる処理です。別のモデルや別の次元数で作ったベクトルどうしは、同じ「座標系」にないため比べられません。次元数が違えば `query-vectors` がエラーになり、次元数が同じでもモデルが違えば、エラーにならずに無関係な文書が返ります。そのため、登録と検索で必ず同じモデルと同じ `dimensions` を使います。

#### 手順19: 質問に近い文書を3件検索する

質問のベクトルで `query-vectors` を実行し、近い順に3件の key・距離・メタデータを `work/query-result.json` に保存します。

```bash
aws s3vectors query-vectors --vector-bucket-name "${VECTOR_BUCKET}" --index-name "${INDEX_NAME}" --query-vector "$(jq -c '{float32: .embedding}' work/emb-query.json)" --top-k 3 --return-distance --return-metadata --output json > work/query-result.json
```

**確認ポイント**: 次のコマンドで3行表示され、1行目の key が `doc-01`、カテゴリが `expense` になっている。2列目の距離が、上の行から下の行へ大きくなっている(同じ値でもかまいません)。

```bash
jq -r '.vectors[] | [.key, (.distance | tostring), .metadata.category] | @tsv' work/query-result.json
```

出力の例です。2行目と3行目の key と、距離の値は異なることがあります。距離は小数点以下が長く表示されます。

```text
doc-01	0.045043349266052246	expense
doc-07	0.7469358444213867	facility
doc-03	0.7602174878120422	expense
```

> **解説**: オプションの意味は次のとおりです。
> - `--query-vector`: 検索に使うベクトル。`{"float32": [256個の数値]}` の形で渡します。
> - `--top-k 3`: 近い順に返す件数。
> - `--return-distance`: 各結果の距離を返します。cosine 距離は「1 − コサイン類似度」で、0 に近いほど質問と近い文書です。
> - `--return-metadata`: 各結果のメタデータ(`category` と `source_text`)を返します。この指定や `--filter` を使うには、`s3vectors:QueryVectors` に加えて `s3vectors:GetVectors` 権限が必要です。

### 4. 検索結果を使って回答させる(RAG)

#### 手順20: 検索結果を渡さずに質問する

比較のため、まず検索結果を渡さずに、質問文だけを Nova Lite に送ります。回答を画面に表示し、`work/answer-norag.txt` にも保存します。

```bash
aws bedrock-runtime converse --model-id amazon.nova-lite-v1:0 --messages "$(jq -nc --arg q "${QUESTION}" '[{role: "user", content: [{text: $q}]}]')" --inference-config '{"maxTokens": 512, "temperature": 0}' --query 'output.message.content[0].text' --output text | tee work/answer-norag.txt
```

**確認ポイント**: 回答の文章が表示される。「ハルニレ精算」の締め切りを知らない、または一般的な説明にとどまる内容になる。次のコマンドで `false` と表示される(回答に `16時30分`、`16:30`、`16時半` のどれも含まれていない)。

```bash
jq -R -s 'test("16時30分|16:30|16時半")' work/answer-norag.txt
```

```text
false
```

回答の文章は実行ごとに変わることがあります。判定はこのコマンドの結果だけで行ってください。

> **解説**: `converse` は、Bedrock のモデルに会話形式でメッセージを送る API です。`--messages` に `[{"role": "user", "content": [{"text": "<質問>"}]}]` を渡しています。`temperature: 0` は、回答のばらつきを小さくする指定です。`maxTokens: 512` は回答の長さ(出力トークン数)の上限で、費用の上限にもなります。

#### 手順21: 検索結果を参考情報として渡して質問する

手順19で取り出した3件の本文(`source_text`)を「参考情報」としてプロンプトに入れ、同じ質問を送ります。回答は `work/answer-rag.txt` にも保存します。

```bash
aws bedrock-runtime converse --model-id amazon.nova-lite-v1:0 --system '[{"text": "あなたは社内ヘルプデスクのアシスタントです。ユーザーのメッセージにある参考情報だけを根拠に、日本語で簡潔に答えてください。参考情報に答えがない場合は、わからないと答えてください。"}]' --messages "$(jq -c --arg q "${QUESTION}" '[{role: "user", content: [{text: ("参考情報:\n" + ([.vectors[].metadata.source_text] | join("\n")) + "\n\n質問: " + $q)}]}]' work/query-result.json)" --inference-config '{"maxTokens": 512, "temperature": 0}' --query 'output.message.content[0].text' --output text | tee work/answer-rag.txt
```

**確認ポイント**: 毎月23日の16時30分が締め切りであることを述べた回答が表示される。次のコマンドで `true` と表示される(回答に `16時30分`、`16:30`、`16時半` のどれかが含まれている)。

```bash
jq -R -s 'test("16時30分|16:30|16時半")' work/answer-rag.txt
```

```text
true
```

回答の例です。文章は実行ごとに変わることがあります。

```text
ハルニレ精算での経費精算の申請締め切りは、毎月23日の16時30分です。締め切りを過ぎた申請は翌月の処理になります。
```

> **解説**: これが RAG の最小構成です。モデル自身は架空の社内情報を知りませんが、検索で見つけた本文をプロンプトに入れることで、その内容にもとづいて答えられるようになります。`--system` には、参考情報だけを根拠にするよう指示するシステムプロンプトを渡しています。社内の文書を増やしても、モデルを学習し直す必要はありません。インデックスにベクトルを追加するだけで、検索の対象になります。

### 5. 検索の条件を変えて結果を比べる

インデックスの設定は作成後に変えられないため、この章では検索(クエリ)側のオプションを変えて、結果の違いを確かめます。手順18の質問のベクトル(`work/emb-query.json`)を使い続けます。

#### 手順22: 返す件数を1件にする

```bash
aws s3vectors query-vectors --vector-bucket-name "${VECTOR_BUCKET}" --index-name "${INDEX_NAME}" --query-vector "$(jq -c '{float32: .embedding}' work/emb-query.json)" --top-k 1 --query 'vectors[].key' --output text
```

**確認ポイント**: `doc-01` の1件だけが表示される。

```text
doc-01
```

#### 手順23: 返す件数を5件にする

```bash
aws s3vectors query-vectors --vector-bucket-name "${VECTOR_BUCKET}" --index-name "${INDEX_NAME}" --query-vector "$(jq -c '{float32: .embedding}' work/emb-query.json)" --top-k 5 --return-metadata --query 'vectors[].[key, metadata.category]' --output text
```

**確認ポイント**: 5行表示され、1行目が `doc-01	expense` になっている。`expense` は3件しかないため、`it` か `facility` の行が2行以上含まれる。

出力の例です。2行目以降の順番は異なることがあります。

```text
doc-01	expense
doc-03	expense
doc-02	expense
doc-06	it
doc-07	facility
```

#### 手順24: カテゴリ `expense` に絞って検索する

`--filter` で、メタデータ `category` が `expense` のベクトルだけを検索対象にします。`--top-k` は手順23と同じ5件です。

```bash
aws s3vectors query-vectors --vector-bucket-name "${VECTOR_BUCKET}" --index-name "${INDEX_NAME}" --query-vector "$(jq -c '{float32: .embedding}' work/emb-query.json)" --top-k 5 --filter '{"category": {"$eq": "expense"}}' --return-metadata --query 'vectors[].[key, metadata.category]' --output text
```

**確認ポイント**: 3行だけ表示され、2列目がすべて `expense` になっている(`doc-01`、`doc-02`、`doc-03`)。`--top-k 5` でも、条件に合うベクトルが3件しかないため3件になる。

```text
doc-01	expense
doc-03	expense
doc-02	expense
```

#### 手順25: カテゴリ `it` に絞って検索する

同じ質問のまま、別のカテゴリ `it` に絞ります。

```bash
aws s3vectors query-vectors --vector-bucket-name "${VECTOR_BUCKET}" --index-name "${INDEX_NAME}" --query-vector "$(jq -c '{float32: .embedding}' work/emb-query.json)" --top-k 5 --filter '{"category": {"$eq": "it"}}' --return-metadata --query 'vectors[].[key, metadata.category]' --output text
```

**確認ポイント**: 3行だけ表示され、2列目がすべて `it` になっている(`doc-04`、`doc-05`、`doc-06` の順不同)。手順22〜24で1位だった `doc-01` は含まれない。

出力の例です。順番は異なることがあります。

```text
doc-06	it
doc-05	it
doc-04	it
```

> **解説**: メタデータフィルタは、類似度に関係なく、条件に合わないベクトルを結果から除きます。部署ごとの文書だけを検索したい場合や、公開範囲で絞りたい場合に使います。条件には `$eq` のほかに `$ne`、`$in`、`$gt` などの演算子を使えます。フィルタに使えるのは、インデックス作成時に `nonFilterableMetadataKeys` に入れなかったキー(このハンズオンでは `category`)だけです。

## 後片付け

作成と逆の順番で削除します。登録したベクトルは、インデックスと一緒に削除されます。

### 作業用のファイルを削除する

`cdk/work/` に保存した埋め込み・検索結果・回答のファイルを削除します。AWS のリソースではありません。

```bash
rm -rf work
```

**確認ポイント**: 次のコマンドで `removed` と表示される。

```bash
test -d work && echo remaining || echo removed
```

```text
removed
```

### CDK で作成したリソースを削除する

`cdk/` ディレクトリで実行します。`--force` は削除の確認プロンプトを出さないオプションです。インデックスが先に、ベクトルバケットが後に削除されます。完了まで1〜3分かかります。

```bash
npx cdk destroy -c jobId=${HANDSON_JOB_ID} --force
```

**確認ポイント**: `✅  Handson-s3vectors-intro-20261011-01: destroyed` と表示される。

```bash
aws cloudformation describe-stacks --stack-name Handson-${HANDSON_JOB_ID}
```

**確認ポイント**: `Stack with id Handson-s3vectors-intro-20261011-01 does not exist` というエラーになる。

### ベクトルバケットが一覧に残っていないことを確認する

S3 Vectors のバケットは、CloudFormation の状態とは別に、S3 Vectors の API で直接確かめます。

```bash
aws s3vectors list-vector-buckets --prefix handson-${HANDSON_JOB_ID} --query 'length(vectorBuckets)'
```

**確認ポイント**: `0` と表示される。

```text
0
```

### ベクトルバケットが存在しないことを確認する

```bash
aws s3vectors get-vector-bucket --vector-bucket-name handson-${HANDSON_JOB_ID}-vectors
```

**確認ポイント**: `NotFoundException` を含むエラーになる。

```text
An error occurred (NotFoundException) when calling the GetVectorBucket operation: ...
```

バケットの情報が表示された場合は、削除に失敗しています。トラブルシューティングの「`cdk destroy` が `DELETE_FAILED` になる」を参照してください。

### 残っていないことを確認する

```bash
aws resourcegroupstaggingapi get-resources \
  --tag-filters "Key=handson-job-id,Values=${HANDSON_JOB_ID}" \
  --query 'ResourceTagMappingList[].ResourceARN' --output text
```

**確認ポイント**: 何も表示されない。削除直後は数分間表示が残ることがあるため、表示された場合は5分ほど待って再実行してください。表示が残る場合でも、前の2つの手順で `list-vector-buckets` が `0`、`get-vector-bucket` が `NotFoundException` になっていれば、ベクトルバケットとインデックスは実際には削除されています。

S3 Vectors のリソースが、このタグ検索(Resource Groups Tagging API)に表示されるかは確認できていません。そのため、上の2つの手順の S3 Vectors 専用の確認を必ず行ってください。このハンズオンでは、タグで検索できないほかのリソース(自動作成されるロググループ、IAM ロールなど)は作りません。CDK のブートストラップで作られたリソース(`CDKToolkit` スタック)はアカウント共通のため、削除しないでください。

このリポジトリで作業している場合は、リポジトリのルートにある棚卸しスクリプトでも確認できます(`cdk/` から実行する場合のパスです)。4つの節(タグ付きリソース / CloudFormation スタック / IAM ロール / S3 Vectors のベクトルバケットとインデックス)がすべて空であれば完了です。

```bash
../../../scripts/list-tagged.sh ${HANDSON_JOB_ID} ${AWS_PROFILE} ${AWS_REGION}
```

Bedrock のモデル呼び出しログをアカウントで有効にしている場合、このハンズオンの呼び出しも既存の送り先(CloudWatch Logs や S3)に記録されます。アカウント共通の設定のため、このハンズオンでは変更も削除もしません。

## トラブルシューティング

| 症状 | 原因 | 対処 |
| --- | --- | --- |
| `aws: error: argument command: Invalid choice` と表示され、`s3vectors` が使えない | AWS CLI が古い、または v1 | AWS CLI v2 を最新版に更新し、事前準備の手順2からやり直す |
| `jq: command not found` と表示される | `jq` が入っていない | `jq` をインストールし、事前準備の手順4からやり直す |
| `npx cdk deploy` で `-c jobId=<英小文字・数字・ハイフン、40文字以内> を指定してください` と表示される | `HANDSON_JOB_ID` が未設定か、大文字などを含んでいる | 事前準備の手順1で `HANDSON_JOB_ID` を設定し直す |
| `npx cdk deploy` で `has not been bootstrapped` や `SSM parameter /cdk-bootstrap/... not found` と表示される | 対象のアカウント・リージョンで CDK のブートストラップがされていない | 管理者にブートストラップを依頼する(ハンズオンでは行わない) |
| `npx cdk deploy` でベクトルバケットの作成が `already exists` で失敗する | 同じ名前のベクトルバケットが残っている(前回の後片付けが途中など) | 後片付けの手順で前回のスタックを削除してから再実行する。他の人と重なっている場合は `HANDSON_JOB_ID` を別の値にする |
| `invoke-model` や `converse` で `AccessDeniedException` になる | プロファイルに `bedrock:InvokeModel` 権限がない、または SCP などでモデルの利用が制限されている | 管理者に、`amazon.titan-embed-text-v2:0` と `amazon.nova-lite-v1:0` を東京リージョンで呼び出す権限を依頼する |
| `invoke-model` で `Invalid base64` などのエラーになる | `--cli-binary-format raw-in-base64-out` を付け忘れた | 本文のコマンドをそのまま実行し直す |
| `put-vectors` で `ValidationException`(次元数が合わない)になる | `EMBED_DIM` が 256 以外になっている、またはターミナルを開き直して `EMBED_DIM` が空になった | 事前準備の手順1で `EMBED_DIM=256` を設定し直し、手順12から再実行する |
| `put-vectors` や `query-vectors` で `--vector-bucket-name` の値がないというエラーになる | ターミナルを開き直して `VECTOR_BUCKET` や `INDEX_NAME` が空になっている | 事前準備の手順1、事前準備の手順7、手順2、手順3の順にやり直す(手順19以降なら手順17も) |
| `query-vectors` で `403`(`AccessDeniedException`)になる | `--return-metadata` や `--filter` には `s3vectors:GetVectors` 権限も必要 | プロファイルに `s3vectors:GetVectors` 権限を追加してもらう |
| 手順14で `8` より小さい値が表示される | 手順13の一部の登録が失敗した | 手順13の出力でエラーの出た key を確認し、手順13を再実行する(同じ key は上書きされる) |
| 手順19の1位が `doc-01` にならない | 質問と文書を別のモデル・別の次元で埋め込んだ、または `QUESTION` が空のまま埋め込んだ | `echo "${QUESTION}"` で質問文を確認し、手順17から再実行する |
| 手順21で `true` にならない | 検索結果に `doc-01` が含まれていない、または生成のばらつき | 手順19の確認コマンドで1行目が `doc-01` かを確認し、手順21を再実行する |
| Nova Lite が使えない(`LEGACY` と表示される、または `ResourceNotFoundException` / `ValidationException` になる) | モデルのライフサイクルが変わった | 後継の Amazon Nova 2 Lite を、日本国内の推論プロファイル `jp.amazon.nova-2-lite-v1:0` で呼び出す(`--model-id` を置き換える)。東京では Nova 2 Lite をリージョン内で直接は呼べず、推論プロファイルと、送信先の東京・大阪リージョンでの呼び出し権限が必要。費用は1回あたり約 $0.09 増える |
| `npx cdk destroy` が `DELETE_FAILED` になる(ベクトルバケットが空でない) | インデックスの削除が終わる前にバケットを削除しようとした | 次のコマンドでインデックスを削除してから、`npx cdk destroy -c jobId=${HANDSON_JOB_ID} --force` を再実行する: `aws s3vectors delete-index --vector-bucket-name handson-${HANDSON_JOB_ID}-vectors --index-name handson-${HANDSON_JOB_ID}-docs` |

## 参考

- [Amazon S3 Vectors のリージョンとクォータ](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-regions-quotas.html)
- [Amazon S3 Vectors の制限](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-limitations.html)
- [ベクトルインデックスの作成](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-create-index.html)
- [ベクトルインデックスの削除](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-index-delete.html)
- [ベクトルバケットの削除](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-buckets-delete.html)
- [ベクトルバケットのタグ](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-tags.html)
- [AWS CLI s3vectors query-vectors](https://docs.aws.amazon.com/cli/latest/reference/s3vectors/query-vectors.html)
- [QueryVectors API](https://docs.aws.amazon.com/AmazonS3/latest/API/API_S3VectorBuckets_QueryVectors.html)
- [AWS::S3Vectors::VectorBucket](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-s3vectors-vectorbucket.html)
- [AWS::S3Vectors::Index](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-s3vectors-index.html)
- [AWS CDK aws_s3vectors モジュール](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_s3vectors-readme.html)
- [Amazon Titan Text Embeddings V2 のパラメータ](https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-titan-embed-text.html)
- [Amazon Titan Text Embeddings V2 のモデルカード](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-titan-text-embeddings-v2.html)
- [Amazon Nova Lite のモデルカード](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-lite.html)
- [Amazon Nova 2 Lite のモデルカード](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-2-lite.html)
- [Amazon Bedrock のモデルアクセス](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html)
- [Amazon S3 Vectors の一般提供(What's New、2025-12)](https://aws.amazon.com/about-aws/whats-new/2025/12/amazon-s3-vectors-generally-available/)

## 付録: CDK コードの説明

| ファイル | 内容 |
| --- | --- |
| `cdk/bin/app.ts` | アプリのエントリーポイント。`jobId` を受け取り、全リソースに `handson-job-id` タグを付ける |
| `cdk/lib/handson-stack.ts` | ベクトルバケット、ベクトルインデックスと、出力(`VectorBucketName` / `VectorBucketArn` / `IndexName` / `IndexArn`)の定義 |
| `cdk/lib/destroy-aspect.ts` | 全リソースの削除ポリシーを `DESTROY` にする(後片付けで残さないため) |

S3 Vectors には L2 コンストラクトがないため、L1 の `CfnVectorBucket` と `CfnIndex` を使います(`cdk/lib/handson-stack.ts` の抜粋)。

```typescript
const EMBEDDING_DIMENSION = 256;

const bucket = new s3vectors.CfnVectorBucket(this, 'VectorBucket', {
  vectorBucketName: `handson-${props.jobId}-vectors`,
});
bucket.applyRemovalPolicy(cdk.RemovalPolicy.DESTROY);

const index = new s3vectors.CfnIndex(this, 'Index', {
  vectorBucketArn: bucket.attrVectorBucketArn,
  indexName: `handson-${props.jobId}-docs`,
  dataType: 'float32',
  dimension: EMBEDDING_DIMENSION,
  distanceMetric: 'cosine',
  metadataConfiguration: {
    nonFilterableMetadataKeys: ['source_text'],
  },
});
index.applyRemovalPolicy(cdk.RemovalPolicy.DESTROY);
```

- `vectorBucketArn: bucket.attrVectorBucketArn`: インデックスからバケットを、名前の文字列ではなく ARN の属性(`Fn::GetAtt`)で参照します。これで CloudFormation に「インデックスはバケットに依存する」という関係ができ、作成はバケット → インデックス、削除はインデックス → バケットの順になります。名前の文字列で参照すると依存関係ができず、インデックスが残ったままバケットを削除しようとして失敗することがあります。
- `dimension: EMBEDDING_DIMENSION`: 256 です。本文の `EMBED_DIM=256`(Titan V2 の `dimensions`)と必ず同じ値にします。インデックスの次元数は作成後に変えられません。
- `distanceMetric: 'cosine'`: cosine 距離で検索します。もう1つの選択肢は `euclidean` です。
- `nonFilterableMetadataKeys: ['source_text']`: 本文はフィルタに使わないキーにします。フィルタ対象のメタデータには1ベクトルあたり2 KB の上限があるため、長い本文はこちらに入れます。
- 暗号化(`encryptionConfiguration`)は指定せず、既定の SSE-S3 を使います。AWS KMS のキーを作らないため、削除待機期間のあるリソースが残りません。
- `applyRemovalPolicy(DESTROY)`: `cdk destroy` でバケットとインデックスを削除します。`DestroyAspect` でもスタック内の全リソースに同じ設定をしています。中のベクトルは、インデックスの削除で一緒に消えます。
