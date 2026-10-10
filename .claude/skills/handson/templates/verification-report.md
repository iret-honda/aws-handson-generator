# 検証レポート: {{title}}

| 項目 | 値 |
| --- | --- |
| ジョブID | {{jobId}} |
| サービス | {{service}} |
| IaC | {{iac}} |
| プロファイル / アカウントID | {{profile}} / {{accountId}} |
| リージョン | {{region}} |
| 検証ラウンド | {{rounds}}回(合格はラウンド {{passedRound}}) |
| 検証方法 | フェーズ1: 人による手動実行 |

## 実行結果

| 手順 | 実行日時 | 結果 | 備考 |
| --- | --- | --- | --- |
{{stepResults}}

コンソール操作の手順は同等のCLI操作で代替して検証した(該当手順の備考に「CLI代替で検証」と記載)。

## 後片付け

- クリーンアップ後の `handson-job-id={{jobId}}` タグ付きリソース: {{remaining}}件
- タグを付けられないリソースの確認: {{untaggedCheck}}

## 不合格だったラウンドの記録

{{failedRounds}}

## レビュー

- review-rubric の採点: {{score}} / 100({{reviewResult}})
- 主な指摘と対応: {{reviewNotes}}

---

{{tokenReport}}
