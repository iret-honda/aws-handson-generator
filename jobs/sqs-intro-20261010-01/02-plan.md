# 構成案: Amazon SQS 入門 ― 標準キューの送受信と可視性タイムアウトを確かめる

| 項目 | 値 |
| --- | --- |
| ジョブID | sqs-intro-20261010-01 |
| AWSプロファイル | default |
| アカウントID | 123456789012 |
| リージョン | ap-northeast-1 |
| IaC | CDK(TypeScript)。スタック名 `Handson-sqs-intro-20261010-01` |
| レベル / 所要時間 | 入門 / 60分 |
| 見積もり(検証1回) | $0.0102 / 上限 $1.00(却下ライン $0.80)。4回分の合計 $0.0408 |

## 目的

CDK で SQS の標準キューを作り、CLI でメッセージの送信・受信・削除を一通り行う。そのうえで、受信しても削除しなければメッセージが一定時間後に戻ってくること(可視性タイムアウト)を、キューの設定値を変えて確かめる。

## 対象者と前提

- 対象者: AWS CLI を日常的に使うが、SQS を触ったことがない社内エンジニア
- 前提知識: AWS CLI の基本操作(`--profile`、`--region`、`--query`)、`npx cdk deploy` / `destroy` を実行したことがある程度の CDK の知識
- 前提環境: Node.js 22 以上、AWS CLI v2、対象アカウントで `CDKToolkit` スタック(CDK ブートストラップ)が作成済みであること(iac-cdk ルール8。ハンズオンでは作らない)

## 学べること

- 標準キューの基本操作(SendMessage / ReceiveMessage / DeleteMessage)と、受信ハンドル(ReceiptHandle)の役割
- 「受信」と「削除」が別の操作であること。削除しないとメッセージは消えず、インフライト(見えない状態)になるだけであること
- 可視性タイムアウトの挙動。期限までは再受信できず、期限後は `ApproximateReceiveCount` が増えて再配信される
- キュー属性(`ApproximateNumberOfMessages` / `ApproximateNumberOfMessagesNotVisible`)で、キューの状態を CLI から読み取る方法
- ショートポーリングでは空が返りうること、`--wait-time-seconds`(ロングポーリング)で安定すること

## 作るリソース

すべてに `handson-job-id=sqs-intro-20261010-01` タグを付ける。

| リソース | 名前 | 作り方 | 課金 | 消し方 |
| --- | --- | --- | --- | --- |
| SQS 標準キュー(SSE-SQS、可視性タイムアウトは context `visibilityTimeoutSeconds` で指定。既定30秒) | `handson-sqs-intro-20261010-01-queue` | CDK | リクエスト課金のみ(時間課金なし) | `npx cdk destroy`(`removalPolicy: DESTROY`) |
| CloudFormation スタック | `Handson-sqs-intro-20261010-01` | CDK | なし(`AWS::*` リソースは追加料金なし) | `npx cdk destroy` |

- CLI で作るリソースはない。CLI で行うのはメッセージの操作と状態の確認だけ。
- `CfnOutput` に `QueueUrl` と `QueueName` を出す。本文では、スタックの出力から環境変数 `QUEUE_URL` に入れる。
- **DLQ は入れない。** 理由は次の3つ。
  1. 60分の配分(下の章立て)がすでに埋まっている。DLQ に移る様子を見るには `maxReceiveCount` 回の受信と可視性タイムアウトの待ちを繰り返す必要があり、さらに10分程度かかる。
  2. `handson-structure` では、DLQ を応用(120分)の「異常系を試す」に割り当てている。入門は「1本で1つのこと」として、可視性タイムアウトに絞る。
  3. DLQ に移るのは受信のタイミングに依存し、ショートポーリングの空振りも重なるため、手本の1本としては検証の再現性が下がる。

## 章立て

