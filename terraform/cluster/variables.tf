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

variable "state_bucket" {
  description = "Remote-state bucket created by the bootstrap stack"
  type        = string
}

variable "instance_type" {
  description = "Instance type of the k3s node. Only AWS Free plan eligible types are allowed."
  type        = string
  default     = "t3.small" # 2 vCPU, 2 GB: enough for k3s and the application

  validation {
    condition = contains(
      ["t3.micro", "t3.small", "c7i-flex.large", "m7i-flex.large"],
      var.instance_type
    )
    error_message = "Use a Free plan eligible x86 type: t3.micro, t3.small, c7i-flex.large or m7i-flex.large."
  }
}

variable "k3s_version" {
  description = "k3s release to install (pinned for reproducible clusters)"
  type        = string
  default     = "v1.31.4+k3s1"
}

variable "root_volume_gb" {
  description = "Size of the node's root disk"
  type        = number
  default     = 30
}
