output "bucket_name" {
  description = "F1 project S3 bucket name"
  value       = aws_s3_bucket.f1_dp_vn.bucket
}

output "bucket_arn" {
  description = "F1 project S3 bucket ARN"
  value       = aws_s3_bucket.f1_dp_vn.arn
}