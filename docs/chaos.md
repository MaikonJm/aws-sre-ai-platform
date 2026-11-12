# Chaos experiments

Each experiment states a hypothesis, injects one failure with `scripts/chaos.sh`, and measures **time to detect** (failure injected → alert firing) and **time to recover** (failure removed → alert resolved). Run them with traffic flowing: `./scripts/generate-traffic.sh 30 5`.

| # | Scenario | Hypothesis | Expected alert | Expected agent finding |
| --- | --- | --- | --- | --- |
| 1 | `api-errors` | 50% of `/orders` requests fail; the availability budget burns fast | `OrdersApiAvailabilityFastBurn` (page) | `FAULT_ERROR_RATE` set on `orders-api` |
| 2 | `api-latency` | Every request takes +400 ms; the latency SLO burns fast | `OrdersApiLatencyFastBurn` (page) | `FAULT_LATENCY_MS` set, p95 above 250 ms |
| 3 | `worker-down` | Orders keep arriving but nothing processes them; the queue grows | `OrdersWorkerUnavailable` + `OrdersBacklogGrowing` (page) | `worker` scaled to 0, queue depth rising |
| 4 | `poison-message` | Invalid orders fail 3 times and land in the DLQ; the CloudWatch alarm e-mails | `OrdersWorkerFailing` (ticket) + DLQ alarm e-mail | invalid amount in worker logs, DLQ not empty |
| 5 | `db-down` | PostgreSQL is gone; the API returns 5xx and readiness fails | `OrdersApiAvailabilityFastBurn` (page) | database connection errors in API logs |

## Results

From `chaos-results.log`. Session 1 (11 Nov 2026) covered scenario 1 and session 2 (12 Nov) scenarios 3 and 4; the post-mortems ([session 1](postmortems/2026-11-11-first-end-to-end-test.md), [session 2](postmortems/2026-11-12-second-test-session.md)) have the timelines and the eleven bugs the runs uncovered.

| # | Time to detect | Time to recover | Agent diagnosis correct? | Issue |
| --- | --- | --- | --- | --- |
| 1 | 135 s | 315 s | First run no (stale probe failures); after [deterministic signals](sre-agent.md#deterministic-signals), yes: `FAULT_ERROR_RATE=0.5`, high confidence | [#14](https://github.com/MaikonJm/aws-sre-ai-platform/issues/14) |
| 2 | not run | | | |
| 3 | 225 s (`OrdersWorkerUnavailable`) | 45 s | First run no (probe failures, `rollout restart`); after the scaled-to-zero signal, yes, with `kubectl -n orders scale deployment/worker --replicas=1` | [#26](https://github.com/MaikonJm/aws-sre-ai-platform/issues/26) |
| 4 | 150 s (+ DLQ alarm e-mail ~2 min later) | n/a: messages stay in the DLQ | First two runs vague; after worker logs and a 500-line window, yes: invalid amount -1, high confidence | [#32](https://github.com/MaikonJm/aws-sre-ai-platform/issues/32) |
| 5 | not run | | | |

Run every scenario with one traffic generator active for longer than the experiment: without requests the SLIs have no data and the alerts resolve by themselves. `chaos.sh start` warns when no generator is running.

## Why detection takes minutes, not seconds

The fast-burn alert needs the error ratio above 7.2% (14.4 × the 0.5% budget) over **both** the last 5 minutes and the last hour. The long window prevents paging on a brief spike, at the cost of a few minutes of detection time. That is a deliberate trade-off from the SLO design ([slo.md](slo.md)).
