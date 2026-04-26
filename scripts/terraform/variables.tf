variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-2"
}

variable "project_name" {
  description = "Project name used for naming all resources"
  type        = string
  default     = "f1-project"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}