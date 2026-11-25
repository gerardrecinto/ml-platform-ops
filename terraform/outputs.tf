output "cluster_name" {
  value = module.eks.cluster_name
}

output "model_bucket" {
  value = aws_s3_bucket.models.bucket
}

output "scoring_role_arn" {
  value = aws_iam_role.scoring.arn
}
