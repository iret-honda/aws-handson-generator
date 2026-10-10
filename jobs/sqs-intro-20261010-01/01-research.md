# リサーチ: Amazon SQS 入門(sqs-intro-20261010-01)

- 調査日: 2026-10-10
- 使用MCP: `aws-knowledge`(search_documentation / read_documentation / get_regional_availability)のみ
- `aws-documentation` と `aws-pricing` は接続失敗のため使用していない。料金は公式料金ページとドキュメント検索で取得した(詳細は「料金」節)
- 取得元に指示文が含まれていた: **検出なし**(取得したページ本文に、エージェントへの実行指示や「無視せよ」の類の文は見当たらなかった)

## 1. サービス概要

- 受信したメッセージはキューに残ったまま、他のコンシューマーからは一時的に見えなくなる。見えない時間が可視性タイムアウト。処理後は `DeleteMessage` で明示的に消す。
  出典: https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html
- 可視性タイムアウトの既定値は30秒。期限までに削除しなければメッセージは再び見えるようになり、同じコンシューマーか別のコンシューマーが受信できる。`ChangeMessageVisibility` で個別に延長・短縮でき、0秒にすると即座に見えるようになる。(同上)
- 標準キューは at-least-once 配信なので、可視性タイムアウト中でも重複配信がないとは保証されない。(同上)
- 標準キューの順序はベストエフォート。スループットはほぼ無制限。
  出典: https://docs.aws.amazon.com/help-panel/AWSSimpleQueueService/latest/console/hp-createq-standard.html
- `ReceiveMessage` は既定でショートポーリング。サーバーの一部だけをサンプリングするため、メッセージが少ないと空が返ることがある(その場合は再実行する)。`WaitTimeSeconds` を指定するとロングポーリング(最大20秒)になる。1回に受信できるのは最大10件。
  出典: https://docs.aws.amazon.com/cli/latest/reference/sqs/receive-message.html
- `receive-message` の `--attribute-names` は非推奨(後方互換のため残っている)。`ApproximateReceiveCount` などを取るなら `--message-system-attribute-names` を使う。(同上)
- 新規キューは SSE-SQS(SQS 管理キーによるサーバー側暗号化)が既定で有効。HTTPS + SigV4 エンドポイントから作成した場合に限る。
  出典: https://aws.amazon.com/blogs/compute/announcing-server-side-encryption-with-amazon-simple-queue-service-managed-encryption-keys-sse-sqs-by-default/
- CDK の `sqs.Queue` も既定は SSE-SQS。KMS キーは作られないので、KMS の削除待機の問題は起きない。
  出典: https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_sqs-readme.html

## 2. 最近の変更(What's New)

| 時期 | 内容 | 出典 |
| --- | --- | --- |
| 2025-08 | 最大メッセージペイロードが 256 KiB から 1 MiB に拡大(標準・FIFO) | https://aws.amazon.com/about-aws/whats-new/2025/08/amazon-sqs-max-payload-size-1mib/ |
| 2025-11 | IPv6 対応が GovCloud (US) に拡大。商用・GovCloud・中国の全リージョンで IPv6 に対応 | https://aws.amazon.com/about-aws/whats-new/2025/11/amazon-sqs-ipv6-aws-govcloud-regions/ |
| (料金ページに記載あり) | フェアキュー: 標準キューでメッセージグループIDを持つメッセージを扱う操作には、フェアキュー料金と標準料金の両方がかかる | https://aws.amazon.com/sqs/pricing/ |

- ハンズオンへの影響: 1 MiB 化に合わせて、CDK の `maxMessageSizeBytes` の既定値も 1 MiB になっている(QueueProps のドキュメントによる)。フェアキューは入門の範囲外なので使わない。メッセージグループIDを付けなければ、フェアキュー料金はかからない。
- 2026年の SQS 自体の変更は、検索では見つからなかった(見つからなかったというだけで、変更がないとは言い切れない)。

## 3. リージョン提供状況(ap-northeast-1)

`get_regional_availability` で確認した。

