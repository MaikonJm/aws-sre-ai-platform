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

variable "github_oidc_subject_prefix" {
  description = <<-EOT
    Prefix of the OIDC "sub" claim allowed to assume the CI role.
    Repositories created after mid-2026 use GitHub's immutable format,
    owner@OWNER_ID/repo@REPO_ID, which cannot be hijacked by re-creating
    a deleted or renamed repository with the same name.
    IDs: gh api repos/OWNER/REPO --jq '.owner.id, .id'
  EOT
  type        = string
  default     = "repo:MaikonJm@37089888/aws-sre-ai-platform@1453410613"
}

variable "ecr_repositories" {
  description = "Container image repositories, one per service"
  type        = set(string)
  default     = ["orders-api", "worker", "sre-agent"]
}
