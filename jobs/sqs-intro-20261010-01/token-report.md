## 実行レポート(job: sqs-intro-20261010-01)

| フェーズ | 入力 | 出力 | キャッシュ読込 | キャッシュ作成 | 想定コスト(USD) |
| --- | --- | --- | --- | --- | --- |
| リサーチ・構成案 | 0 | 0 | 0 | 0 | $0.0000 |
| 執筆 | 44 | 16,138 | 1,438,044 | 134,397 | $1.3083 |
| 検証(再試行 2回を含む) | 1,315 | 13,646 | 1,780,724 | 59,621 | $1.1019 |
| レビュー | 18 | 18,781 | 439,311 | 83,483 | $0.8860 |
| 合計 | 1,377 | 48,565 | 3,658,079 | 277,501 | $3.2962 |

AWS検証費用(見積もり): $0.01 / 上限 $1.00
(根拠: Pricing MCP 未使用(接続失敗)、公式料金ページから取得。https://aws.amazon.com/sqs/pricing/ は読めたが単価表が描画されず数値が取れなかったため、AWS 公式ブログ(https://aws.amazon.com/blogs/aws-cloud-financial-management/aws-price-list-gets-a-natural-language-upgrade-introducing-the-aws-pricing-mcp-server/)の標準キュー $0.40/100万リクエストを使用(リージョン記載なし。ap-northeast-1 の値としては未確認)。SQS 標準キュー リクエスト 500件/回、CloudFormation は AWS::* のため追加料金なし(https://aws.amazon.com/cloudformation/pricing/)、リージョン単価の不確かさと CDK アセットの S3 リクエスト分をバッファ $0.01 で計上。ap-northeast-1、無料枠なし、時間課金リソースなし)

トークン費用: $3.2962 / 上限 $10.00

- 想定コストは Claude Code が出力する **API料金換算の想定コスト** であり、Pro/Max プランの実際の請求額とは一致しない。正確な請求額は Claude Console で確認すること。
- 集計元: OpenTelemetry api_request イベント。フェーズの開始・終了時刻(jobs/sqs-intro-20261010-01/phases.jsonl)で振り分けた。
