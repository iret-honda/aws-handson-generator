---
name: iac-cdk
description: ハンズオン用 AWS CDK(TypeScript)コードの規約。バージョン、ディレクトリ構成、命名規則、RemovalPolicy.DESTROY の徹底、handson-job-id タグの付与。IaC種別がCDKのハンズオンでIaCを書くときに使う。
---

# CDK(TypeScript)の規約

## バージョン

`templates/package.json` と `templates/package-lock.json` で固定している。ハンズオンごとに上げない(上げるときはこのスキルのテンプレートを更新し、手本で検証してから)。

| パッケージ | バージョン |
| --- | --- |
| aws-cdk-lib | 2.273.0 |
| aws-cdk(CLI) | 2.1145.0(`npx cdk` でプロジェクト内のものを使う) |
| constructs | 10.8.1 |
| typescript | 5.9.3 |
| Node.js | 22 以上 |

## ディレクトリ構成

`templates/` を `handsons/<job-id>/cdk/` にそのままコピーして始める。

```
cdk/
├── bin/app.ts             # jobId の受け取り、タグ付与、DestroyAspect の適用(原則変更しない)
├── lib/destroy-aspect.ts  # 全 CfnResource を RemovalPolicy.DESTROY にする(変更しない)
├── lib/handson-stack.ts   # ハンズオンのリソース定義(ここを書く)
├── cdk.json
├── package.json
├── package-lock.json
└── tsconfig.json
```

スタックは原則1つ。スタック名は `Handson-<jobId>`(`bin/app.ts` で決まる)。

## 必須ルール

1. **jobId を context で受け取る**: `npx cdk deploy -c jobId=${HANDSON_JOB_ID}`。`bin/app.ts` が `cdk.Tags.of(app).add('handson-job-id', jobId)` で全リソースにタグを付ける。
2. **RemovalPolicy.DESTROY**: `DestroyAspect` が全リソースに適用する。加えて、中身が残るリソースは個別に設定する。
   - S3: `removalPolicy: DESTROY` と `autoDeleteObjects: true`
   - ECR: `emptyOnDelete: true`
   - RDS / DynamoDB: `deletionProtection: false`
3. **ロググループは明示的に作る**: Lambda などが自動作成するロググループはタグも削除ポリシーも付かず、`cdk destroy` 後に残る。`logs.LogGroup` を定義して `retention: logs.RetentionDays.ONE_DAY` を付け、関数の `logGroup` に渡す。
4. **命名**: 物理名を付ける場合は `handson-${jobId}-<役割>`(例: `handson-${jobId}-queue`)。本文のリソース名と一致させる。名前の長さ制限があるリソース(IAM ロール64文字、S3 バケット63文字など)に注意する。
5. **後続手順で使う値は `CfnOutput`** で出す。本文ではスタックの出力から変数に入れる。
6. **ハードコードしない**: アカウントID・リージョンは `env` と `cdk.Aws.ACCOUNT_ID` / `cdk.Aws.REGION` を使う。
7. **Lookup を避ける**: `Vpc.fromLookup` など、合成時にAWSを参照する機能は使わない(合成を決定的にし、静的チェックを認証情報なしで通すため)。
8. **ブートストラップは前提**: アカウント共通の `CDKToolkit` スタックは管理者が事前に用意する。ハンズオンでは作らず、消さない。

## 静的チェック

検証の静的チェックでは、人が次を実行する。

```bash
npm ci
npx tsc --noEmit
npx cdk synth -c jobId=<job-id>
```

合成されたテンプレート(`cdk.out/Handson-<job-id>.template.json`)で、全リソースに `handson-job-id` タグがあり、`DeletionPolicy` が `Delete` であることを確認する(タグをサポートしないリソースタイプは除く)。

## 調べるとき

コンストラクトの使い方やベストプラクティスは `aws-iac` MCP で確認する。L2 コンストラクトがあれば L1(`Cfn*`)より優先する。
