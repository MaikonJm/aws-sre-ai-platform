#!/bin/bash
# Deploys the orders application on the k3s node.
# Run it on the node (SSM session) from a clone of this repository:
#   ./scripts/deploy-app.sh            # latest image pushed by CI
#   ./scripts/deploy-app.sh <git-sha>  # a specific build
set -euo pipefail

export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
export AWS_REGION="${AWS_REGION:-us-east-1}"
PROJECT=aws-sre-ai-platform
NAMESPACE=orders
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGISTRY="$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
QUEUE_URL=$(aws sqs get-queue-url --queue-name "$PROJECT-orders" --query QueueUrl --output text)

latest_tag() {
  aws ecr describe-images --repository-name "$PROJECT/$1" \
    --query 'sort_by(imageDetails, &imagePushedAt)[-1].imageTags[0]' --output text
}
TAG="${1:-$(latest_tag orders-api)}"
echo "Deploying tag $TAG from $REGISTRY"

kubectl apply -f "$REPO_ROOT/k8s/app/namespace.yaml"

# Database password: generated once, never stored in Git
if ! kubectl -n "$NAMESPACE" get secret postgres-credentials >/dev/null 2>&1; then
  kubectl -n "$NAMESPACE" create secret generic postgres-credentials \
    --from-literal=password="$(openssl rand -hex 24)"
fi

kubectl -n "$NAMESPACE" create configmap app-config \
  --from-literal=DB_HOST=postgres \
  --from-literal=DB_NAME=orders \
  --from-literal=DB_USER=orders \
  --from-literal=QUEUE_URL="$QUEUE_URL" \
  --from-literal=AWS_REGION="$AWS_REGION" \
  --dry-run=client -o yaml | kubectl apply -f -

# Image pull secret for ECR (also refreshed every 6h by a systemd timer)
/usr/local/bin/refresh-ecr-secret

# Render the manifests with the ECR images and apply
WORK=$(mktemp -d)
cp "$REPO_ROOT"/k8s/app/*.yaml "$WORK/"
cat >> "$WORK/kustomization.yaml" <<IMAGES
images:
  - name: orders-api
    newName: $REGISTRY/$PROJECT/orders-api
    newTag: "$TAG"
  - name: worker
    newName: $REGISTRY/$PROJECT/worker
    newTag: "$TAG"
IMAGES
kubectl apply -k "$WORK"
rm -rf "$WORK"

kubectl -n "$NAMESPACE" rollout status statefulset/postgres --timeout=180s
kubectl -n "$NAMESPACE" rollout status deployment/orders-api --timeout=180s
kubectl -n "$NAMESPACE" rollout status deployment/worker --timeout=180s
kubectl -n "$NAMESPACE" get pods -o wide
