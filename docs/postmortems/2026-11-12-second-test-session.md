# Post-mortem: second test session on AWS

- **Date:** 2026-11-12 (session 13:35–15:45 BRT, timeline in UTC)
- **Status:** final
- **Severity:** page and ticket (`worker-down` and `poison-message`, injected on purpose)
- **Authors:** Maikon Marquez

> Blameless: this document is about how the system and the process allowed each problem, not about who did what.

## Summary

The second session rebuilt the cluster from scratch and ran two more chaos scenarios: `worker-down` (the worker scaled to 0) and `poison-message` (orders with a negative amount). Both were detected in under 4 minutes and both ended with a correct AI diagnosis, but only after the session found and fixed seven more problems: two in node bootstrap, one silent alert, one stale-data surprise, and three in the evidence the agent gives the model. Every fix shipped through CI during the session.

## Impact

- `worker-down`: orders kept being accepted (all three SLOs stayed at 100%) but nothing processed them; the backlog reached about 1,940 orders before recovery. Customers would see orders stuck in `pending`, a failure the API SLOs cannot see.
- `poison-message`: 3 invalid orders per run ended in the Dead Letter Queue after 3 attempts each; valid orders were not affected.
- 3,657 orders left in SQS by the first session were dropped into the DLQ (see root cause 4).

## Results

