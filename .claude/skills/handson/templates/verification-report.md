# 検証レポート: {{title}}

| 項目 | 値 |
| --- | --- |
| ジョブID | {{jobId}} |
| サービス | {{service}} |
| IaC | {{iac}} |
| プロファイル / アカウントID | {{profile}} / {{accountId}} |
| リージョン | {{region}} |
| 検証ラウンド | {{rounds}}回(合格はラウンド {{passedRound}}) |
| 検証方法 | {{method}}(フェーズ2以降は「自動: handson-verifier / sandbox-runner」) |
| CloudTrail の追跡 | ユーザーエージェントに `handson-{{jobId}}` を含む呼び出し |

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
