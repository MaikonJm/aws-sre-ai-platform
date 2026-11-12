# Post-mortem: first end-to-end test on AWS

- **Date:** 2026-11-11 (session 21:00–23:30 BRT, timeline in UTC)
- **Status:** final
- **Severity:** page (`OrdersApiAvailabilityFastBurn`, injected on purpose)
- **Authors:** Maikon Marquez

> Blameless: this document is about how the system and the process allowed each problem, not about who did what.

## Summary

The first full run on AWS injected a 50% error rate into the Orders API (chaos scenario `api-errors`). The burn-rate alert fired in 135 s and the system recovered 315 s after the fault was removed. The path from alert to AI investigation to GitHub issue failed in four places before it worked; each failure was silent, and each was fixed in its own pull request during the session. The final run produced [issue #14](https://github.com/MaikonJm/aws-sre-ai-platform/issues/14) with the correct root cause.

## Impact

- Requests failed: about 50% of `POST /orders` while the fault was active (lab traffic only, ~5 req/s).
- Availability (1 h) dropped to 71.27% against a 99.5% SLO; the 6 h error budget reached 0%. The cluster had only ~15 minutes of history, so the budget drained much faster than it would in production.
- Latency SLO unaffected: p95 stayed near 49 ms.

## Timeline (UTC, 12 Nov 2026)

| Time | Event |
| --- | --- |
| 00:03 | Observability stack deployed; traffic generator started |
| ~00:05 | Grafana shows "No data" for availability and error budget while the system is healthy (bug 1) |
| 00:10 | Fix merged: no 5xx series counts as zero errors ([#10](https://github.com/MaikonJm/aws-sre-ai-platform/pull/10)) |
| 00:20:12 | Fault injected: `FAULT_ERROR_RATE=0.5` |
| 00:22:28 | `OrdersApiAvailabilityFastBurn` fires (**time to detect: 135 s**) |
| ~00:25 | No investigation: the alert was routed to the `null` receiver (bug 2) |
| 00:28 | Fix merged: alerts carry `namespace: orders` ([#11](https://github.com/MaikonJm/aws-sre-ai-platform/pull/11)) |
| 00:30:26 | Alerts reach the agent; Bedrock blames probe failures, which is wrong (bug 3); no GitHub token yet |
| 01:01 | Fix merged: deterministic signals and recent events only ([#12](https://github.com/MaikonJm/aws-sre-ai-platform/pull/12)) |
| 01:06:47 | Fault removed |
| 01:12:02 | Alert resolved (**time to recover: 315 s**); fault injected again |
| ~01:20 | Alert fires again but Alertmanager does not re-send it (bug 4) |
| 01:26 | Fix merged: `send_resolved: true` ([#13](https://github.com/MaikonJm/aws-sre-ai-platform/pull/13)) |
| ~01:45 | Agent investigates; GitHub answers 403: the token had read-only access |
| ~02:05 | Traffic generator ends; with no requests the alerts resolve by themselves |
| 02:16:26 | Traffic restarted; alerts fire with a correctly scoped token in place |
| 02:16:58 | Agent opens [#14](https://github.com/MaikonJm/aws-sre-ai-platform/issues/14) and [#15](https://github.com/MaikonJm/aws-sre-ai-platform/issues/15) with the correct root cause |
| 02:26:15 | Fault removed |

## Root cause

The outage itself was the injected fault. The interesting failures were in the detection and response path:

1. **"No data" on healthy dashboards.** In PromQL, `errors / total` returns nothing when the 5xx series does not exist yet, so a perfectly healthy service looked broken.
2. **Alerts never reached the agent.** The SLO rules aggregate with `sum()`, which drops every label. The Alertmanager route matches on `namespace = "orders"`, so the alerts fell through to the `null` receiver without any error.
3. **Wrong AI diagnosis.** The evidence included warning events from the rollout that applied the fault (readiness probes refused while pods restarted). Nova Micro read those as the cause and missed one `FAULT_ERROR_RATE` line in a large JSON.
4. **No re-notification.** With `send_resolved: false`, Alertmanager never records that an alert resolved. When the same alert fired again, it matched the last notification and would only repeat after `repeat_interval` (4 h).

## Detection

The fast-burn alert needs both the 5-minute and the 1-hour error ratio above 7.2%. The 5-minute window crossed in seconds; the 1-hour window took about two minutes. 135 s is acceptable for a page and is the price of not paging on short spikes.

Bugs 2 and 4 were not detected by anything: they were found by reading Alertmanager's routes and notification metrics by hand.

## AI agent assessment

| Run | Root cause given | Correct? | Why |
| --- | --- | --- | --- |
| 1 | Readiness and liveness probe failures | No | Stale events dominated the evidence; the fault env var was buried |
| 2 | Fault injection enabled, `FAULT_ERROR_RATE=0.5` | Yes, high confidence | Code-computed signals listed the env var first; events limited to 15 min |

The correct run still proposed `kubectl edit deployment orders-api`, an interactive command that cannot be reviewed as written. Each investigation cost 4,614 input and 173 output tokens and took 0.89 s on Bedrock.

## What went well

- Burn-rate alerting behaved as designed: fast enough, no false page.
- Read-only design held: the agent changed nothing, even when its diagnosis was wrong.
- Every bug was reproduced, fixed and merged through CI in under 30 minutes.

## What went wrong

- Four silent failures between "alert fires" and "engineer gets a report"; none produced an error anywhere.
- The GitHub token setup relied on pasting a secret into a browser terminal, which joined lines and failed silently; a token also ended up in chat and screenshots and had to be revoked.
- The fine-grained token defaulted to read-only access, and nothing checked it before the first incident.
- The traffic generator stopped mid-test, which looked like another pipeline failure.

## Action items

| Action | Type | Status |
| --- | --- | --- |
| Treat a missing 5xx series as zero errors | detect | Done ([#10](https://github.com/MaikonJm/aws-sre-ai-platform/pull/10)) |
| Label every alert with `namespace` | detect | Done ([#11](https://github.com/MaikonJm/aws-sre-ai-platform/pull/11)) |
| Deterministic signals before the LLM; events from the last 15 min only | mitigate | Done ([#12](https://github.com/MaikonJm/aws-sre-ai-platform/pull/12)) |
| `send_resolved: true` on the agent webhook | detect | Done ([#13](https://github.com/MaikonJm/aws-sre-ai-platform/pull/13)) |
| Discard interactive commands; ask for complete `kubectl` commands | mitigate | Done ([#17](https://github.com/MaikonJm/aws-sre-ai-platform/pull/17)) |
| API retries the database at startup instead of crashing | prevent | Done ([#17](https://github.com/MaikonJm/aws-sre-ai-platform/pull/17)) |
| Read the GitHub token from SSM Parameter Store and verify its permission on deploy | prevent | Done (this PR) |
| Warn when a chaos experiment starts without traffic | detect | Done (this PR) |
| Alert when the agent's investigations fail (`sre_agent_investigations_total{outcome="error"}`) | detect | Open |
| Alert when Alertmanager drops SLO alerts to the `null` receiver | detect | Open |
| Run scenarios 2–5 (`api-latency`, `worker-down`, `poison-message`, `db-down`) | — | Open |
