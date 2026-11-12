#!/bin/bash
# Chaos experiments for the orders platform. Run on the node with traffic
# flowing (./scripts/generate-traffic.sh 30 5 in another session).
#
#   ./scripts/chaos.sh start <scenario>   inject the failure and wait for the alert (MTTD)
#   ./scripts/chaos.sh stop  <scenario>   remove the failure and wait for recovery (MTTR)
#
# Scenarios: api-errors | api-latency | worker-down | poison-message | db-down
set -euo pipefail

export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
ACTION="${1:?start|stop}"
SCENARIO="${2:?scenario}"
NS=orders
LOG=chaos-results.log
PROM="http://$(kubectl -n monitoring get svc monitoring-kube-prometheus-prometheus -o jsonpath='{.spec.clusterIP}'):9090"

declare -A ALERT=(
  [api-errors]=OrdersApiAvailabilityFastBurn
  [api-latency]=OrdersApiLatencyFastBurn
  [worker-down]=OrdersBacklogGrowing
  [poison-message]=OrdersWorkerFailing
  [db-down]=OrdersApiAvailabilityFastBurn
)
EXPECTED="${ALERT[$SCENARIO]:?unknown scenario}"

firing() {
  curl -s "$PROM/api/v1/query" --data-urlencode \
    "query=ALERTS{alertname=\"$EXPECTED\",alertstate=\"firing\"}" | grep -q '"result":\[{'
}

wait_until() { # $1 = "firing" | "resolved"
  local start=$(date +%s)
  while true; do
    if [ "$1" = firing ] && firing; then break; fi
    if [ "$1" = resolved ] && ! firing; then break; fi
    sleep 15
    printf '.' >&2
  done
  echo $(( $(date +%s) - start ))
}

inject() {
  case "$SCENARIO" in
    api-errors)     kubectl -n $NS set env deployment/orders-api FAULT_ERROR_RATE=0.5 ;;
    api-latency)    kubectl -n $NS set env deployment/orders-api FAULT_LATENCY_MS=400 ;;
    worker-down)    kubectl -n $NS scale deployment/worker --replicas=0 ;;
    poison-message) for _ in 1 2 3; do
                      curl -s -X POST localhost/orders -H 'content-type: application/json' \
                        -d '{"item":"poison","quantity":1,"amount":"-1"}'; echo
                    done ;;
    db-down)        kubectl -n $NS scale statefulset/postgres --replicas=0 ;;
  esac
}

recover() {
  case "$SCENARIO" in
    api-errors)     kubectl -n $NS set env deployment/orders-api FAULT_ERROR_RATE- ;;
    api-latency)    kubectl -n $NS set env deployment/orders-api FAULT_LATENCY_MS- ;;
    worker-down)    kubectl -n $NS scale deployment/worker --replicas=1 ;;
    poison-message) echo "Poison messages stay in the DLQ for analysis (14 days)." ;;
    db-down)        kubectl -n $NS scale statefulset/postgres --replicas=1 ;;
  esac
}

case "$ACTION" in
  start)
    # Without traffic the SLIs have no data and burn-rate alerts resolve on
    # their own, which looked like a broken pipeline in the first test.
    if ! pgrep -f generate-traffic.sh >/dev/null; then
      echo "WARNING: no traffic generator running. Start one first:" >&2
      echo "  nohup ./scripts/generate-traffic.sh 60 5 > traffic.log 2>&1 &" >&2
    fi
    echo "$(date -Is) START $SCENARIO (expecting $EXPECTED)" | tee -a "$LOG"
    inject
    echo -n "Waiting for $EXPECTED to fire" >&2
    SECS=$(wait_until firing)
    echo; echo "$(date -Is) FIRING $EXPECTED after ${SECS}s (time to detect)" | tee -a "$LOG"
    echo "The SRE agent is investigating; check GitHub issues or: kubectl -n sre-agent logs deploy/sre-agent"
    ;;
  stop)
    echo "$(date -Is) RECOVER $SCENARIO" | tee -a "$LOG"
    recover
    echo -n "Waiting for $EXPECTED to resolve" >&2
    SECS=$(wait_until resolved)
    echo; echo "$(date -Is) RESOLVED $EXPECTED after ${SECS}s (time to recover)" | tee -a "$LOG"
    ;;
  *) echo "usage: $0 start|stop <scenario>"; exit 1 ;;
esac
