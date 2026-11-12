#!/bin/bash
# Deploys the AI SRE agent and points Alertmanager at it.
# Run on the node after deploy-app.sh and deploy-observability.sh.
#
# GitHub issues are optional. The token (fine-grained, this repository only,
# Issues: read and write) is read from SSM Parameter Store, so it is never
# pasted into a terminal:
#   aws ssm put-parameter --name /sre-platform/github-token --type SecureString --value ...
#   (or create it in the console: Systems Manager > Parameter Store)
# GITHUB_TOKEN=... in the environment still works and takes precedence.
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

TOKEN_PARAM="${GITHUB_TOKEN_PARAM:-/sre-platform/github-token}"
if [ -z "${GITHUB_TOKEN:-}" ]; then
  GITHUB_TOKEN=$(aws ssm get-parameter --name "$TOKEN_PARAM" --with-decryption \
    --query Parameter.Value --output text 2>/dev/null || true)
fi
if [ -n "${GITHUB_TOKEN:-}" ]; then
  kubectl -n sre-agent create secret generic sre-agent-github \
    --from-literal=token="$GITHUB_TOKEN" --dry-run=client -o yaml | kubectl apply -f -
  # An empty issue is rejected with 422 when the token may create issues,
  # and with 403 when it lacks the permission (found in the first test).
  REPO="${GITHUB_REPOSITORY:-MaikonJm/$PROJECT}"
  CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST -d '{}' \
    -H "Authorization: Bearer $GITHUB_TOKEN" "https://api.github.com/repos/$REPO/issues")
  case "$CODE" in
    422) echo "GitHub token OK: it can open issues in $REPO" ;;
    *)   echo "WARNING: GitHub token check returned HTTP $CODE; it needs access to $REPO with Issues: read and write" ;;
  esac
else
  echo "No GitHub token found ($TOKEN_PARAM): reports stay in the logs and at GET /reports"
fi
unset GITHUB_TOKEN

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
# Restart so a new or rotated token is picked up even when the image is unchanged
kubectl -n sre-agent rollout restart deployment/sre-agent
kubectl -n sre-agent rollout status deployment/sre-agent --timeout=180s
echo "Agent ready. Reports: kubectl -n sre-agent port-forward svc/sre-agent 8080 & curl localhost:8080/reports"