| # | 手順 | 確認ポイントの概要 | 目安 | 備考 |
| --- | --- | --- | --- | --- |
| 1 | 事前準備: 環境変数(`AWS_PROFILE`、`AWS_REGION`、`HANDSON_JOB_ID`)を設定し、`aws sts get-caller-identity` でアカウントを確認する。`CDKToolkit` スタックがあることを確認し、`npm ci` を実行する | `Account` が `123456789012`。`aws cloudformation describe-stacks --stack-name CDKToolkit` が `CREATE_COMPLETE` か `UPDATE_COMPLETE` を返す | 10分 | |
| 2 | 基本リソースを作る: `npx cdk deploy -c jobId=${HANDSON_JOB_ID}` で標準キューを作り、出力から `QUEUE_URL` を取る | スタックが `CREATE_COMPLETE`。`get-queue-attributes` で `VisibilityTimeout=30`、`SqsManagedSseEnabled=true`。`list-queue-tags` に `handson-job-id` がある | 15分 | 初回の deploy は1〜2分程度(推測) |
| 3-1 | 基本操作: メッセージを3件送信する(`send-message`) | 各送信で `MessageId` が返る。少し待ってから `ApproximateNumberOfMessages` が 3 | 5分 | 属性値は概算値なので、反映に数秒かかることを本文に書く |
| 3-2 | 基本操作: 受信する(`receive-message --wait-time-seconds 10 --max-number-of-messages 10`) | `Messages[].Body` に送った本文があり、`ReceiptHandle` が取れる。`ApproximateNumberOfMessagesNotVisible` が受信した件数になる | 7分 | ショートポーリングだと空が返ることがあるので、ロングポーリングを使う理由を書く。一度に3件そろわない場合は繰り返す |
| 3-3 | 基本操作: 受信したメッセージを削除する(`delete-message`) | `ApproximateNumberOfMessages` と `ApproximateNumberOfMessagesNotVisible` がどちらも 0 | 8分 | |
| 4-1 | 違いを見る(既定30秒): 1件送信し、受信だけして削除しない。すぐ再受信し、30秒以上待ってからもう一度受信する | 直後の再受信は空で、`NotVisible=1`。30秒後の受信では同じ `MessageId` が返り、`ApproximateReceiveCount=2` | 4分 | |
| 4-2 | 設定を変える: `npx cdk deploy -c jobId=... -c visibilityTimeoutSeconds=10` で可視性タイムアウトを10秒にし、60秒待つ。4-1 と同じ操作を繰り返す | `VisibilityTimeout=10`。10秒強で再受信できる(30秒待たずに戻る) | 5分 | 属性の反映に最大60秒かかるため待つ(01-research.md 6節)。`cdk diff` で変更点が VisibilityTimeout だけであることも見せる |
| 4-3 | 残ったメッセージを `delete-message` で消す。補足として、`change-message-visibility --visibility-timeout 0` を使えば即座に見える状態へ戻せることを1コマンドで示す | `ApproximateNumberOfMessages` と `NotVisible` がどちらも 0 | 1分 | 4-3 は省略可能な発展扱いにして、時間を超えそうなら飛ばせるようにする |
| 5 | 後片付け: `npx cdk destroy -c jobId=${HANDSON_JOB_ID} --force`。その後 `./scripts/list-tagged.sh` でタグ付きリソースが0件であることを確かめる | スタックが `describe-stacks` で見つからない。`get-queue-url` が `QueueDoesNotExist` を返す。`list-tagged.sh` の3節がすべて空 | 5分 | Tagging API の表示が遅れる場合は5分後に再実行する |

合計 60分。コンソール手順はない(すべて CLI と CDK で完結する)。

## 費用見積もり

