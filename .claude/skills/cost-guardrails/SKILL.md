---
name: cost-guardrails
description: ハンズオン検証費用の守り。1本$1.00の上限、構成案の却下ライン、使用禁止または要承認のサービスとインスタンスタイプ、無料枠の扱い、見積もりの書式。構成案の作成時、検証前、レビュー時に使う。
---

# 費用の守り

上限の値は `config/handson.config.json` の `limits` を正とする。このファイルの数値と食い違ったら設定ファイルに従う。金額はすべてUSDで表示し、円換算はしない。

| 上限 | 値 | 判定のタイミング |
| --- | --- | --- |
| AWS検証費用 | 1本あたり $1.00(`awsCostUsd`) | 構成案、検証中 |
| 構成案の却下ライン | 上限の8割 = $0.80(`planRejectRatio`) | 構成案 |
| 実行時間 | 60分(`maxRuntimeMinutes`) | 検証中(時間課金リソースがある場合) |
| トークン費用 | `tokenCostUsd` | フェーズの切り替わりごと |

## 見積もりの原則

1. **実績ではなく見積もりで止める**。AWS の請求データは反映に時間がかかるため。
2. 単価は `aws-pricing` MCP で、検証リージョンの値を取る。記憶の値を使わない。
3. **無料枠は考慮しない**。検証用アカウントが無料枠を使い切っている可能性があるため、保守的に見積もる。
4. 時間課金は、最低課金単位(1時間、1分、1秒など)を確認したうえで、実行時間の上限(60分)ぶんで計算する。
5. 検証は修正ループで最大4回(初回+3回)実行されうる。構成案では1回分の見積もりを $0.80 以下にし、4回分の合計も併記する。
6. Cost Explorer API は呼び出しごとに課金されるため、自動では呼ばない。実績額は後日コスト配分タグで人が確認する。

## 使用禁止(構成案に入れない)

- 長期契約・前払い: Reserved Instances、Savings Plans、Capacity Reservations
- 取り消せない課金: Route 53 のドメイン登録、AWS Shield Advanced、サポートプランの変更、AWS Marketplace の有料サブスクリプション
- 高額な最低料金: Amazon Redshift(プロビジョンド)、Amazon OpenSearch Service ドメイン、AWS Private CA、AWS Directory Service、Amazon MSK(プロビジョンド)
- GPU / 高性能インスタンス: `p*`、`g*`、`inf*`、`trn*`、`x*`、`u-*` ファミリー、`*.metal`
- SageMaker のリアルタイムエンドポイント、ノートブックインスタンスの長時間稼働

## 要承認(使うなら構成案の「リスク」に理由を書き、人の承認時に確認してもらう)

- 時間課金のネットワーク: NAT Gateway、インターフェイス型 VPC エンドポイント、Transit Gateway、Client VPN
- 起動・削除に時間がかかるもの: Amazon RDS / Aurora、Amazon ElastiCache、Amazon CloudFront、Amazon EKS
- 削除に待機期間があるもの: AWS KMS カスタマーマネージドキー(最短7日の削除待機があり、後片付け検証でタグ付きリソースとして残る)
- EC2 で `t3.small` / `t4g.small` を超えるインスタンスタイプ、複数台の起動
- Amazon Bedrock などの従量課金がトークン単位のサービス(呼び出し回数と入力サイズを見積もりに明記する)
- データ転送量が大きくなる手順(大きなファイルのアップロード・ダウンロード)

## 推奨

- EC2 が必要なら `t4g.micro` または `t3.micro`、EBS は gp3 の最小サイズ
- VPC が必要ならパブリックサブネットだけの構成にし、NAT Gateway を使わない
- サーバーレス(Lambda、SQS、SNS、DynamoDB オンデマンド、S3 など)のリクエスト課金を優先する
- CloudWatch Logs の保持期間は1日

## 見積もりの書式(`jobs/<job-id>/aws-cost.json`)

```json
{
  "estimatedUsd": 0.05,
  "estimatedUsdAllRounds": 0.20,
  "basis": "SQS リクエスト 1,000件、Lambda 100回 128MB 1秒、ap-northeast-1、無料枠なし",
  "pricingRegion": "ap-northeast-1",
  "retrievedAt": "2026-10-10T05:00:00Z",
  "items": [
    {"resource": "SQS 標準キュー リクエスト", "unitPriceUsd": 0.0000004, "unit": "request", "quantity": 1000, "usd": 0.0004}
  ],
  "hourlyResources": [],
  "verifiedEstimateUsd": null
}
```

- `estimatedUsd`: 検証1回分の見積もり。構成案の判定に使う。`items` の合計 + 時間課金 × 実行時間の上限(60分)
- `items`: 時間課金以外(リクエスト課金、一括のバッファなど)。検証1回分の量で書く
- `hourlyResources`: 時間課金のリソース(`{"resource", "unitPriceUsdPerHour", "minimumHours"}`、`minimumHours` は最低課金時間があれば)。`items` には入れない
- `verifiedEstimateUsd`: 検証後、実際の実行時間を反映した見積もり(実績額ではない)。オーケストレーターが追記する

検証中は `sandbox-runner` の `estimate_job_cost` が、ラウンドごとに「`items` の合計 + Σ 単価 × 経過時間」で見積もりを更新し、全ラウンドの合計が上限の `teardownRatio`(9割 = $0.90)に達したら `run_step` を止めて teardown を促す。`items` と `hourlyResources` が実態より小さいとこの守りが効かないので、量は多めに見積もる。
