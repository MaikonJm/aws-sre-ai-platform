# Chaos experiments

Each experiment states a hypothesis, injects one failure with `scripts/chaos.sh`, and measures **time to detect** (failure injected → alert firing) and **time to recover** (failure removed → alert resolved). Run them with traffic flowing: `./scripts/generate-traffic.sh 30 5`.

| # | Scenario | Hypothesis | Expected alert | Expected agent finding |
| --- | --- | --- | --- | --- |
| 1 | `api-errors` | 50% of `/orders` requests fail; the availability budget burns fast | `OrdersApiAvailabilityFastBurn` (page) | `FAULT_ERROR_RATE` set on `orders-api` |
| 2 | `api-latency` | Every request takes +400 ms; the latency SLO burns fast | `OrdersApiLatencyFastBurn` (page) | `FAULT_LATENCY_MS` set, p95 above 250 ms |
| 3 | `worker-down` | Orders keep arriving but nothing processes them; the queue grows | `OrdersBacklogGrowing` (page) | `worker` scaled to 0, queue depth rising |
| 4 | `poison-message` | Invalid orders fail 3 times and land in the DLQ; the CloudWatch alarm e-mails | `OrdersWorkerFailing` (ticket) + DLQ alarm e-mail | invalid amount in worker logs, DLQ not empty |
| 5 | `db-down` | PostgreSQL is gone; the API returns 5xx and readiness fails | `OrdersApiAvailabilityFastBurn` (page) | database connection errors in API logs |

## Results

Filled in from `chaos-results.log` during the test session.

| # | Time to detect | Time to recover | Agent diagnosis correct? | Issue |
| --- | --- | --- | --- | --- |
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |

## Why detection takes minutes, not seconds

The fast-burn alert needs the error ratio above 7.2% (14.4 × the 0.5% budget) over **both** the last 5 minutes and the last hour. The long window prevents paging on a brief spike, at the cost of a few minutes of detection time. That is a deliberate trade-off from the SLO design ([slo.md](slo.md)).
