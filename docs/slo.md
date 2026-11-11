# Service Level Objectives: Orders API

SLOs turn "is the service OK?" into numbers that decide when to page someone and when it is safe to ship.

## SLIs and SLOs

| SLI | Definition | SLO |
| --- | --- | --- |
| Availability | Share of `/orders` requests that do not return 5xx | **99.5%** |
| Latency | Share of `/orders` requests answered in under 250 ms | **99%** |

Health checks and `/metrics` are excluded: they measure the platform, not the user experience.

## Error budget

A 99.5% SLO allows 0.5% of requests to fail. Over 30 days, that is about 3.6 hours of full outage. While budget is left, the team ships; when it runs out, reliability work takes priority.

## Alerting: multi-window, multi-burn-rate

Alerts fire on how fast the budget is being consumed, not on single errors (method from the Google SRE Workbook, chapter 5).

| Alert | Burn rate | Windows (both must breach) | Meaning | Severity |
| --- | --- | --- | --- | --- |
| Fast burn | 14.4x | 1 h and 5 min | 2% of the 30-day budget gone in 1 hour | page |
| Slow burn | 6x | 6 h and 30 min | 5% of the budget gone in 6 hours | ticket |

The short window makes the alert stop soon after the problem is fixed; the long window avoids paging on a brief spike.

Two more alerts cover the asynchronous path: `OrdersWorkerFailing` (processing errors, which end in the DLQ) and `OrdersBacklogGrowing` (orders created faster than processed).

## Where it lives

- Recording and alerting rules: [`k8s/observability/slo-rules.yaml`](../k8s/observability/slo-rules.yaml)
- Grafana dashboard **Orders · SLOs**: [`k8s/observability/dashboard.yaml`](../k8s/observability/dashboard.yaml)
- Fault injection for testing the alerts: `FAULT_LATENCY_MS` and `FAULT_ERROR_RATE` environment variables on the API
