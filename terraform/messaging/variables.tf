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

variable "alert_email" {
  description = "E-mail that receives alerts when messages land in the DLQ"
  type        = string
}

variable "max_receive_count" {
  description = "Delivery attempts before a message is moved to the DLQ"
  type        = number
  default     = 3
}
