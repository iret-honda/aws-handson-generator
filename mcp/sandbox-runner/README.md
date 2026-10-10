# sandbox-runner

ハンズオン検証用の MCP サーバー。AWS への書き込み経路をこのサーバー1つに絞り、検証担当(`handson-verifier`)だけが使う。設計は `docs/AWSハンズオン自動生成エージェント 設計書.md` の「ツールとMCPサーバー構成」「セキュリティとコスト管理」。

リポジトリ直下の `.mcp.json` で `uv run --project mcp/sandbox-runner sandbox-runner` として起動する。初回は uv が依存パッケージ(`uv.lock` で固定)を入れる。

## ツール

| ツール | 内容 | AWS |
| --- | --- | --- |
| `list_steps` | 本文(`handsons/<job-id>/README.md`)の手順とコマンドのブロックID(例: `step-12#1`)、確認ポイント、出力例 | 触れない |
| `run_step` | 1ブロック(または CLI 代替のコマンド)を実行して出力を返す | 書き込みあり |
| `list_tagged_resources` | `handson-job-id` タグ付きのリソース一覧。後片付け検証は `remainingCount` が0で合格 | 読み取り |
| `teardown` | IaC の destroy → タグ付きスタックの削除 → タグ付きリソースの削除 → 棚卸し。ラウンドを終える | 書き込みあり |
| `estimate_job_cost` | `aws-cost.json` とラウンドの経過時間からの見積もり。3つの上限の状態 | 触れない |

## 守りの仕組み

1. **プロファイルとリージョンの固定**: ジョブで最初に呼ばれたとき、`jobs/<job-id>/input.json` の値と STS で取ったアカウントIDを `jobs/<job-id>/sandbox/session.json` に固定する。以降、`input.json` が変わっていたら止める。構成案で承認されたアカウントIDと違う場合も止める。
2. **コマンド文字列の検査**(`policy.scan_command`): 固定した環境変数(`AWS_PROFILE`、`PATH`、認証情報など)の上書き、ガードを迂回する呼び出し(絶対パスの `aws`、`eval`、`env`、`bash -c`、`python3 -c`、`docker` など)、作業ディレクトリの外への `cd` / `rm` を拒否する。本文の「環境変数を設定する」手順の `export AWS_PROFILE=...` などの行は、実行せずに固定値で置き換える。
3. **シムによる引数の検査**(`shims/` → `guard.py`): `PATH` の先頭に置いたシムが `aws` / `cdk` / `npx` / `npm` / `terraform` の引数を検査する。
   - `aws`: 読み取り系(`get-` / `list-` / `describe-` など)は通す。変更系は、対象の名前・URL・ARN にジョブIDが含まれるか、ARN / EC2 のIDで指定した対象に `handson-job-id` タグが付いている場合だけ通す。アカウントや請求、IAM ユーザー・アクセスキー、`sts assume-role` などは設定(`sandbox.deniedAwsServices` / `deniedAwsOperations`)で拒否する。EC2 は許可したインスタンスタイプで1台だけ
   - `cdk`: `-c jobId=<ジョブID>` が必須。`bootstrap` などは使えない。`cdk.json` の `app` は `npx ts-node --prefer-ts-exts bin/<名前>.ts` だけ
   - `npx`: `cdk` / `tsc` / `ts-node` / `tsx` だけ。`--no` を付け、レジストリから取ってこない
   - `terraform`: `-var job_id` / `region` がジョブの値と一致すること。`init` には state の置き場所(`jobs/<job-id>/terraform.tfstate`)を足す。`import` や `state rm` は使えない
4. **上限**: `run_step` の前後で、AWS 費用の見積もり(上限の `teardownRatio`)、トークン費用(`scripts/report.py --check`)、ラウンドの実行時間(`maxRuntimeMinutes`)を確かめ、超えていたら実行せず `action: teardown` を返す。
5. **削除はタグを確かめてから**: `teardown` と `scripts/cleanup-stale.sh` は、削除の直前にもう一度タグを確かめる。タグのないリソースには触れない(名前にジョブIDを含むロググループだけは例外)。
6. **追跡**: すべての AWS 呼び出しのユーザーエージェントに `handson-<job-id>` が入る(`AWS_SDK_UA_APP_ID`)。CloudTrail の `userAgent` で検索できる。

これらは多層防御の1層で、シェルの意味を完全に解釈するものではない。たとえば `npx cdk synth` は本文の IaC コード(TypeScript)を実行するので、そのコードが SDK を直接呼べば引数の検査は効かない。被害範囲の最終的な境界は、検証専用アカウントと IAM 権限である。

## 作業領域(`jobs/<job-id>/sandbox/`、git には入れない)

| ファイル | 内容 |
| --- | --- |
| `session.json` | 固定したプロファイル・リージョン・アカウントID、ラウンドの開始・終了時刻 |
| `shell/` | 手順間で引き継ぐシェル変数(`vars.sh`)と作業ディレクトリ(`cwd`)。新しいラウンドで初期化 |
| `runs/round-<n>.jsonl` | 実行したコマンドと、省略していない出力 |
| `guard.jsonl` | シムの判定(許可・拒否と理由) |
| `teardown.jsonl` | teardown の経過と結果 |
| `work/` | 予備の作業ディレクトリ(作業ディレクトリとして許可している場所の1つ) |

アカウントIDや受信ハンドルを含むので、`.gitignore` と `.claude/settings.json`(Edit / Write を deny)で扱いを制限している。

## 開発

```bash
cd mcp/sandbox-runner
uv run pytest -q
```

テストは仮のリポジトリを作って動かし、AWS には接続しない。

`teardown` が自動削除できる種類は `resources.py` の `DELETERS`(SQS、SNS、S3、Lambda、ロググループ、DynamoDB、IAM ロール・ポリシー、ECR、Secrets Manager、SSM パラメーター、Step Functions、EventBridge ルール、EC2 インスタンス・セキュリティグループ・ボリューム、CloudFormation スタック)。新しいサービスのハンズオンで「要手動削除」が出たら、ここに追加する。
