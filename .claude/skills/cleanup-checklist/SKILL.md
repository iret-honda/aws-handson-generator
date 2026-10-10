---
name: cleanup-checklist
description: ハンズオンの後片付けで消し忘れやすいリソース(ENI、ロググループ、スナップショットなど)のサービス別チェックリストと、後片付け検証の手順。執筆・検証・レビュー時に使う。
---

# 後片付けチェックリスト

後片付け検証の合格条件は「**クリーンアップ手順の実行後、`handson-job-id=<job-id>` タグ付きのリソースが0件**」。加えて、タグが付かずに残るリソースがないことを、下のサービス別項目で確認する。

## 後片付け検証の手順

1. 本文の「後片付け」を上から実行する(IaC の destroy を含む)。
2. `./scripts/list-tagged.sh <job-id> <profile> <region>` を実行し、3つの節(タグ付きリソース / CloudFormation スタック / IAM ロール)がすべて空であることを確認する。
3. 削除直後は Resource Groups Tagging API に数分間残ることがある。表示された ARN は、各サービスの describe 系コマンドで実在するか確かめる。実在しなければ5分後に再実行する。
4. 下のサービス別項目のうち、該当するものを確認する。
5. 残っていたら失敗扱い。本文の後片付けに足りない手順を執筆担当に返す。

取りこぼしたリソースを人が消すときも、`handson-job-id` タグを確認してから消す。タグのない既存リソースには触れない。アカウント全体を掃除するツール(aws-nuke など)は使わない。

## 共通の落とし穴

| 落とし穴 | 対策 |
| --- | --- |
| 自動作成されるロググループ(`/aws/lambda/<関数名>`、`/aws/vendedlogs/...`、`/aws/codebuild/...` など)にタグが付かず残る | IaC で LogGroup を明示的に定義し、保持期間1日・削除ポリシー DESTROY にする。確認: `aws logs describe-log-groups --log-group-name-prefix /aws/lambda/handson-<job-id>` |
| CLI で作ったリソースは IaC の destroy で消えない | 本文の後片付けに、CLI で作ったものの削除手順を逆順で書く |
| 削除の順序依存(使用中のセキュリティグループ、アタッチ済みポリシー) | 依存するものから消す。IaC に任せられるものは IaC で作る |
| IAM ロールはグローバルで Tagging API に出ない | `list-tagged.sh` の IAM 節で確認する |
| CDK のアセット(ブートストラップの S3 バケット・ECR リポジトリ内) | アカウント共通のため対象外。ハンズオンでは大きなアセットを作らない |
| Terraform の state を消すとリソースが孤立する | 後片付けが終わるまで `terraform.tfstate` を消さない |

## サービス別の項目

| サービス | 消し忘れやすいもの | 確認・対策 |
| --- | --- | --- |
| Lambda | 自動作成ロググループ、VPC Lambda の ENI(削除に最大数十分) | ロググループを明示作成。VPC 接続は避ける。使う場合は ENI の削除待ちを所要時間に含める |
| EC2 | EBS ボリューム(`DeleteOnTermination=false`)、スナップショット、AMI、Elastic IP、キーペア | `aws ec2 describe-volumes --filters Name=tag:handson-job-id,Values=<job-id>`。EIP は解放まで課金 |
| VPC | NAT Gateway、Elastic IP、インターフェイス型エンドポイント、ENI | NAT Gateway は削除後も `deleted` 状態で一覧に残るが課金はない |
| S3 | オブジェクトが残っていてバケットを削除できない、バージョニングの旧版 | CDK: `autoDeleteObjects`、Terraform: `force_destroy`。CLI: `aws s3 rb s3://<bucket> --force`(バージョニング有効時は旧版の削除も必要) |
| ECR | イメージが残っていてリポジトリを削除できない | CDK: `emptyOnDelete`、Terraform: `force_delete` |
| CloudFormation | `DELETE_FAILED` のスタック | 原因リソースを確認して手動で消してから再削除 |
| RDS / Aurora | 最終スナップショット、削除保護、自動バックアップ | `skip_final_snapshot`、削除保護オフ。`aws rds describe-db-snapshots` |
| DynamoDB | 削除保護、オンデマンドバックアップ | 削除保護オフ。`aws dynamodb list-backups` |
| SQS | DLQ を別に作った場合の消し忘れ | DLQ も IaC で作る |
| SNS | トピック削除後もサブスクリプションが残る場合(メール購読の未確認など) | `aws sns list-subscriptions` |
| KMS | カスタマーマネージドキーは即時削除できず、7日以上の削除待機中もタグ付きで残る | 原則使わない(`cost-guardrails` の要承認)。AWS マネージドキーを使う |
| Secrets Manager | 既定で7〜30日の復旧期間中は残る | CLI: `--force-delete-without-recovery`、Terraform: `recovery_window_in_days = 0` |
| CloudWatch | アラーム、ダッシュボード、メトリクスフィルター | IaC で作る |
| API Gateway | アカウント設定の CloudWatch ロール(アカウント共通の設定) | ハンズオンで変更しない |
| Step Functions | 実行ログ用ロググループ | ロググループを明示作成 |
| Kinesis / Firehose | 配信先 S3 のオブジェクト、エラー出力 | 配信先バケットを `autoDeleteObjects` / `force_destroy` |
| IAM | CLI で作ったロール・ポリシー・インスタンスプロファイル | IaC で作る。CLI で作る場合は `--tags` を付け、デタッチしてから削除 |

新しいサービスでハンズオンを作り、ここにない消し忘れが見つかったら、この表に1行追加する(人の承認後)。
