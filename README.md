# AWS ハンズオン自動生成エージェント

AWS のサービス名を渡すと、ハンズオン教材一式を作る Claude Code 用のエージェント構成です。手順はサンドボックスの AWS アカウントで実際に実行して確かめ、通ったものだけを成果物にします。対象読者は社内エンジニアです。

成果物は次の4つです。

- ハンズオン本文(Markdown)
- IaC(AWS CDK の TypeScript か Terraform)と CLI コマンド
- 想定コストと削除手順
- 検証レポート(末尾にトークン数、API 料金換算の想定コスト、AWS 検証費用の見積もり)

「第三者が本文どおりに完了でき、クリーンアップ後にリソースが残らないこと」を完成の条件にしています。

設計の詳細は [docs/AWSハンズオン自動生成エージェント 設計書.md](docs/AWSハンズオン自動生成エージェント%20設計書.md) を参照してください。

## 現在の状況

フェーズ1(試作)を進めています。Claude Code 上で手動運用し、AWS での実行検証は人が行います。`/handson` が検証シートを作り、人がそれを実行して結果を返す流れです。

| フェーズ | 内容 | 次に進む条件 |
| --- | --- | --- |
| 1 | Claude Code で手作業でハンズオンを1本作り切る | 手本の1本が完成 |
| 2 | 検証担当のサブエージェントと `sandbox-runner` MCP を作り、検証ループを自動化する | 後片付け漏れなしで連続合格 |
| 3 | チームで運用する。Agent Toolkit for AWS への移行もここで検討する | — |

手本の1本目は [handsons/sqs-intro-20261010-01/](handsons/sqs-intro-20261010-01/)(Amazon SQS 入門)です。

## 前提

- Claude Code(CLI か VS Code 拡張)
- AWS CLI と、検証専用アカウントのプロファイル(既定は `~/.aws/credentials` の `default`)
- Node.js(CDK を使う場合)、Terraform(Terraform を使う場合)
- `uv`(`uvx` で MCP サーバーを起動します)
- Python 3(レポート集計)
- Docker(トークン計測用の OpenTelemetry Collector を動かす場合)

## セットアップ

```bash
git clone https://github.com/iret-honda/aws-handson-generator.git
cd aws-handson-generator

# コミット前の機密情報チェックを有効にする(clone ごとに必要)
git config core.hooksPath .githooks
```

MCP サーバーの設定は [.mcp.json](.mcp.json)、権限とテレメトリの設定は [.claude/settings.json](.claude/settings.json) にあり、clone すれば同じ構成で動きます。

トークンを計測する場合は Collector を起動し、`.claude/settings.json` の `env` と同じ内容を `.claude/settings.local.json`(gitignore 済み)にも書いてください。共有の設定ファイルの `env` はセッションに反映されないことがあります。

```bash
./scripts/telemetry.sh up      # 停止は down、状態確認は status
```

## 使い方

Claude Code で次のように実行します。

```
/handson Amazon SQS
/handson Amazon SQS --iac terraform --profile sandbox --region us-east-1
/handson --resume sqs-intro-20261010-01
```

| 引数 | 既定値 |
| --- | --- |
| サービス名 | 必須 |
| `--iac cdk\|terraform` | `cdk` |
| `--profile` | `default` |
| `--region` | `ap-northeast-1` |
| `--level 入門\|応用` | `入門` |
| `--duration <分>` | 入門60分、応用120分 |
| `--theme` | なし(リサーチ担当が提案) |

処理は次の順に進みます。人の判断が入るのは構成案の承認と最終レビューの2か所です。

1. 入力の解釈とアカウント確認
2. リサーチと構成案の作成(`handson-researcher`)
3. **人が構成案を承認**
4. 執筆(`handson-writer`)
5. 検証(フェーズ1は人が検証シートに沿って実行)
6. レビュー(`handson-reviewer`)
7. **人が最終レビュー**
8. 出力(git コミットとレポート)

検証で不合格になると執筆担当に戻します。3回直しても通らなければ人に判断を仰ぎます。各ステップの成果物はファイルに残すので、途中で止まっても `--resume` で再開できます。

## 費用の上限