| 種別 | 対象 | 状態 |
| --- | --- | --- |
| CloudFormation リソース | `AWS::SQS::Queue`、`AWS::SQS::QueuePolicy` | isAvailableIn |
| API | `SQS+CreateQueue`、`SendMessage`、`ReceiveMessage`、`DeleteMessage`、`ChangeMessageVisibility`、`GetQueueAttributes`、`ListQueueTags` | isAvailableIn |

使う機能はすべて ap-northeast-1 で一般提供されている。プレビュー機能は使わない。

## 4. CDK(aws-cdk-lib 2.273.0 系)の `sqs.Queue` の既定値

出典: https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_sqs.QueueProps.html

| プロパティ | 既定値 | ハンズオンでの扱い |
| --- | --- | --- |
| `queueName` | CloudFormation が自動生成 | `handson-${jobId}-queue` を明示する |
| `visibilityTimeout` | 30秒(0〜43200秒) | context で値を受け取る(既定30秒、第4章で10秒に変える) |
| `removalPolicy` | `RemovalPolicy.DESTROY` | 既定のままで消える。テンプレートの `DestroyAspect` でも DESTROY になる |
| `encryption` | 新規キューは `SQS_MANAGED`(SSE-SQS) | 既定のまま。KMS は使わない |
| `retentionPeriod` | 4日 | 既定のまま(どうせ destroy で消える) |
| `receiveMessageWaitTime` | 0(ショートポーリング) | 既定のまま。受信コマンド側で `--wait-time-seconds` を指定する |
| `deadLetterQueue` | なし | 入門では使わない(理由は 02-plan.md) |
| `maxMessageSizeBytes` | 1 MiB | 既定のまま |

## 5. 関係する CLI コマンドと API

| 目的 | CLI | API |
| --- | --- | --- |
| キュー URL の取得 | スタックの出力から取る(`aws cloudformation describe-stacks --query`)。補助として `aws sqs get-queue-url --queue-name` | `GetQueueUrl` |
| 属性の確認 | `aws sqs get-queue-attributes --attribute-names VisibilityTimeout ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible SqsManagedSseEnabled` | `GetQueueAttributes` |
| 送信 | `aws sqs send-message --queue-url --message-body` | `SendMessage` |
| 受信 | `aws sqs receive-message --queue-url --wait-time-seconds --max-number-of-messages --message-system-attribute-names ApproximateReceiveCount` | `ReceiveMessage` |
| 削除 | `aws sqs delete-message --queue-url --receipt-handle` | `DeleteMessage` |
| 可視性の変更 | `aws sqs change-message-visibility --queue-url --receipt-handle --visibility-timeout` | `ChangeMessageVisibility` |
| タグの確認 | `aws sqs list-queue-tags --queue-url` | `ListQueueTags` |

出典: https://docs.aws.amazon.com/cli/latest/reference/sqs/receive-message.html 、 https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html

## 6. 制約・クォータ(手順に影響するもの)

| 項目 | 内容 | 出典 |
| --- | --- | --- |
| キュー名 | 最大80文字。英数字、`-`、`_` が使える。大文字と小文字を区別する。`handson-sqs-intro-20261010-01-queue` は35文字なので問題ない | https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/quotas-queues.html |
| 属性変更の反映 | `SetQueueAttributes` での変更は、ほとんどの属性で反映に最大60秒かかる(`MessageRetentionPeriod` は最大15分) | https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_SetQueueAttributes.html |
| 同じ名前での再作成 | キューを消してから60秒間は同じ名前で作れない(`QueueDeletedRecently`) | https://docs.aws.amazon.com/aws-sdk-php/v3/api/api-sqs-2012-11-05.html |
| インフライト数 | 標準キューは約12万件まで | https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/quotas-queues.html |
| ロングポーリング | 最大20秒 | 同上 |
| タグ操作 | アカウントあたり 30 TPS | 同上 |
| 可視性タイムアウト | 0〜43200秒(12時間) | https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_sqs.QueueProps.html |

ハンズオンへの影響(推測を含む):
- 第4章で CDK から可視性タイムアウトを変える。CloudFormation はキューの属性更新に `SetQueueAttributes` 相当を使うと推測されるため、反映待ちとして `cdk deploy` の後に60秒待つ手順を入れる。
- 検証の修正ループでは destroy から deploy までの間隔が60秒未満になると、`QueueDeletedRecently` で作成に失敗しうる。検証担当(人)に、再実行の前に60秒以上空けるよう伝える。

