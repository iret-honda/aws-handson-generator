provider "aws" {
  region = var.region

  # 全リソースに handson-job-id タグを付ける。後片付けの確認はこのタグで行う。
  default_tags {
    tags = {
      "handson-job-id" = var.job_id
    }
  }
}