上限は [config/handson.config.json](config/handson.config.json) の `limits` で管理しています。どれかを超えたら検証を止めて後片付けに入ります。金額はすべて USD 表示です。

| 項目 | 値 |
| --- | --- |
| AWS 検証費用(1本あたり) | $1.00 |
| 構成案を作り直す見積もり額 | 上限の8割($0.80)超 |
| トークン費用(API 料金換算) | $10.00 |
| 実行時間(時間課金リソースがある場合) | 60分 |
| 修正ループ | 3回 |

費用は実績ではなく見積もりで判定します(Pricing MCP を使用)。Cost Explorer API は呼び出しごとに課金されるので自動では呼びません。

## 安全のための仕組み

- サブエージェントが `aws` / `cdk` / `terraform` を直接実行することは `.claude/settings.json` で禁止しています。フェーズ2以降、AWS に書き込めるのは検証担当が使う `sandbox-runner` MCP だけになります。
- 作るリソースにはすべて `handson-job-id` タグを付けます(CDK はタグと `RemovalPolicy.DESTROY`、Terraform は `default_tags`)。後片付けの検証は、このタグが付いたリソースが0件になれば合格です。アカウント全体を掃除するツールは使いません。
- 外部ドキュメントやブログの内容はデータとして扱い、そこに書かれた指示には従いません。

## コミット前のマスキング

コミットするファイルに機密情報を残してはいけません。コミット前に必ず次を実行してください。

```bash
./scripts/mask-sensitive.sh <job-id>
```

AWS アカウントID、SQS の受信ハンドル、検証シートのメッセージID、検証者の実名を置き換えます。`.githooks/pre-commit` は、これらに加えてアクセスキーIDとパブリック IP を検出するとコミットを止めます。

## スクリプト

| コマンド | 内容 |
| --- | --- |
| `./scripts/new-job.sh <slug> <level>` | ジョブディレクトリを作り、ジョブIDを返す |
| `./scripts/phase.sh <job-id> <phase> start\|end` | フェーズの開始・終了時刻を記録する(トークン集計の区切り) |
| `./scripts/aws-identity.sh <profile> <region>` | 使うアカウントのIDを確認する(読み取りのみ) |
| `./scripts/list-tagged.sh <job-id> <profile> <region>` | タグ付きリソースを棚卸しする(後片付けの確認) |
| `python3 scripts/report.py <job-id> [--check]` | トークン数と想定コストのレポートを作る。`--check` は上限判定だけ |
| `./scripts/mask-sensitive.sh <job-id>` | コミット前に機密情報を置き換える |
| `./scripts/telemetry.sh up\|down\|status` | OpenTelemetry Collector を操作する |

## ディレクトリ構成

```
.
├── .claude/
│   ├── agents/          # サブエージェント(リサーチ / 執筆 / レビュー)
│   ├── skills/          # /handson 本体と、書き方・判断基準のスキル
│   └── settings.json    # 権限とテレメトリ
├── .githooks/           # 機密情報を検出する pre-commit
├── .mcp.json            # AWS 系 MCP サーバーの接続設定
├── config/              # 上限・既定値・OTel の項目名
├── docs/                # 設計書と図
├── handsons/<job-id>/   # 成果物(README.md=本文、cdk/ か terraform/、verification-report.md)
├── jobs/<job-id>/       # 各ステップの中間成果物(構成案、承認記録、検証記録、レビューなど)
├── scripts/             # 補助スクリプト
└── telemetry/           # Collector の設定(生データの data/ は gitignore)
```

スキルの役割分担は次のとおりです。「何ができるか」は MCP(AWS Knowledge / Documentation / IaC / Terraform / Pricing)から、「どう書くか・どう判断するか」はスキルから得ます。

| スキル | 内容 |
| --- | --- |
| `handson` | オーケストレーター(`/handson` の本体) |
| `handson-structure` | 構成案の作り方と章立て例 |
| `handson-writing` | 本文の書き方とテンプレート、手本 |
| `iac-cdk` / `iac-terraform` | IaC の規約とテンプレート |
| `cost-guardrails` | 費用上限、使用禁止サービス、見積もりの書式 |
| `cleanup-checklist` | 消し忘れやすいリソースのチェックリスト |
| `review-rubric` | 公開可否の採点基準 |