## 7. 料金

### 取得の経緯

- **Pricing MCP は使っていない(接続失敗)。単価は公式の料金ページとドキュメント検索から取った。**
- `https://aws.amazon.com/sqs/pricing/` と `https://aws.amazon.com/jp/sqs/pricing/` は read_documentation で読めた。ただし単価表は動的に描画されるらしく、本文に数値がなかった(「リクエストの月額料金は以下のとおりです」の後が空)。読めたのは課金の仕組みだけ。
- 単価の数値は、ドキュメント検索で見つかった AWS 公式ブログの値を使った。標準キュー **$0.40 / 100万リクエスト**、FIFO $0.50 / 100万リクエスト。
  出典: https://aws.amazon.com/blogs/aws-cloud-financial-management/aws-price-list-gets-a-natural-language-upgrade-introducing-the-aws-pricing-mcp-server/
  - 注意: この値は Pricing MCP の回答例としてブログに載っているもので、**リージョンが書かれていない**。ap-northeast-1 の単価としては確認できていない。見積もりではこの値を使い、リージョン差の不確かさはバッファで吸収する(02-plan.md と aws-cost.json に明記)。

### 課金の仕組み(料金ページで確認)

出典: https://aws.amazon.com/sqs/pricing/

- SQS のアクションはすべて1リクエストとして数える(`GetQueueAttributes`、`ListQueueTags` なども含む)。
- 1リクエストには1〜10件のメッセージを入れられ、合計は最大 1 MiB。ペイロードは 64 KB ごとに1リクエストとして課金される。
- 同じリージョン内での送受信にはデータ転送料金がかからない。
- 最低料金はない。無料枠は毎月100万リクエストだが、`cost-guardrails` に従い見積もりでは考慮しない。
- KMS を使う場合は KMS の呼び出し料金が別にかかる。今回は SSE-SQS なので該当しない。
- 空振りの受信(メッセージが返らない `ReceiveMessage`)も課金対象。
  出典: https://repost.aws/knowledge-center/sqs-high-charges

### 関連サービス

- CloudFormation: `AWS::*` 名前空間のリソースプロバイダーは追加料金なし。
  出典: https://aws.amazon.com/cloudformation/pricing/
- CDK のアセットとテンプレートはブートストラップの S3 バケットに置かれる。S3 の料金ページ(https://aws.amazon.com/s3/pricing/)は読めたが、取得範囲内にリクエスト単価の数値はなかった。テンプレート数件の PUT と GET だけなので金額は誤差の範囲と推測し、見積もりではバッファに含めた。

## 8. 消し忘れやすいリソース

| 対象 | 内容 | 対策 |
| --- | --- | --- |
| キュー本体 | CDK の既定 `removalPolicy` が DESTROY なので、`cdk destroy` で消える | テンプレートの `DestroyAspect` でも DESTROY にする |
| DLQ | 別に作ると消し忘れやすい(cleanup-checklist の SQS 項目) | 今回は作らない |
| CLI で作るリソース | なし。CLI で行うのはメッセージ操作だけで、メッセージはキューと一緒に消える | — |
| ロググループ | Lambda を使わないので自動作成されるものはない | — |
| CDKToolkit スタック / アセット | アカウント共通なので対象外(iac-cdk ルール8)。ハンズオンでは作らず、消さない | 事前準備で存在を確認するだけ |
| Tagging API の表示遅れ | 削除直後は数分間残って見えることがある | `aws sqs get-queue-url` で実在しないことを確かめ、5分後に `list-tagged.sh` を再実行する |

## 9. 推測として扱っている点

- CloudFormation がキューの属性を更新するときに、内部で `SetQueueAttributes` 相当を呼ぶため60秒の反映待ちが同じように当てはまる、という点は推測。手順では安全側に倒して60秒待つ。
- ap-northeast-1 の SQS 単価が $0.40 / 100万リクエストと同じか、それに近いという点は推測。10倍だったとしても1回あたり $0.002 程度で、判定は変わらない。