| Scenario | Time to detect | AI diagnosis, first run | AI diagnosis after fixes | Issue |
| --- | --- | --- | --- | --- |
| `worker-down` | 225 s (`OrdersWorkerUnavailable`); recovered 45 s after the fix | Wrong: probe failures; proposed `rollout restart` | Right: worker scaled to 0; `kubectl -n orders scale deployment/worker --replicas=1` | [#22](https://github.com/MaikonJm/aws-sre-ai-platform/issues/22) → [#26](https://github.com/MaikonJm/aws-sre-ai-platform/issues/26) |
| `poison-message` | 150 s (`OrdersWorkerFailing`), same in all 3 runs; recovery n/a, the messages stay in the DLQ for analysis | Vague: "processing issue", medium confidence | Right: invalid amount -1, high confidence, no command proposed | [#28](https://github.com/MaikonJm/aws-sre-ai-platform/issues/28) → [#32](https://github.com/MaikonJm/aws-sre-ai-platform/issues/32) |

The DLQ alarm e-mail arrived about 2 minutes after the poison messages reached the DLQ. Each investigation used 2,800–5,300 input tokens and answered in about 1 s.

## Timeline (UTC, 12 Nov 2026)

| Time | Event |
| --- | --- |
| 16:38 | Cluster created; cloud-init fails at `snap install aws-cli` (snap store unreachable) |
| 16:46 | Retry for the snap install merged ([#20](https://github.com/MaikonJm/aws-sre-ai-platform/pull/20)); the store keeps timing out |
| 16:50 | AWS CLI from the official installer instead of snap ([#21](https://github.com/MaikonJm/aws-sre-ai-platform/pull/21)); node finished by hand |
| 16:53 | Application deployed; API pods start with 0 restarts (startup retry from session 1 works) |
| 16:59 | DLQ holds 3,657 messages: orders from session 1 whose rows died with the old database |
| 17:01 | DLQ alarm e-mail (CloudWatch → SNS) |
| 17:01:55 | `worker-down` injected |
| 17:07:41 | `OrdersBacklogGrowing` fires (345 s; the rule waits for 20 orders plus 5 minutes) |
| 17:07:58 | Agent opens [#22](https://github.com/MaikonJm/aws-sre-ai-platform/issues/22): blames probe failures (wrong) |
| 17:11 | Fix merged: scaled-to-zero signal, events of healthy pods dropped ([#23](https://github.com/MaikonJm/aws-sre-ai-platform/pull/23)) |
| ~17:12 | `OrdersBacklogGrowing` resolves by itself while the worker is still down |
| 17:39:14 | Worker restored; the alert had already resolved, so `chaos.sh` measured 0 s; the backlog drains at ~3,600 orders/min |
| 17:50 | Fix merged: backlog rule survives a missing worker; new `OrdersWorkerUnavailable` ([#24](https://github.com/MaikonJm/aws-sre-ai-platform/pull/24)) |
| 17:51:43 | `worker-down` injected again |
| 17:55:28 | `OrdersWorkerUnavailable` fires (**time to detect: 225 s**) |
| 17:55:58 | [#25](https://github.com/MaikonJm/aws-sre-ai-platform/issues/25): right cause, invalid command that printed the AWS account ID |
| 17:57:58 | [#26](https://github.com/MaikonJm/aws-sre-ai-platform/issues/26): right cause and exact fix command |
| 18:01 | Fix merged: account IDs redacted, invented flags rejected ([#27](https://github.com/MaikonJm/aws-sre-ai-platform/pull/27)) |
| 18:10:45 | Worker restored |
| 18:11:31 | `OrdersWorkerUnavailable` resolves (**time to recover: 45 s**) |
| 18:13:38 | `poison-message` injected |
| 18:16:08 | `OrdersWorkerFailing` fires (150 s) |
| 18:16:28 | [#28](https://github.com/MaikonJm/aws-sre-ai-platform/issues/28): vague diagnosis, medium confidence |
| 18:18:08 | DLQ alarm e-mail |
| 18:19 | Fix merged: worker logs always collected ([#29](https://github.com/MaikonJm/aws-sre-ai-platform/pull/29)) |
| 18:26:58 | [#30](https://github.com/MaikonJm/aws-sre-ai-platform/issues/30): still vague |
| 18:31 | Fix merged: 500-line log window, error lines kept ([#31](https://github.com/MaikonJm/aws-sre-ai-platform/pull/31)) |
| 18:38:39 | `poison-message` injected again |
| 18:41:09 | `OrdersWorkerFailing` fires (**time to detect: 150 s**) |
| 18:41:28 | [#32](https://github.com/MaikonJm/aws-sre-ai-platform/issues/32): invalid amount -1, high confidence |

## Root causes

1. **Node bootstrap depended on the snap store.** `snap install aws-cli` ran before snapd finished seeding and then kept timing out. With `set -e`, the script stopped before it created the ECR pull-secret timer. A retry was not enough; the official AWS installer removed the dependency.
2. **The agent missed "scaled to 0".** The replica signal fired only when ready < desired. With desired = 0 nothing looked wrong, and probe failures from the deploy 14 minutes earlier, on API pods that were healthy by then, filled the evidence.
3. **The backlog alert went quiet during the outage.** With the worker gone, `orders_processed_total` disappears, and `created - processed` became an empty result instead of a large one. The alert resolved about 10 minutes into the outage. Same class of bug as the "No data" panels in session 1: a missing series is not zero unless the query says so.
4. **Queue state outlived the database.** `terraform destroy` removes the node and its PostgreSQL data, but the SQS queue lives in another stack. Orders still in flight at the end of session 1 were consumed by the new worker, not found in the new database, and moved to the DLQ.
5. **The model invented a flag and leaked the account ID.** Issue #25 proposed `kubectl scale ... --image=<account>.dkr.ecr...`: `scale` has no `--image`, and the image URL carried the account ID into a public issue.
6. **The worker's logs never reached the model.** Logs came from unhealthy pods or the first two healthy ones, which were both API pods.
7. **A 40-line log tail covered 8 seconds.** The worker logs one line per order (~5/s), so the "invalid amount" errors from two minutes earlier had scrolled out.

## What went well

- Detection worked for every scenario once the alert gap was closed: 225 s and 150 s.
- The SLOs stayed green during `worker-down`, which is correct: the API was healthy. The dedicated worker and backlog alerts are what caught it, and that split is worth explaining in the write-up.
- The token flow through SSM Parameter Store worked on the first try, and `deploy-agent.sh` confirmed the permission before any incident.
- The read-only design held through three wrong or incomplete diagnoses: nothing was changed without a human.

## What went wrong

- Seven defects in one session; four were in the agent's evidence, not in the model.
- An AWS account ID was published in a public issue before the redaction existed.
- The CloudShell session dropped mid-test. Together with the silent backlog alert, the first `worker-down` run produced no usable recovery time.

## Action items

| Action | Type | Status |
| --- | --- | --- |
| Install the AWS CLI with the official installer | prevent | Done ([#20](https://github.com/MaikonJm/aws-sre-ai-platform/pull/20), [#21](https://github.com/MaikonJm/aws-sre-ai-platform/pull/21)) |
| Signal for deployments scaled to 0; drop events of healthy pods | mitigate | Done ([#23](https://github.com/MaikonJm/aws-sre-ai-platform/pull/23)) |
| Backlog rule with `or vector(0)`; `OrdersWorkerUnavailable` alert | detect | Done ([#24](https://github.com/MaikonJm/aws-sre-ai-platform/pull/24)) |
| Redact account IDs; reject invented flags | prevent | Done ([#27](https://github.com/MaikonJm/aws-sre-ai-platform/pull/27)) |
| Always collect worker logs; log errors as signals; 500-line window | mitigate | Done ([#29](https://github.com/MaikonJm/aws-sre-ai-platform/pull/29), [#31](https://github.com/MaikonJm/aws-sre-ai-platform/pull/31)) |
| Purge the orders queue on `terraform destroy`, or keep the database outside the node | prevent | Open |
| Add a rule check to CI that fails when a query can return "no data" for a missing series | detect | Open |
| Run `api-latency` and `db-down` | — | Open |
