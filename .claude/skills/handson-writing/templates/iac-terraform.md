# Terraform版の差し込み内容

本文テンプレートの `<!-- IAC:... -->` を、以下の対応する節で置き換える。`{{...}}` は構成案に合わせて埋める。

## IAC:PREREQUISITES

```markdown
  - Terraform {{バージョン}} 以上(`terraform version` で確認)
  - このリポジトリの `terraform/` ディレクトリ
```

## IAC:SETUP

````markdown
### 2. Terraform を初期化する

```bash
cd terraform
```

```bash
terraform init
```

**確認ポイント**: `Terraform has been successfully initialized!` と表示される。

state(作成したリソースの記録)はこのディレクトリの `terraform.tfstate` に保存されます。後片付けが終わるまで削除しないでください。
````

## IAC:DEPLOY

````markdown
### 手順{{n}}: 作成されるリソースを確認する

```bash
terraform plan -var "job_id=${HANDSON_JOB_ID}" -var "region=${AWS_REGION}"
```

**確認ポイント**: 最後に `Plan: {{N}} to add, 0 to change, 0 to destroy.` と表示される。

### 手順{{n+1}}: Terraform でリソースを作成する

```bash
terraform apply -var "job_id=${HANDSON_JOB_ID}" -var "region=${AWS_REGION}" -auto-approve
```

`-auto-approve` は確認プロンプトを省略するオプションです。直前の手順で作成内容を確認済みのため付けています。

**確認ポイント**: `Apply complete! Resources: {{N}} added, 0 changed, 0 destroyed.` と表示され、`Outputs:` に `{{出力名}}` が表示される。

### 手順{{n+2}}: 出力を変数に入れる

```bash
{{VAR}}=$(terraform output -raw {{出力名}})
```

**確認ポイント**: `echo ${{VAR}}` で {{期待する形}} が表示される。
````

## IAC:DESTROY

````markdown
### Terraform で作成したリソースを削除する

```bash
terraform destroy -var "job_id=${HANDSON_JOB_ID}" -var "region=${AWS_REGION}" -auto-approve
```

**確認ポイント**: `Destroy complete! Resources: {{N}} destroyed.` と表示される。

```bash
terraform state list
```

**確認ポイント**: 何も表示されない。
````

## IAC:CODE_NOTES

````markdown
## 付録: Terraform コードの説明

| ファイル | 内容 |
| --- | --- |
| `terraform/versions.tf` | Terraform と AWS プロバイダーのバージョン固定 |
| `terraform/providers.tf` | `default_tags` で全リソースに `handson-job-id` タグを付ける |
| `terraform/variables.tf` | `job_id` と `region` |
| `terraform/main.tf` | {{リソース}} の定義 |
| `terraform/outputs.tf` | 後続の手順で使う値 |

{{要点となるコードの抜粋と説明}}
````
