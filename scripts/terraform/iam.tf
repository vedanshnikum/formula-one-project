data "aws_iam_user" "existing" {
  user_name = "himalaya-project"
}

resource "aws_iam_policy" "f1_s3_policy" {
  name        = "${var.project_name}-s3-policy-${var.environment}"
  description = "Allow Databricks to read and write F1 project S3 bucket"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ]
        Resource = [
          aws_s3_bucket.f1_dp_vn.arn,
          "${aws_s3_bucket.f1_dp_vn.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_user_policy_attachment" "f1_s3_attachment" {
  user       = data.aws_iam_user.existing.user_name
  policy_arn = aws_iam_policy.f1_s3_policy.arn
}