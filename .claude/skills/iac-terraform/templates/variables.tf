variable "job_id" {
  description = "ハンズオンのジョブID。リソース名と handson-job-id タグに使う"
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{0,39}$", var.job_id))
    error_message = "job_id は英小文字・数字・ハイフンで40文字以内にしてください。"
  }
}

variable "region" {
  description = "リソースを作るリージョン"
  type        = string
  default     = "ap-northeast-1"
}
