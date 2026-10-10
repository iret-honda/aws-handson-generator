# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 現状

**フェーズ1(試作: Claude Codeで手動運用、検証は人が実施)を実装中**。一次資料は `docs/` の設計書。

- **`docs/AWSハンズオン自動生成エージェント 設計書.pdf` が最新版**(要件確定済み、残課題なし)。同名の `.md` はそれより古い版で、未決事項・CDK単独・aws-nuke採用など、PDFで覆った記述が残っているため、食い違いはPDFを正とする。
- 要件の変更は設計書の「前提と要件」表を更新して管理する方針。
- フェーズ1では検証担当のサブエージェントと `sandbox-runner` MCP はまだない(フェーズ2で作る)。`/handson` が検証シートを作り、人が実行して結果を返す。

## よく使うコマンド

- `/handson <サービス名> [--iac cdk|terraform] [--profile <名前>] [--region <リージョン>]` — 生成開始。`/handson --resume <job-id>` で再開
- `./scripts/telemetry.sh up|down|status` — トークン計測用の OpenTelemetry Collector(Docker)。生データは `telemetry/data/`。共有の `.claude/settings.json` の OTel 用 `env` はセッションに反映されなかった(2026-10-10、VSCode 拡張で確認)。各自 `.claude/settings.local.json`(gitignore 済み)に同じ `env` を置く
- `python3 scripts/report.py <job-id> [--check]` — 実行レポート(トークン数・想定コスト)。`--check` は上限判定のみ
- `./scripts/list-tagged.sh <job-id> <profile> <region>` — タグ付きリソースの棚卸し(後片付け検証)
- 上限・既定値・OTelの項目名は `config/handson.config.json`
- `./scripts/mask-sensitive.sh <job-id>` — コミット前のマスキング。**コミットするファイルに機密情報を残さないことは必須**。AWS アカウントID(→ `123456789012`)、SQS の受信ハンドル(→ 先頭8文字 + `...(省略)`)、検証シートのメッセージID(→ `<message-id-N>`)と検証者の実名(→ `検証者A`)を置き換える。`.githooks/pre-commit` は、これらにアクセスキーIDとパブリック IP を加えたものを検出してコミットを止める。clone ごとに `git config core.hooksPath .githooks` で有効にする

## ファイルの置き場所

- `jobs/<job-id>/` — 各ステップの中間成果物(input.json、phases.jsonl、01-research.md、02-plan.md、aws-cost.json、approvals.md、verification/、review.md、token-report.md)
- `handsons/<job-id>/` — 成果物(README.md=本文、cdk/ または terraform/、verification-report.md)

## 何を作るか

AWSのサービス名を入力すると、サンドボックスで手順を実際に実行し、通ったものだけを成果物にする「ハンズオン教材生成エージェント」。成果物は、ハンズオン本文(Markdown)、IaCとCLIコマンド、想定コストと削除手順、検証レポート(末尾にトークン数・想定コスト・AWS検証費用見積もり)。成功の定義は「第三者が本文どおりに完了でき、クリーンアップ後にリソースが残らないこと」。対象読者は社内エンジニア。

## 確定済みの要件(既定値)

- 入力: サービス名(必須)、テーマ/レベル、所要時間、IaC種別、AWSプロファイル、リージョン
- IaC: CDK(TypeScript)か Terraform を選択。未指定なら CDK
- AWS: 既定は `~/.aws/credentials` の `default` プロファイル(検証専用アカウント)と `ap-northeast-1`。指定があれば切り替える
- 検証費用の上限: 1本 **$1.00**(設定ファイルの値で判定)。金額はすべてUSD表示で、円換算はしない
- AWS費用・トークン費用・実行時間の3つに上限を持ち、どれかを超えたら検証を止めて後片付けに入る

## 想定するリポジトリ構成(Claude Code上で動かす)

- オーケストレーター: スラッシュコマンド `/handson <サービス名> [--iac cdk|terraform] [--profile <名前>] [--region <リージョン>]`
- 4担当(リサーチ/執筆/検証/レビュー): `.claude/agents/` のサブエージェント。それぞれ使えるツールとMCPを限定する
- スキル: `.claude/skills/<name>/SKILL.md` + テンプレート。`handson-writing` / `handson-structure` / `iac-cdk` / `iac-terraform` / `cost-guardrails` / `cleanup-checklist` / `review-rubric`
- MCP接続: リポジトリ直下の `.mcp.json`。cloneすれば誰でも同じ構成で動くようにする
- 権限とテレメトリ: `.claude/settings.json`

