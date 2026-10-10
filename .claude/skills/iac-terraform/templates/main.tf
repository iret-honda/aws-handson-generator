locals {
  # リソース名は "handson-${var.job_id}-<役割>" にそろえる(本文の表記と一致させる)。
  name_prefix = "handson-${var.job_id}"
}

# 例:
# resource "aws_sqs_queue" "main" {
#   name = "${local.name_prefix}-queue"
# }
