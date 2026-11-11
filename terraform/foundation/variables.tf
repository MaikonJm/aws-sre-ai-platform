variable "project" {
  description = "Project name, used as a prefix for every resource"
  type        = string
  default     = "aws-sre-ai-platform"
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "CIDR block of the VPC"
  type        = string
  default     = "10.20.0.0/16"
}

variable "github_repository" {
  description = "GitHub repository allowed to assume the CI role (owner/name)"
  type        = string
  default     = "MaikonJm/aws-sre-ai-platform"
}

variable "ecr_repositories" {
  description = "Container image repositories, one per service"
  type        = set(string)
  default     = ["orders-api", "worker"]
}
