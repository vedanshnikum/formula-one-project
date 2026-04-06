resource "aws_s3_bucket" "f1_dp_vn" {
  bucket = "f1-dp-vn"

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_s3_bucket_versioning" "f1_dp_vn" {
  bucket = aws_s3_bucket.f1_dp_vn.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "f1_dp_vn" {
  bucket                  = aws_s3_bucket.f1_dp_vn.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}