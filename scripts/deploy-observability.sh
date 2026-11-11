#!/bin/bash
# Installs Prometheus, Alertmanager and Grafana (kube-prometheus-stack)
# plus the SLO rules and dashboard. Run it on the node after deploy-app.sh.
# Needs about 4 GB of RAM: use instance_type = "c7i-flex.large".
set -euo pipefail

export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHART_VERSION="${CHART_VERSION:-^67.0.0}" # pinned major version

kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

# Grafana admin password: generated once, never stored in Git
if ! kubectl -n monitoring get secret grafana-admin >/dev/null 2>&1; then
  kubectl -n monitoring create secret generic grafana-admin \
    --from-literal=admin-user=admin \
    --from-literal=admin-password="$(openssl rand -hex 16)"
fi

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null
helm repo update >/dev/null
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --version "$CHART_VERSION" \
  --values "$REPO_ROOT/k8s/observability/values.yaml" \
  --wait --timeout 10m

kubectl apply -f "$REPO_ROOT/k8s/observability/podmonitors.yaml"
kubectl apply -f "$REPO_ROOT/k8s/observability/slo-rules.yaml"
kubectl apply -f "$REPO_ROOT/k8s/observability/dashboard.yaml"

PUBLIC_IP=$(curl -s -H "X-aws-ec2-metadata-token: $(curl -s -X PUT http://169.254.169.254/latest/api/token \
  -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')" http://169.254.169.254/latest/meta-data/public-ipv4)
echo
echo "Grafana:  http://$PUBLIC_IP/grafana  (user: admin)"
echo "Password: kubectl -n monitoring get secret grafana-admin -o jsonpath='{.data.admin-password}' | base64 -d"
