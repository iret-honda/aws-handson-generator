# CDK版の差し込み内容

本文テンプレートの `<!-- IAC:... -->` を、以下の対応する節で置き換える。`{{...}}` は構成案に合わせて埋める。

## IAC:PREREQUISITES

```markdown
  - Node.js 22 以上(`node --version` で `v22.` 以上)
  - このリポジトリの `cdk/` ディレクトリ(AWS CDK は `npx` でプロジェクト内のバージョンを使います)
  - 対象のアカウント・リージョンで CDK のブートストラップが済んでいること(事前準備で確認します)
```

## IAC:SETUP

````markdown
### 2. CDK プロジェクトを準備する

```bash
cd cdk
```

```bash
npm ci
```

**確認ポイント**: `npx cdk --version` で `{{CDK CLI のバージョン}}` から始まるバージョンが表示される。

### 3. CDK のブートストラップを確認する

```bash
aws cloudformation describe-stacks --stack-name CDKToolkit --query 'Stacks[0].StackStatus' --output text
```

**確認ポイント**: `CREATE_COMPLETE` または `UPDATE_COMPLETE` と表示される。

`Stack with id CDKToolkit does not exist` と表示された場合は、アカウントの管理者にブートストラップを依頼してください。ブートストラップで作られるリソースはアカウント共通のもので、このハンズオンの後片付けの対象外です。
````

## IAC:DEPLOY

````markdown
### 手順{{n}}: CDK でリソースをデプロイする

`cdk/lib/handson-stack.ts` に定義した {{リソース}} を作成します。`-c jobId=...` で渡した値が、リソース名と `handson-job-id` タグに使われます。

```bash
npx cdk deploy -c jobId=${HANDSON_JOB_ID} --require-approval never
```

`--require-approval never` は、IAM 権限の変更確認をスキップするオプションです。ハンズオンの手順を止めないために付けています。

**確認ポイント**: 最後に `✅  Handson-<HANDSON_JOB_ID>` と `Outputs:` が表示され、`{{出力名}}` に値が入っている。

### 手順{{n+1}}: スタックの出力を変数に入れる

```bash
{{VAR}}=$(aws cloudformation describe-stacks --stack-name Handson-${HANDSON_JOB_ID} --query "Stacks[0].Outputs[?OutputKey=='{{出力名}}'].OutputValue" --output text)
```

**確認ポイント**: `echo ${{VAR}}` で {{期待する形}} が表示される。
````

## IAC:DESTROY

````markdown
### CDK で作成したリソースを削除する

```bash
npx cdk destroy -c jobId=${HANDSON_JOB_ID} --force
```

**確認ポイント**: `✅  Handson-<HANDSON_JOB_ID>: destroyed` と表示される。

```bash
aws cloudformation describe-stacks --stack-name Handson-${HANDSON_JOB_ID}
```

**確認ポイント**: `Stack with id Handson-<HANDSON_JOB_ID> does not exist` というエラーになる。
````

## IAC:CODE_NOTES

````markdown
## 付録: CDK コードの説明

| ファイル | 内容 |
| --- | --- |
| `cdk/bin/app.ts` | アプリのエントリーポイント。`jobId` を受け取り、全リソースに `handson-job-id` タグを付ける |
| `cdk/lib/handson-stack.ts` | {{リソース}} の定義 |
| `cdk/lib/destroy-aspect.ts` | 全リソースの削除ポリシーを `DESTROY` にする(後片付けで残さないため) |

{{要点となるコードの抜粋と説明}}
````
