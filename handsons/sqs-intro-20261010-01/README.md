# Amazon SQS の標準キューでメッセージを送受信し、可視性タイムアウトを確かめる

<!-- job: sqs-intro-20261010-01 / iac: cdk / 検証リージョン: ap-northeast-1 -->

## このハンズオンで学べること

- Amazon Simple Queue Service (Amazon SQS) の標準キューで、メッセージの送信(SendMessage)・受信(ReceiveMessage)・削除(DeleteMessage)を行う方法と、削除に使う受信ハンドル(ReceiptHandle)の役割
- 「受信」と「削除」が別の操作であること。受信しただけではメッセージは消えず、一定時間見えなくなるだけであること
- 可視性タイムアウトの挙動。期限までは再受信できず、期限後は `ApproximateReceiveCount` が増えて再び受信できること
- キュー属性(`ApproximateNumberOfMessages` / `ApproximateNumberOfMessagesNotVisible`)で、キューの状態を CLI から読み取る方法
- ショートポーリングでは空の応答が返りうること、`--wait-time-seconds`(ロングポーリング)で受信が安定すること

## 対象者と前提

- 対象者: AWS CLI を日常的に使うが、SQS を触ったことがない社内エンジニア
- 前提知識: AWS CLI の基本操作(`--query`、`--output`)、`npx cdk deploy` / `destroy` を実行したことがある程度の AWS CDK の知識
- 必要な環境:
  - AWS CLI v2(`aws --version` で `aws-cli/2.` と表示される)。手順13・14・17・22・24・28 では、`aws sqs receive-message` の `--message-system-attribute-names` オプションを使います。このオプションは、非推奨になった `--attribute-names` の後継として追加されたもので、古い v2 にはありません。使えるようになった最低バージョンは確認できていないため、しばらく更新していない場合は、最新版に更新してから始めてください
  - Node.js 22 以上(`node --version` で `v22.` 以上)
  - このディレクトリ(`handsons/sqs-intro-20261010-01/`)の `cdk/` ディレクトリ(AWS CDK は `npx` でプロジェクト内のバージョンを使います)
  - 対象のアカウント・リージョンで CDK のブートストラップが済んでいること(事前準備で確認します)
  - シェルは bash または zsh(手順中で `for`、`while read`、`tee`、`cut`、`wc` を使います)
- AWSアカウント: 検証用アカウントのプロファイル。CloudFormation スタックの作成・更新・削除、SQS キューの作成・削除とメッセージ操作、CDK ブートストラップのロールの引き受け(`sts:AssumeRole`)ができる権限

## 所要時間と想定コスト

- 所要時間: 約60分
- 想定コスト: 約 $0.01(USD、ap-northeast-1、所要時間ぶん。無料枠は考慮していません)

| リソース | 単価 | 本ハンズオンでの量 | 想定コスト |
| --- | --- | --- | --- |
| SQS 標準キュー リクエスト | $0.40 / 100万リクエスト | 約500リクエスト(CLI 操作、CloudFormation による作成・更新・削除、空の受信を多めに見込んだ量) | $0.0002 |
| AWS CloudFormation(`AWS::*` リソースのみ) | 追加料金なし | 1スタック(デプロイ2回、削除1回) | $0.0000 |
| 余裕分(リージョン別単価の差、CDK アセットの S3 リクエスト) | — | — | $0.0100 |
| 合計 | | | **$0.0102** |

