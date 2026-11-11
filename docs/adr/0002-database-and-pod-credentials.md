# ADR 0002: Database and AWS credentials for the application

- **Status:** Accepted
- **Date:** 2026-11-11

## Context

Phase 2 adds an orders API and a worker that need a PostgreSQL database and access to Amazon SQS. The project runs on limited AWS credits and on a single-node k3s cluster (ADR 0001).

## Decisions

### PostgreSQL inside the cluster

A `StatefulSet` with a 2 GB volume (k3s `local-path` storage) instead of Amazon RDS.

- RDS bills per hour plus storage and backups; the in-cluster database costs nothing extra.
- The application only depends on a PostgreSQL endpoint, so switching to RDS means changing `DB_HOST` and the secret.
- Trade-off: no automated backups, no Multi-AZ, data is lost when the cluster is destroyed. Acceptable for a lab; in production this is RDS Multi-AZ.

### Node role instead of per-pod roles

k3s on EC2 has no IRSA or EKS Pod Identity, so pods use the node's IAM role. The SQS permissions are scoped to the project's queues only, and the role can only pull images (ECR read-only).

- Trade-off: every pod on the node shares the same AWS permissions. In production (EKS), each service gets its own role through Pod Identity.

### Secrets

The database password is generated on the node (`openssl rand`) and stored as a Kubernetes Secret; it never appears in Git. ECR pull credentials expire after 12 hours and are refreshed every 6 hours by a systemd timer using the node role.
