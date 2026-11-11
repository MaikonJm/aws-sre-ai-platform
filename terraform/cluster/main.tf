# Single-node k3s cluster on EC2 (decision in docs/adr/0001).
# No SSH and no open Kubernetes API: access goes through SSM Session Manager.

data "terraform_remote_state" "foundation" {
  backend = "s3"

  config = {
    bucket = var.state_bucket
    key    = "foundation/terraform.tfstate"
    region = var.region
  }
}

locals {
  vpc_id    = data.terraform_remote_state.foundation.outputs.vpc_id
  subnet_id = data.terraform_remote_state.foundation.outputs.public_subnet_ids[0]
}

# Latest Ubuntu 24.04 LTS AMI published by Canonical
data "aws_ssm_parameter" "ubuntu" {
  name = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
}

# ---------- Network access ----------

resource "aws_security_group" "node" {
  name        = "${var.project}-k3s-node"
  description = "k3s node: HTTP/HTTPS ingress only, no SSH, no public API"
  vpc_id      = local.vpc_id

  tags = { Name = "${var.project}-k3s-node" }
}

resource "aws_vpc_security_group_ingress_rule" "http" {
  security_group_id = aws_security_group.node.id
  description       = "Ingress controller (Traefik) - HTTP"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_ingress_rule" "https" {
  security_group_id = aws_security_group.node.id
  description       = "Ingress controller (Traefik) - HTTPS"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.node.id
  description       = "Outbound: packages, images, AWS APIs"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# ---------- Node identity ----------

data "aws_iam_policy_document" "ec2_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "node" {
  name               = "${var.project}-k3s-node"
  assume_role_policy = data.aws_iam_policy_document.ec2_trust.json
}

# Session Manager access instead of SSH keys
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Pull application images from the project's ECR repositories
resource "aws_iam_role_policy_attachment" "ecr_read" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_instance_profile" "node" {
  name = "${var.project}-k3s-node"
  role = aws_iam_role.node.name
}

# ---------- The node ----------

resource "aws_instance" "k3s" {
  ami                    = data.aws_ssm_parameter.ubuntu.value
  instance_type          = var.instance_type
  subnet_id              = local.subnet_id
  vpc_security_group_ids = [aws_security_group.node.id]
  iam_instance_profile   = aws_iam_instance_profile.node.name

  user_data = templatefile("${path.module}/user-data.sh.tftpl", {
    k3s_version = var.k3s_version
    region      = var.region
  })
  user_data_replace_on_change = true

  # IMDSv2 only: blocks SSRF-style credential theft
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  root_block_device {
    volume_size = var.root_volume_gb
    volume_type = "gp3"
    encrypted   = true
  }

  tags = { Name = "${var.project}-k3s" }

  lifecycle {
    ignore_changes = [ami] # a new AMI must not recreate the cluster by surprise
  }
}

# ---------- Application permissions ----------
# On k3s there is no IRSA/Pod Identity, so the pods use the node role.
# Permissions stay scoped to the project's queues only.
# In production (EKS) this would move to a per-service role.

data "terraform_remote_state" "messaging" {
  backend = "s3"

  config = {
    bucket = var.state_bucket
    key    = "messaging/terraform.tfstate"
    region = var.region
  }
}

data "aws_iam_policy_document" "orders_queue" {
  statement {
    sid = "OrdersQueue"
    actions = [
      "sqs:SendMessage",
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:ChangeMessageVisibility",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
    ]
    resources = [data.terraform_remote_state.messaging.outputs.orders_queue_arn]
  }

  statement {
    sid       = "InspectDlq"
    actions   = ["sqs:ReceiveMessage", "sqs:GetQueueAttributes", "sqs:GetQueueUrl"]
    resources = [data.terraform_remote_state.messaging.outputs.orders_dlq_arn]
  }
}

resource "aws_iam_role_policy" "orders_queue" {
  name   = "orders-queue"
  role   = aws_iam_role.node.id
  policy = data.aws_iam_policy_document.orders_queue.json
}

# ---------- AI SRE agent: one model, invoke only ----------

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "bedrock" {
  statement {
    sid     = "InvokeAgentModel"
    actions = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = [
      "arn:aws:bedrock:${var.region}:${data.aws_caller_identity.current.account_id}:inference-profile/us.${var.bedrock_model_id}",
      # the US inference profile may route the call to any US region
      "arn:aws:bedrock:*::foundation-model/${var.bedrock_model_id}",
    ]
  }
}

resource "aws_iam_role_policy" "bedrock" {
  name   = "bedrock-agent-model"
  role   = aws_iam_role.node.id
  policy = data.aws_iam_policy_document.bedrock.json
}
