terraform {
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.68.0"
    }
  }

  # state はローカルに置く。検証時は -backend-config="path=<repo>/jobs/<job-id>/terraform.tfstate" でジョブディレクトリに保存する。
  backend "local" {}
}
