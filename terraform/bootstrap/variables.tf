variable "project" {
  description = "Project name, used as a prefix for every resource"
  type        = string
  default     = "aws-sre-ai-platform"
}

variable "region" {
  description = "AWS region for the whole platform"
  type        = string
  default     = "us-east-1"
}

variable "monthly_budget_usd" {
  description = "Monthly spend limit (before credits) that triggers alerts"
  type        = number
  default     = 40
}

variable "alert_email" {
  description = "E-mail that receives budget alerts"
  type        = string
}
