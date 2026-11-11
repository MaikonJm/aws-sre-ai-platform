# ADR 0001: Kubernetes runtime on a limited budget

- **Status:** Accepted
- **Date:** 2026-11-11

## Context

The platform runs on an AWS account with about US$ 133 in credits and 87 days left. Kubernetes is central to the project (deployments, autoscaling, GitOps and the AI SRE agent). Amazon EKS charges for the control plane every hour the cluster exists, plus worker nodes, a load balancer and, if used, a NAT gateway.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| Amazon EKS (managed) | What most companies run in production; IAM integration (IRSA / Pod Identity) | Control plane billed per hour; easy to burn credits if left running |
| k3s on a single EC2 instance | Lowest cost; full Kubernetes API; same manifests and Helm charts | Not managed; single node, no control plane HA |

## Decision

**k3s on a single EC2 instance** (`t3.small` by default, Ubuntu 24.04), restricted to AWS Free plan eligible instance types.

- Cost: one `t3.small` costs about US$ 0.02/hour, paid from credits, versus the EKS control plane plus nodes.
- Availability: works on the AWS Free plan, which may restrict managed services.
- Portability: k3s is a certified Kubernetes distribution, so manifests, Helm charts and ArgoCD work the same as on EKS.
- Access without SSH: the node is managed through SSM Session Manager; the Kubernetes API is not exposed to the internet.

Guardrails:

- Every working session ends with `terraform destroy`.
- No NAT gateway: nodes in public subnets with locked-down security groups, or VPC endpoints.
- AWS Budgets alerts at 50%, 80% and 100% of US$ 40/month (`terraform/bootstrap`).

## Consequences

The application, GitOps and observability layers are written against the Kubernetes API only, so moving to EKS later means replacing one Terraform stack. The trade-off accepted for this project is a single node with no control-plane high availability; in production this would be EKS across at least two Availability Zones.
