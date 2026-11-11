#!/bin/bash
# Deploys the AI SRE agent and points Alertmanager at it.
# Run on the node after deploy-app.sh and deploy-observability.sh.
#   GITHUB_TOKEN=github_pat_... ./scripts/deploy-agent.sh   # issues on GitHub (optional)
set -euo pipefail

export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
export AWS_REGION="${AWS_REGION:-us-east-1}"
PROJECT=aws-sre-ai-platform
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGISTRY="$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
TAG="${1:-$(aws ecr describe-images --repository-name "$PROJECT/sre-agent" \
  --query 'sort_by(imageDetails, &imagePushedAt)[-1].imageTags[0]' --output text)}"
echo "Deploying sre-agent:$TAG"

kubectl create namespace sre-agent --dry-run=client -o yaml | kubectl apply -f -

kubectl -n sre-agent create configmap sre-agent-config \
  --from-literal=AWS_REGION="$AWS_REGION" \
  --from-literal=BEDROCK_MODEL_ID="${BEDROCK_MODEL_ID:-us.amazon.nova-micro-v1:0}" \
  --from-literal=TARGET_NAMESPACE=orders \
  --from-literal=QUEUE_NAMES="$PROJECT-orders,$PROJECT-orders-dlq" \
  --from-literal=GITHUB_REPOSITORY="${GITHUB_REPOSITORY:-MaikonJm/$PROJECT}" \
  --dry-run=client -o yaml | kubectl apply -f -

if [ -n "${GITHUB_TOKEN:-}" ]; then
  kubectl -n sre-agent create secret generic sre-agent-github \
    --from-literal=token="$GITHUB_TOKEN" --dry-run=client -o yaml | kubectl apply -f -
fi

# Pull secret in the agent namespace too
NAMESPACES="orders sre-agent" /usr/local/bin/refresh-ecr-secret

WORK=$(mktemp -d)
cp "$REPO_ROOT"/k8s/sre-agent/*.yaml "$WORK/"
cat >> "$WORK/kustomization.yaml" <<IMAGES
images:
  - name: sre-agent
    newName: $REGISTRY/$PROJECT/sre-agent
    newTag: "$TAG"
IMAGES
kubectl apply -k "$WORK"
rm -rf "$WORK"
kubectl -n sre-agent rollout status deployment/sre-agent --timeout=180s
echo "Agent ready. Reports: kubectl -n sre-agent port-forward svc/sre-agent 8080 & curl localhost:8080/reports"