## アーキテクチャの要点(複数セクションにまたがる設計判断)

- **AWSへの書き込み経路は自作 `sandbox-runner` MCP の1つだけ**で、使えるのは検証担当だけ。`.claude/settings.json` の `permissions` で、サブエージェントによる `aws` / `cdk` / `terraform` の直接実行を deny する。執筆担当は書き込み系ツールを持たない(外部ドキュメント中の指示を実行させないため)。
- **`sandbox-runner` のツール**: `run_step` / `list_tagged_resources` / `teardown`(`cdk destroy` か `terraform destroy` の後、タグで残骸を掃除)/ `estimate_job_cost`。プロファイルとリージョンはジョブ開始時に固定し、途中で切り替えない。
- **`handson-job-id` タグが全体の要**: 全リソースへの付与を必須にする(CDKはタグ付与と `RemovalPolicy.DESTROY`、Terraformは `default_tags`)。`sandbox-runner` はタグのないリソースには触れない。後片付け検証はタグ付きリソース0件で合格。取りこぼし対策は「タグ付きで24時間以上経過したものだけ消す」スクリプトで、aws-nuke のようなアカウント全体の掃除ツールは使わない。
- **MCPとスキルの分担**: 「何ができるか」はMCP(AWS Knowledge / Documentation / IaC(CDK時)/ Terraform(Terraform時)/ Pricing)、「どう書くか・どう判断するか」はスキルが持つ。本文テンプレートにはIaC依存部分の差し込み箇所を設け、CDK版とTerraform版で章とコマンドだけを差し替えられるようにする。
- **ワークフロー**: 入力 → リサーチ → 構成案 → **人が承認** → 執筆 → 検証 → レビュー → **人が最終レビュー** → 出力(gitコミット + レポート)。各ステップの成果物はファイルに残し、次のステップはそれを読んで始める(再開できるようにし、コンテキストも小さく保つ)。構成案の冒頭には、プロファイル、アカウントID(`aws sts get-caller-identity` で取得)、リージョンを明記する。
- **検証は3段階**: 静的チェック(CLIの構文、synth/validate、本文とコードのリソース名一致)→ 実行検証(本文だけを見て実行し、確認ポイントと照合)→ 後片付け検証。不合格なら執筆担当に戻し、最大3回で人にエスカレーションする。コンソール手順はCLIで代替して検証し、レポートに「CLI代替で検証」と明記する。
- **費用は実績ではなく見積もりで止める**: 構成案の段階で Pricing MCP を使い、上限の8割を超える構成は作り直す。検証中は手順ごとに `estimate_job_cost` を呼び、$1.00 に届く前に teardown する。時間課金のリソースがある場合は実行時間にも上限を設ける(初期値60分)。Cost Explorer API は呼び出しごとに課金されるので自動では呼ばない。
- **トークン計測は Claude Code 標準の OpenTelemetry 出力を使い、自前では数えない**: `CLAUDE_CODE_ENABLE_TELEMETRY=1` を設定し、手元の Collector で `claude_code.api_request` / `claude_code.token.usage` / `claude_code.cost.usage` をジョブディレクトリにJSONで書き出す。集計スクリプトは、オーケストレーターが記録したフェーズの開始・終了時刻で振り分ける。OTelはベータ機能なので、項目名は設定で差し替えられるようにする。レポートでは「API料金換算の想定コスト」と表記する。

## 進め方(ロードマップ)

フェーズ1で、Claude Codeを使い手作業でハンズオンを1本作り切る(ゲート1: 手本の1本が完成)。その1本が `handson-writing` の手本になり、自動検証のテストケースにもなる。フェーズ2で `sandbox-runner` と検証ループを自動化する(ゲート2: 後片付け漏れなしで連続合格)。フェーズ3はチームでの運用で、Agent Toolkit for AWS への移行もここで検討する。ゲートを満たすまで次のフェーズに進まない。