- SQS はリクエスト単位の課金だけで、時間課金や最低料金はありません。キューを置いておくだけでは料金はかかりません。
- メッセージが返らなかった受信(空の応答)も1リクエストとして課金されます。
- 上の SQS 単価は AWS 公式ブログに記載された値で、ap-northeast-1 の単価としては確認できていません。差があっても金額が小さいため、余裕分で見込んでいます。正確な単価は [Amazon SQS の料金](https://aws.amazon.com/sqs/pricing/) で確認してください。

## 構成

CDK で SQS の標準キューを1つ作り、そのキューに対して AWS CLI でメッセージを送信・受信・削除します。可視性タイムアウトは、最初は既定値の30秒で作り、途中で CDK から10秒に変更します。キューは SQS 管理キーによるサーバー側暗号化(SSE-SQS)を使い、AWS KMS のキーは作りません。

```text
ターミナル(AWS CLI) --send-message / receive-message / delete-message--> SQS 標準キュー
ターミナル(npx cdk)  --deploy / destroy--> CloudFormation スタック --> SQS 標準キュー
```

| リソース | 名前 | 作り方 |
| --- | --- | --- |
| SQS 標準キュー | `handson-${HANDSON_JOB_ID}-queue` | IaC(CDK) |
| CloudFormation スタック | `Handson-${HANDSON_JOB_ID}` | IaC(CDK) |

CLI で作るリソースはありません。CLI で行うのはメッセージの操作と状態の確認だけです。すべてのリソースに `handson-job-id` タグが付きます。

## 事前準備

### 1. 環境変数を設定する

以降の手順はすべて、このターミナルで実行します。

```bash
export AWS_PROFILE=<使用するプロファイル名>
export AWS_REGION=ap-northeast-1
export HANDSON_JOB_ID=sqs-intro-20261010-01
export AWS_PAGER=""
```

`HANDSON_JOB_ID` は、作成するリソースの名前とタグ(`handson-job-id`)に使います。同じアカウントで他の人も同時に実施する場合は、キュー名が重ならないよう、英小文字・数字・ハイフンで別の値(例: `sqs-intro-yamada`)に変えてください。後片付けでの確認にも使うので、ターミナルを開き直した場合は再設定してください。

`AWS_PAGER=""` は、AWS CLI の出力がページャー(`less` など)で止まらないようにする設定です。

**確認ポイント**: 次のコマンドで、使用するアカウントIDが表示される。

```bash
aws sts get-caller-identity --query Account --output text
```

```text
123456789012
```

### 2. `cdk/` に移動する

この README があるディレクトリ(`handsons/sqs-intro-20261010-01/`)で、`cdk/` に移動します。以降の手順はすべて `cdk/` で実行します。

```bash
cd cdk
```

**確認ポイント**: `no such file or directory` などのエラーが表示されずにプロンプトに戻る。エラーになった場合は、この README があるディレクトリにいるかを確かめてから再実行してください。

### 3. 依存パッケージをインストールする

`cdk/package-lock.json` に固定されたバージョンの AWS CDK と依存パッケージを、`cdk/node_modules/` にインストールします。

```bash
npm ci
```

**確認ポイント**: 最後に `added <数> packages` を含む行が表示され、`npm error`(古い npm では `npm ERR!`)で終わっていない。

### 4. CDK のバージョンを確認する

```bash
npx cdk --version
```

**確認ポイント**: `2.1145.0` から始まるバージョンが表示される。

```text
2.1145.0 (build xxxxxxx)
```

### 5. CDK のブートストラップを確認する

```bash
aws cloudformation describe-stacks --stack-name CDKToolkit --query 'Stacks[0].StackStatus' --output text
```

**確認ポイント**: `CREATE_COMPLETE` または `UPDATE_COMPLETE` と表示される。

`Stack with id CDKToolkit does not exist` と表示された場合は、アカウントの管理者にブートストラップを依頼してください。ブートストラップで作られるリソースはアカウント共通のもので、このハンズオンの後片付けの対象外です。

## 手順

### 1. キューを作成する

#### 手順1: CDK でキューをデプロイする

`cdk/lib/handson-stack.ts` に定義した SQS 標準キューを作成します。`-c jobId=...` で渡した値が、キュー名と `handson-job-id` タグに使われます。

```bash
npx cdk deploy -c jobId=${HANDSON_JOB_ID} --require-approval never
```

CDK は既定で、IAM の権限やセキュリティグループのルールを広げる変更があると、デプロイ前に承認の確認プロンプトを出します。`--require-approval never` は、この確認プロンプトを出さないオプションです。ハンズオンの手順を止めないために付けています(このスタックは IAM リソースもセキュリティグループも作りません)。完了まで1〜2分かかります。

**確認ポイント**: 最後に `✅  Handson-sqs-intro-20261010-01` と `Outputs:` が表示され、`QueueUrl` と `QueueName` に値が入っている。

```text
 ✅  Handson-sqs-intro-20261010-01

Outputs:
Handson-sqs-intro-20261010-01.QueueName = handson-sqs-intro-20261010-01-queue
Handson-sqs-intro-20261010-01.QueueUrl = https://sqs.ap-northeast-1.amazonaws.com/123456789012/handson-sqs-intro-20261010-01-queue
```

#### 手順2: キューの URL を変数に入れる

以降の SQS の操作はすべてキューの URL を指定します。スタックの出力 `QueueUrl` を変数 `QUEUE_URL` に入れます。

```bash
QUEUE_URL=$(aws cloudformation describe-stacks --stack-name Handson-${HANDSON_JOB_ID} --query "Stacks[0].Outputs[?OutputKey=='QueueUrl'].OutputValue" --output text)
```

**確認ポイント**: 次のコマンドで、`https://sqs.ap-northeast-1.amazonaws.com/` で始まり `/handson-sqs-intro-20261010-01-queue` で終わる URL が表示される。

```bash
echo ${QUEUE_URL}
```

```text
https://sqs.ap-northeast-1.amazonaws.com/123456789012/handson-sqs-intro-20261010-01-queue
```

ターミナルを開き直した場合は、事前準備の手順1(環境変数)、事前準備の手順2(`cdk/` への移動)、この手順2の順にやり直してください。

#### 手順3: キューの設定を確認する

可視性タイムアウトと暗号化の設定を確認します。

```bash
aws sqs get-queue-attributes --queue-url "${QUEUE_URL}" --attribute-names VisibilityTimeout SqsManagedSseEnabled --query Attributes --output json
```

**確認ポイント**: `VisibilityTimeout` が `"30"`、`SqsManagedSseEnabled` が `"true"` と表示される。

```json
{
    "VisibilityTimeout": "30",
    "SqsManagedSseEnabled": "true"
}
```

> **解説**: 可視性タイムアウトは、受信されたメッセージが他の受信者から見えなくなる時間(秒)です。SQS の既定値は30秒です。

#### 手順4: キューのタグを確認する

後片付けの確認に使う `handson-job-id` タグが付いていることを確認します。

```bash
aws sqs list-queue-tags --queue-url "${QUEUE_URL}" --query Tags --output json
```

**確認ポイント**: `"handson-job-id": "sqs-intro-20261010-01"` が含まれている(`HANDSON_JOB_ID` を変えた場合はその値)。

```json
{
    "handson-job-id": "sqs-intro-20261010-01"
}
```

### 2. メッセージを送信・受信・削除する

#### 手順5: メッセージを3件送信する

`order-1`、`order-2`、`order-3` という本文のメッセージを1件ずつ送信します。

```bash
for i in 1 2 3; do aws sqs send-message --queue-url "${QUEUE_URL}" --message-body "order-${i}" --query MessageId --output text; done
```

**確認ポイント**: メッセージID(`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` の形式)が3行表示される。

```text
5f2a1c9e-0b7d-4e3a-9c1f-2d8e6a4b7c01
a1b2c3d4-1111-4a2b-8c3d-4e5f6a7b8c02
0e9d8c7b-2222-4f6e-9d5c-3b2a1f0e9d03
```

#### 手順6: キューにメッセージが3件あることを確認する

```bash
aws sqs get-queue-attributes --queue-url "${QUEUE_URL}" --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible --query Attributes --output json
```

**確認ポイント**: `ApproximateNumberOfMessages` が `"3"`、`ApproximateNumberOfMessagesNotVisible` が `"0"` と表示される。`"3"` より小さい場合は、5秒ほど待ってから同じコマンドを再実行してください。

```json
{
    "ApproximateNumberOfMessages": "3",
    "ApproximateNumberOfMessagesNotVisible": "0"
}
```

> **解説**: `ApproximateNumberOfMessages` は受信できる状態のメッセージ数、`ApproximateNumberOfMessagesNotVisible` は受信済みで見えない状態(インフライト)のメッセージ数です。名前のとおり概算値で、実際の状態から数秒遅れて反映されることがあります。

#### 手順7: メッセージを受信する

メッセージを最大10件受信し、メッセージID・本文・受信ハンドルをファイル `received-basic.txt` に追記します。受信ハンドルは、後の手順で削除に使います。

```bash
aws sqs receive-message --queue-url "${QUEUE_URL}" --max-number-of-messages 10 --wait-time-seconds 10 --visibility-timeout 300 --query 'not_null(Messages, `[]`)[].[MessageId,Body,ReceiptHandle]' --output text | tee -a received-basic.txt
```

**確認ポイント**: 1〜3行表示され、各行が「メッセージID、本文(`order-1` などの3つのいずれか)、受信ハンドル(長い文字列)」の3列になっている。

```text
5f2a1c9e-0b7d-4e3a-9c1f-2d8e6a4b7c01	order-1	AQEB...(長い文字列)...
a1b2c3d4-1111-4a2b-8c3d-4e5f6a7b8c02	order-2	AQEB...(長い文字列)...
0e9d8c7b-2222-4f6e-9d5c-3b2a1f0e9d03	order-3	AQEB...(長い文字列)...
```

> **解説**: オプションの意味は次のとおりです。
> - `--wait-time-seconds 10`: ロングポーリング。メッセージが届くまで最大10秒待ちます。指定しないとショートポーリングになり、SQS がサーバーの一部だけを調べるため、メッセージがあっても空の応答が返ることがあります。
> - `--visibility-timeout 300`: 今回受信したメッセージだけ、見えない時間をキューの設定(30秒)ではなく300秒にします。削除までに時間がかかっても、メッセージが再び見える状態に戻らないようにするためです。
> - `` --query 'not_null(Messages, `[]`)[]...' ``: 応答にメッセージがない場合、何も出力しないようにする指定です。

#### 手順8: 3件とも受信できたことを確認する

```bash
wc -l < received-basic.txt
```

**確認ポイント**: `3` と表示される。

```text
       3
```

`3` より小さい場合は、手順7をもう一度実行してから、この手順8をやり直してください。1回の受信で3件そろわないことがあるのは、標準キューの通常の動作です。

#### 手順9: メッセージがキューから消えずに見えない状態になっていることを確認する

```bash
aws sqs get-queue-attributes --queue-url "${QUEUE_URL}" --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible --query Attributes --output json
```

**確認ポイント**: `ApproximateNumberOfMessages` が `"0"`、`ApproximateNumberOfMessagesNotVisible` が `"3"` と表示される。値が変わっていない場合は、5秒ほど待ってから再実行してください。

```json
{
    "ApproximateNumberOfMessages": "0",
    "ApproximateNumberOfMessagesNotVisible": "3"
}
```

> **解説**: 受信したメッセージはキューから消えていません。見えない状態(インフライト)になっているだけで、削除しなければ可視性タイムアウトの後に再び受信できるようになります。

#### 手順10: 受信したメッセージを削除する

`received-basic.txt` の各行の受信ハンドルを使って、3件を削除します。

```bash
while IFS=$'\t' read -r MESSAGE_ID BODY HANDLE; do aws sqs delete-message --queue-url "${QUEUE_URL}" --receipt-handle "${HANDLE}"; echo "deleted: ${BODY}"; done < received-basic.txt
```

**確認ポイント**: `deleted: order-1`、`deleted: order-2`、`deleted: order-3` の3行が表示され(順番は異なることがあります)、エラーが表示されない。

```text
deleted: order-1
deleted: order-2
deleted: order-3
```

> **解説**: 削除にはメッセージIDではなく、受信のたびに発行される受信ハンドルを使います。同じメッセージでも受信するたびに受信ハンドルは変わります。

#### 手順11: キューが空になったことを確認する

```bash
aws sqs get-queue-attributes --queue-url "${QUEUE_URL}" --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible --query Attributes --output json
```

**確認ポイント**: `ApproximateNumberOfMessages` と `ApproximateNumberOfMessagesNotVisible` がどちらも `"0"` と表示される。`"0"` にならない場合は、5秒ほど待ってから再実行してください。

```json
{
    "ApproximateNumberOfMessages": "0",
    "ApproximateNumberOfMessagesNotVisible": "0"
}
```

### 3. 可視性タイムアウト(30秒)の挙動を確かめる

この章では、メッセージを受信しても削除せず、30秒後に再び受信できることを確かめます。**手順13から手順15までは、30秒以内に続けて実行してください。**

#### 手順12: メッセージを1件送信する

送信したメッセージのIDを変数 `MSG_ID` に入れます。

```bash
MSG_ID=$(aws sqs send-message --queue-url "${QUEUE_URL}" --message-body "visibility-test" --query MessageId --output text)
```

**確認ポイント**: 次のコマンドで、メッセージID(`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` の形式)が表示される。

```bash
echo ${MSG_ID}
```

```text
3d6f0a2b-7c41-4e8a-b5d2-9f1e0c3a6b04
```

#### 手順13: 受信だけして削除しない

メッセージを受信し、メッセージIDと受信回数(`ApproximateReceiveCount`)を表示します。この後、削除はしません。

```bash
aws sqs receive-message --queue-url "${QUEUE_URL}" --wait-time-seconds 5 --message-system-attribute-names ApproximateReceiveCount --query 'not_null(Messages, `[]`)[].[MessageId,Attributes.ApproximateReceiveCount]' --output text
```

**確認ポイント**: 手順12の `MSG_ID` と同じメッセージIDと、受信回数 `1` が表示される。

```text
3d6f0a2b-7c41-4e8a-b5d2-9f1e0c3a6b04	1
```

何も表示されなかった場合は、同じコマンドを再実行してください。

#### 手順14: すぐに再受信して、メッセージが見えないことを確かめる

手順13と同じコマンドを、手順13から30秒以内に実行します。

```bash
aws sqs receive-message --queue-url "${QUEUE_URL}" --wait-time-seconds 5 --message-system-attribute-names ApproximateReceiveCount --query 'not_null(Messages, `[]`)[].[MessageId,Attributes.ApproximateReceiveCount]' --output text
```

**確認ポイント**: 約5秒待った後、何も表示されずにプロンプトに戻る。

メッセージが表示された場合は、手順13から30秒を過ぎています。その場合は、そのまま手順16に進んでください(以降の受信回数は、この確認ポイントの記載より1ずつ多くなります)。

#### 手順15: メッセージが見えない状態でキューに残っていることを確認する

```bash
aws sqs get-queue-attributes --queue-url "${QUEUE_URL}" --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible --query Attributes --output json
```

**確認ポイント**: 手順13から30秒以内であれば、`ApproximateNumberOfMessages` が `"0"`、`ApproximateNumberOfMessagesNotVisible` が `"1"` と表示される。

```json
{
    "ApproximateNumberOfMessages": "0",
    "ApproximateNumberOfMessagesNotVisible": "1"
}
```

#### 手順16: 可視性タイムアウトが過ぎるまで30秒待つ

```bash
sleep 30
```

**確認ポイント**: 約30秒後にプロンプトに戻る。

#### 手順17: もう一度受信して、同じメッセージが戻ってきたことを確かめる

```bash
aws sqs receive-message --queue-url "${QUEUE_URL}" --wait-time-seconds 5 --message-system-attribute-names ApproximateReceiveCount --query 'not_null(Messages, `[]`)[].[MessageId,Attributes.ApproximateReceiveCount]' --output text
```

**確認ポイント**: 手順12の `MSG_ID` と同じメッセージIDと、受信回数 `2` が表示される。

```text
3d6f0a2b-7c41-4e8a-b5d2-9f1e0c3a6b04	2
```

> **解説**: 削除されなかったメッセージは、可視性タイムアウトが過ぎると再び受信できる状態に戻ります。受信者が処理の途中で停止しても、メッセージは失われずに別の受信者が処理を引き継げます。そのため、処理が終わったら必ず削除します。
>
> 標準キューは「少なくとも1回」の配信です。そのため、まれに可視性タイムアウト中でも同じメッセージが届くことがあります。

このメッセージは削除せず、次の章でも使います。

### 4. 可視性タイムアウトを10秒に変える

この章では、CDK からキューの可視性タイムアウトを10秒に変え、メッセージが30秒より早く戻ってくることを確かめます。

#### 手順18: 変更内容を確認する

`-c visibilityTimeoutSeconds=10` を付けたときに、何が変わるかを確認します。

```bash
npx cdk diff -c jobId=${HANDSON_JOB_ID} -c visibilityTimeoutSeconds=10
```

**確認ポイント**: `[~] VisibilityTimeout` の行と、その下に `[-] 30`(変更前)と `[+] 10`(変更後)が表示される。

出力のうち、該当部分の表示例です。罫線やインデント、前後に表示されるリソースの行は、CDK のバージョンによって異なることがあります。

```text
 └─ [~] VisibilityTimeout
     ├─ [-] 30
     └─ [+] 10
```

#### 手順19: 可視性タイムアウトを10秒にしてデプロイする

```bash
npx cdk deploy -c jobId=${HANDSON_JOB_ID} -c visibilityTimeoutSeconds=10 --require-approval never
```

**確認ポイント**: 最後に `✅  Handson-sqs-intro-20261010-01` と表示される。キューは作り直されないため、`Outputs:` の `QueueUrl` は手順1と同じ値になる。

#### 手順20: 設定の反映を60秒待つ

SQS のキュー属性の変更は、反映まで最大60秒かかります。

```bash
sleep 60
```

**確認ポイント**: 約60秒後にプロンプトに戻る。

#### 手順21: 可視性タイムアウトが10秒になったことを確認する

```bash
aws sqs get-queue-attributes --queue-url "${QUEUE_URL}" --attribute-names VisibilityTimeout --query Attributes --output json
```

**確認ポイント**: `VisibilityTimeout` が `"10"` と表示される。

```json
{
    "VisibilityTimeout": "10"
}
```

#### 手順22: 手順17のメッセージを受信する

手順17で受信したメッセージは、30秒以上たったので再び受信できる状態に戻っています。

```bash
aws sqs receive-message --queue-url "${QUEUE_URL}" --wait-time-seconds 5 --message-system-attribute-names ApproximateReceiveCount --query 'not_null(Messages, `[]`)[].[MessageId,Attributes.ApproximateReceiveCount]' --output text
```

**確認ポイント**: 手順12の `MSG_ID` と同じメッセージIDと、受信回数 `3` が表示される。

```text
3d6f0a2b-7c41-4e8a-b5d2-9f1e0c3a6b04	3
```

#### 手順23: 12秒待つ

新しい可視性タイムアウト(10秒)より少し長く待ちます。

```bash
sleep 12
```

**確認ポイント**: 約12秒後にプロンプトに戻る。

#### 手順24: 10秒強で同じメッセージが戻ってきたことを確かめる

今回は、受信したメッセージの受信ハンドルもファイル `received-last.txt` に保存します。後の手順で削除に使うため、`--visibility-timeout 300` で今回受信したメッセージだけ見えない時間を300秒にします。

```bash
aws sqs receive-message --queue-url "${QUEUE_URL}" --wait-time-seconds 5 --visibility-timeout 300 --message-system-attribute-names ApproximateReceiveCount --query 'not_null(Messages, `[]`)[].[MessageId,Attributes.ApproximateReceiveCount,ReceiptHandle]' --output text | tee received-last.txt
```

**確認ポイント**: 手順12の `MSG_ID` と同じメッセージID、受信回数 `4`、受信ハンドルの3列が1行表示される。30秒待たずに、約12秒で再受信できている。

```text
3d6f0a2b-7c41-4e8a-b5d2-9f1e0c3a6b04	4	AQEB...(長い文字列)...
```

何も表示されなかった場合は、同じコマンドを再実行してください(`received-last.txt` は上書きされます)。

> **解説**: 可視性タイムアウトは、受信者が1件の処理にかかる時間より長くします。短すぎると、処理中のメッセージが別の受信者にも配られ、二重に処理されます。長すぎると、受信者が停止したときに再処理が始まるまでの時間が延びます。

### 5. 残ったメッセージを削除する

#### 手順25: 受信ハンドルを変数に入れる

```bash
RECEIPT_HANDLE=$(cut -f3 received-last.txt)
```

**確認ポイント**: 次のコマンドで、`AQEB` などで始まる長い文字列が1行表示される。

```bash
echo ${RECEIPT_HANDLE}
```

```text
AQEB...(長い文字列)...
```

手順26〜29は発展の手順です。時間が足りない場合は、手順30に進んでください。

#### 手順26(発展): 見えない時間を0秒にして、すぐに見える状態へ戻す

`change-message-visibility` を使うと、受信済みのメッセージの見えない時間を個別に変えられます。0秒にすると、すぐに再び受信できる状態に戻ります。

```bash
aws sqs change-message-visibility --queue-url "${QUEUE_URL}" --receipt-handle "${RECEIPT_HANDLE}" --visibility-timeout 0
```

**確認ポイント**: 何も表示されずにプロンプトに戻る(エラーが表示されない)。

#### 手順27(発展): メッセージが見える状態に戻ったことを確認する

```bash
aws sqs get-queue-attributes --queue-url "${QUEUE_URL}" --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible --query Attributes --output json
```

**確認ポイント**: `ApproximateNumberOfMessages` が `"1"`、`ApproximateNumberOfMessagesNotVisible` が `"0"` と表示される。値が変わっていない場合は、5秒ほど待ってから再実行してください。

```json
{
    "ApproximateNumberOfMessages": "1",
    "ApproximateNumberOfMessagesNotVisible": "0"
}
```

#### 手順28(発展): もう一度受信して受信ハンドルを保存する

受信ハンドルは受信のたびに変わるため、削除の前に受信し直して新しい受信ハンドルを保存します。

```bash
aws sqs receive-message --queue-url "${QUEUE_URL}" --wait-time-seconds 5 --visibility-timeout 300 --message-system-attribute-names ApproximateReceiveCount --query 'not_null(Messages, `[]`)[].[MessageId,Attributes.ApproximateReceiveCount,ReceiptHandle]' --output text | tee received-last.txt
```

**確認ポイント**: 手順12の `MSG_ID` と同じメッセージID、受信回数 `5`、受信ハンドルの3列が1行表示される。

#### 手順29(発展): 新しい受信ハンドルを変数に入れる

```bash
RECEIPT_HANDLE=$(cut -f3 received-last.txt)
```

**確認ポイント**: 次のコマンドで、手順25とは異なる長い文字列が1行表示される。

```bash
echo ${RECEIPT_HANDLE}
```

```text
AQEB...(手順25とは異なる長い文字列)...
```

#### 手順30: メッセージを削除する

```bash
aws sqs delete-message --queue-url "${QUEUE_URL}" --receipt-handle "${RECEIPT_HANDLE}"
```

**確認ポイント**: 何も表示されずにプロンプトに戻る(エラーが表示されない)。

#### 手順31: キューが空になったことを確認する

```bash
aws sqs get-queue-attributes --queue-url "${QUEUE_URL}" --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible --query Attributes --output json
```

**確認ポイント**: `ApproximateNumberOfMessages` と `ApproximateNumberOfMessagesNotVisible` がどちらも `"0"` と表示される。削除の直後は反映が数秒遅れ、`ApproximateNumberOfMessagesNotVisible` が `"1"` のまま表示されることがあります。`"0"` にならない場合は、5秒ほど待ってから同じコマンドを再実行してください。

```json
{
    "ApproximateNumberOfMessages": "0",
    "ApproximateNumberOfMessagesNotVisible": "0"
}
```

## 後片付け

作成と逆の順番で削除します。キューに残ったメッセージは、キューと一緒に削除されます。

### 受信結果を保存したファイルを削除する

手順7と手順24(手順28)で作ったローカルのファイルを削除します。AWS のリソースではありません。

```bash
rm -f received-basic.txt received-last.txt
```

**確認ポイント**: 次のコマンドで何も表示されない。

```bash
ls received-basic.txt received-last.txt 2>/dev/null
```

### CDK で作成したリソースを削除する

`cdk/` ディレクトリで実行します。`--force` は削除の確認プロンプトを出さないオプションです。

```bash
npx cdk destroy -c jobId=${HANDSON_JOB_ID} --force
```

**確認ポイント**: `✅  Handson-sqs-intro-20261010-01: destroyed` と表示される。

```bash
aws cloudformation describe-stacks --stack-name Handson-${HANDSON_JOB_ID}
```

**確認ポイント**: `Stack with id Handson-sqs-intro-20261010-01 does not exist` というエラーになる。

### キューが削除されたことを確認する

```bash
aws sqs get-queue-url --queue-name handson-${HANDSON_JOB_ID}-queue
```

**確認ポイント**: `The specified queue does not exist` を含むエラーになる。キューの削除には最大60秒かかるため、URL が表示された場合は1分ほど待って再実行してください。

### 残っていないことを確認する

```bash
aws resourcegroupstaggingapi get-resources \
  --tag-filters "Key=handson-job-id,Values=${HANDSON_JOB_ID}" \
  --query 'ResourceTagMappingList[].ResourceARN' --output text
```

**確認ポイント**: 何も表示されない。削除直後は数分間表示が残ることがあるため、表示された場合は5分ほど待って再実行してください。表示が残る場合でも、前の手順で `get-queue-url` がエラーになっていれば、キューは実際には削除されています。

このハンズオンでは、タグで検索できないリソース(自動作成されるロググループ、IAM ロールなど)は作りません。CDK のブートストラップで作られたリソース(`CDKToolkit` スタック)はアカウント共通のため、削除しないでください。

このリポジトリで作業している場合は、リポジトリのルートにある棚卸しスクリプトでも確認できます(`cdk/` から実行する場合のパスです)。3つの節(タグ付きリソース / CloudFormation スタック / IAM ロール)がすべて空であれば完了です。

```bash
../../../scripts/list-tagged.sh ${HANDSON_JOB_ID} ${AWS_PROFILE} ${AWS_REGION}
```

## トラブルシューティング

| 症状 | 原因 | 対処 |
| --- | --- | --- |
| `npx cdk deploy` で `-c jobId=<英小文字・数字・ハイフン、40文字以内> を指定してください` と表示される | `HANDSON_JOB_ID` が未設定か、大文字などを含んでいる | 事前準備の手順1で `HANDSON_JOB_ID` を設定し直す |
| `npx cdk deploy` で `Unable to resolve AWS account to use` と表示される | 認証情報またはプロファイルが読めていない | `echo ${AWS_PROFILE}` で値を確認し、`aws sts get-caller-identity` が成功することを確かめる |
| `npx cdk deploy` で `SSM parameter /cdk-bootstrap/... not found` や `has not been bootstrapped` と表示される | 対象のアカウント・リージョンで CDK のブートストラップがされていない | 管理者にブートストラップを依頼する(ハンズオンでは行わない) |
| `npx cdk deploy` で `You must wait 60 seconds after deleting a queue before you can create another with the same name` と表示される | 同じ名前のキューを削除してから60秒たっていない(`QueueDeletedRecently`) | 1分以上待ってから、`npx cdk deploy` を再実行する |
| `aws sqs ...` で `Parameter validation failed: Invalid length for parameter QueueUrl` などのエラーになる | ターミナルを開き直して `QUEUE_URL` が空になっている | 事前準備の手順1、事前準備の手順2(`cdk/` への移動)、手順2の順にやり直す |
| 手順13などで `Unknown options: --message-system-attribute-names` を含むエラーになる | AWS CLI v2 のバージョンが古く、このオプションに対応していない | `aws --version` でバージョンを確認し、AWS CLI v2 を最新版に更新してから、手順12からやり直す |
| 手順7で表示されるメッセージが3件未満 | 1回の受信で全件が返るとは限らない(標準キューの通常の動作) | 手順7を再実行し、手順8で `3` になるまで繰り返す |
| 手順14でメッセージが表示される | 手順13から30秒を過ぎた。またはまれに起きる重複配信 | そのまま手順16に進む。以降の受信回数は記載より多くなる |
| 手順6・9・11などで属性値が期待値にならない | `Approximate...` は概算値で、反映が数秒遅れる | 5秒ほど待ってから再実行する |
| 手順21で `VisibilityTimeout` が `"30"` のまま | 属性の変更が反映されていない、または手順19で `-c visibilityTimeoutSeconds=10` を付け忘れた | 手順19の出力を確認し、30秒待ってから手順21を再実行する |
| 手順30で `ReceiptHandleIsInvalid` などのエラーになる | 受信ハンドルが古い(後から別の受信がされた) | 手順28と手順29で受信し直してから、手順30を再実行する |

## 参考

- [Amazon SQS の可視性タイムアウト](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [Amazon SQS のキューのクォータ](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/quotas-queues.html)
- [SetQueueAttributes(属性変更の反映時間)](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_SetQueueAttributes.html)
- [AWS CLI receive-message](https://docs.aws.amazon.com/cli/latest/reference/sqs/receive-message.html)
- [AWS CDK aws_sqs モジュール](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_sqs-readme.html)
- [AWS CDK QueueProps](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_sqs.QueueProps.html)
- [Amazon SQS の料金](https://aws.amazon.com/sqs/pricing/)
- [AWS CloudFormation の料金](https://aws.amazon.com/cloudformation/pricing/)

## 付録: CDK コードの説明

| ファイル | 内容 |
| --- | --- |
| `cdk/bin/app.ts` | アプリのエントリーポイント。`jobId` を受け取り、全リソースに `handson-job-id` タグを付ける |
| `cdk/lib/handson-stack.ts` | SQS 標準キューと、出力(`QueueUrl` / `QueueName`)の定義 |
| `cdk/lib/destroy-aspect.ts` | 全リソースの削除ポリシーを `DESTROY` にする(後片付けで残さないため) |

キューの定義は次のとおりです(`cdk/lib/handson-stack.ts` の抜粋)。

```typescript
const queue = new sqs.Queue(this, 'Queue', {
  queueName: `handson-${props.jobId}-queue`,
  visibilityTimeout: cdk.Duration.seconds(visibilityTimeoutSeconds),
  encryption: sqs.QueueEncryption.SQS_MANAGED,
  removalPolicy: cdk.RemovalPolicy.DESTROY,
});

new cdk.CfnOutput(this, 'QueueUrl', { value: queue.queueUrl });
new cdk.CfnOutput(this, 'QueueName', { value: queue.queueName });
```

- `queueName`: キュー名を `handson-<jobId>-queue` に固定します。後片付けで `get-queue-url` による確認に使います。
- `visibilityTimeout`: context の `visibilityTimeoutSeconds` から受け取ります。指定がなければ30秒です。既定値と同じ30秒でも明示しているのは、手順18の `cdk diff` で `30` から `10` への変化を表示するためです。
- `encryption: SQS_MANAGED`: SQS 管理キーによる暗号化(SSE-SQS)です。AWS KMS のキーを作らないため、削除待機期間のあるリソースが残りません。
- `removalPolicy: DESTROY`: `cdk destroy` でキューを削除します。`DestroyAspect` でもスタック内の全リソースに同じ設定をしています。