**Pricing MCP 未使用(接続失敗)、公式料金ページから取得。** `https://aws.amazon.com/sqs/pricing/` は読めたが、単価表が描画されておらず数値が取れなかった。そこでドキュメント検索で見つかった AWS 公式ブログの標準キュー単価 $0.40 / 100万リクエストを使った。このブログの値はリージョンが書かれておらず、ap-northeast-1 の単価としては確認できていない。その不確かさと、S3(CDK アセット)のリクエスト単価が取れなかった分を、バッファ $0.01 で見込んでいる。無料枠は考慮しない。

| リソース | 単価 | 想定量(検証1回) | 金額 |
| --- | --- | --- | --- |
| SQS 標準キュー リクエスト | $0.0000004 / リクエスト($0.40 / 100万) | 500 リクエスト(CLI 操作 約60 + CloudFormation による作成・更新・削除 約30 + 再試行・空振りの受信分を大きく上乗せ) | $0.0002 |
| CloudFormation(`AWS::*`) | 追加料金なし | 1スタック、deploy 2回、destroy 1回 | $0.0000 |
| バッファ(リージョン単価の不確かさ、CDK アセットの S3 リクエスト) | 単価未取得 | — | $0.0100 |
| 合計 | | | **$0.0102** |

- 4回分(初回と修正3回)の合計: $0.0408
- 却下ライン $0.80 に対して約1.3%。SQS の単価が仮に10倍でも、1回 $0.012 程度で判定は変わらない。

時間課金のリソース: なし(SQS はリクエスト課金のみ。最低料金なし)。

## リスクと消し忘れポイント

- **単価がリージョン別に確認できていない**: Pricing MCP が使えず、料金ページの単価表も読めなかった。金額は小さいので判定への影響はないが、承認時に、人が料金ページか料金計算ツールで ap-northeast-1 の単価を目視で確認することを勧める。
- **CDK ブートストラップの有無**: リサーチ担当は AWS を参照できないため、`CDKToolkit` スタックがあるかは未確認。ない場合は、管理者に事前のブートストラップを依頼する(ハンズオンでは作らない)。
- **属性値は概算値で、反映に遅れがある**: `ApproximateNumberOfMessages*` は即座には一致しない。確認ポイントには「数秒待って再確認」を入れる。
- **可視性タイムアウトの変更の反映待ち**: 属性の変更は反映に最大60秒かかる。4-2 では deploy 後に60秒待ち、`get-queue-attributes` で値を確かめてから操作する。
- **ショートポーリングの空振り**: 受信はすべて `--wait-time-seconds` を付けたロングポーリングにする。4-1 の「直後の再受信は空」の確認では待ち時間を5秒程度にし、可視性タイムアウト(30秒・10秒)より十分短くする。
- **標準キューの重複配信**: at-least-once 配信なので、まれに可視性タイムアウト中でも再配信されうる。本文の注記に入れ、検証で起きた場合は再実行で判定する。
- **検証ループでの再作成の失敗**: キューを削除してから60秒間は同じ名前で作れない(`QueueDeletedRecently`)。修正ループで destroy の直後に deploy する場合は、60秒以上空ける。
- **消し忘れ**: CLI で作るリソースはなく、DLQ も作らない。キュー内のメッセージはキューと一緒に消える。後片付けは `cdk destroy` と `list-tagged.sh` で完結する。`CDKToolkit` とそのアセットはアカウント共通なので対象外(消さない)。

## 参照ドキュメント

- https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html
- https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/quotas-queues.html
- https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html
- https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_SetQueueAttributes.html
- https://docs.aws.amazon.com/cli/latest/reference/sqs/receive-message.html
- https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_sqs.QueueProps.html
- https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_sqs-readme.html
- https://aws.amazon.com/sqs/pricing/
- https://aws.amazon.com/blogs/aws-cloud-financial-management/aws-price-list-gets-a-natural-language-upgrade-introducing-the-aws-pricing-mcp-server/
- https://aws.amazon.com/cloudformation/pricing/
- https://aws.amazon.com/about-aws/whats-new/2025/08/amazon-sqs-max-payload-size-1mib/
