# ADR 0001: Kubernetes runtime on a limited budget

- **Status:** Proposed
- **Date:** 2026-11-10

## Context

The platform runs on an AWS account with about US$ 133 in credits and 87 days left. Kubernetes is central to the project (deployments, autoscaling, GitOps and the AI SRE agent). Amazon EKS charges for the control plane every hour the cluster exists, plus worker nodes, a load balancer and, if used, a NAT gateway.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| Amazon EKS (managed) | What most companies run in production; IAM integration (IRSA / Pod Identity) | Control plane billed per hour; easy to burn credits if left running |
| k3s on a single EC2 instance | Lowest cost; full Kubernetes API; same manifests and Helm charts | Not managed; single node, no control plane HA |

## Decision

To be confirmed after checking which services the account plan allows. Guardrails apply either way:

- Every working session ends with `terraform destroy`.
- No NAT gateway: nodes in public subnets with locked-down security groups, or VPC endpoints.
- AWS Budgets alerts at 50%, 80% and 100% of US$ 40/month (`terraform/bootstrap`).

## Consequences

The application, GitOps and observability layers are written against the Kubernetes API only, so they run unchanged on either option.
