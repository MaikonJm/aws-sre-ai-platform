#!/bin/bash
# Sends a steady stream of orders through the ingress so the SLO
# dashboard has data. Usage: ./scripts/generate-traffic.sh [minutes] [requests/second]
set -euo pipefail

MINUTES="${1:-10}"
RPS="${2:-5}"
END=$(( $(date +%s) + MINUTES * 60 ))
ITEMS=(t-shirt hoodie cap mug sticker)

echo "Sending ~$RPS orders/s for $MINUTES minutes (Ctrl+C to stop)"
while [ "$(date +%s)" -lt "$END" ]; do
  for _ in $(seq "$RPS"); do
    ITEM=${ITEMS[$RANDOM % ${#ITEMS[@]}]}
    curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost/orders \
      -H 'content-type: application/json' \
      -d "{\"item\":\"$ITEM\",\"quantity\":$((RANDOM % 5 + 1)),\"amount\":\"$((RANDOM % 200 + 10)).90\"}" &
  done
  wait
  sleep 1
done | sort | uniq -c
