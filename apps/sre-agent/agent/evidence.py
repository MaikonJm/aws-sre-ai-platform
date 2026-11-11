"""Collects read-only evidence about an incident.

Everything here only reads: Kubernetes (pods, events, logs, deployments),
Prometheus (SLIs) and SQS (queue depth). Nothing is ever changed.
"""

import logging
import os

import boto3
import httpx
from kubernetes import client, config

log = logging.getLogger("sre-agent.evidence")

NAMESPACE = os.environ.get("TARGET_NAMESPACE", "orders")
PROMETHEUS_URL = os.environ.get(
    "PROMETHEUS_URL", "http://monitoring-kube-prometheus-prometheus.monitoring:9090"
)
QUEUE_NAMES = [q for q in os.environ.get("QUEUE_NAMES", "").split(",") if q]
LOG_LINES = int(os.environ.get("LOG_LINES", "40"))

SLI_QUERIES = {
    "error_ratio_5m": "orders_api:error_ratio:rate5m",
    "error_ratio_1h": "orders_api:error_ratio:rate1h",
    "slow_ratio_5m": "orders_api:slow_ratio:rate5m",
    "p95_latency_seconds": 'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{namespace="orders",route=~"/orders.*"}[5m])))',
    "orders_created_per_min": 'sum(rate(orders_created_total{namespace="orders"}[5m])) * 60',
    "orders_processed_per_min": 'sum(rate(orders_processed_total{namespace="orders"}[5m])) * 60',
    "worker_failures_per_min": 'sum(rate(orders_failed_total{namespace="orders"}[5m])) * 60',
}


def _k8s() -> tuple[client.CoreV1Api, client.AppsV1Api]:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    return client.CoreV1Api(), client.AppsV1Api()


def kubernetes_evidence() -> dict:
    core, apps = _k8s()
    pods = []
    unhealthy = []
    for pod in core.list_namespaced_pod(NAMESPACE).items:
        restarts = sum(cs.restart_count for cs in (pod.status.container_statuses or []))
        waiting = [
            cs.state.waiting.reason
            for cs in (pod.status.container_statuses or [])
            if cs.state and cs.state.waiting
        ]
        ready = all(cs.ready for cs in (pod.status.container_statuses or [])) if pod.status.container_statuses else False
        pods.append({
            "name": pod.metadata.name,
            "phase": pod.status.phase,
            "ready": ready,
            "restarts": restarts,
            "waiting_reasons": waiting,
        })
        if not ready or restarts or waiting:
            unhealthy.append(pod.metadata.name)

    events = [
        {"reason": e.reason, "object": e.involved_object.name, "message": (e.message or "")[:300], "count": e.count}
        for e in core.list_namespaced_event(NAMESPACE).items
        if e.type == "Warning"
    ][-15:]

    deployments = []
    for d in apps.list_namespaced_deployment(NAMESPACE).items:
        container = d.spec.template.spec.containers[0]
        env = {e.name: e.value for e in (container.env or []) if e.value is not None}
        deployments.append({
            "name": d.metadata.name,
            "replicas_desired": d.spec.replicas,
            "replicas_ready": d.status.ready_replicas or 0,
            "image": container.image,
            # literal env vars only (secrets come from secretKeyRef and are not read)
            "env": env,
        })

    logs = {}
    targets = unhealthy or [p["name"] for p in pods if p["name"].startswith(("orders-api", "worker"))][:2]
    for name in targets[:3]:
        try:
            logs[name] = core.read_namespaced_pod_log(name, NAMESPACE, tail_lines=LOG_LINES)[-4000:]
        except client.ApiException as exc:
            logs[name] = f"<logs unavailable: {exc.reason}>"

    return {"pods": pods, "warning_events": events, "deployments": deployments, "logs": logs}


def prometheus_evidence() -> dict:
    results = {}
    with httpx.Client(base_url=PROMETHEUS_URL, timeout=5) as http:
        for name, query in SLI_QUERIES.items():
            try:
                data = http.get("/api/v1/query", params={"query": query}).json()["data"]["result"]
                results[name] = round(float(data[0]["value"][1]), 4) if data else None
            except Exception as exc:  # evidence is best effort
                results[name] = f"<error: {exc}>"
    return results


def sqs_evidence() -> dict:
    sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    depths = {}
    for name in QUEUE_NAMES:
        try:
            url = sqs.get_queue_url(QueueName=name)["QueueUrl"]
            attrs = sqs.get_queue_attributes(
                QueueUrl=url,
                AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"],
            )["Attributes"]
            depths[name] = {k: int(v) for k, v in attrs.items()}
        except Exception as exc:
            depths[name] = f"<error: {exc}>"
    return depths


def collect() -> dict:
    evidence = {}
    for key, fn in (("kubernetes", kubernetes_evidence), ("slis", prometheus_evidence), ("queues", sqs_evidence)):
        try:
            evidence[key] = fn()
        except Exception as exc:
            log.exception("evidence %s failed", key)
            evidence[key] = f"<unavailable: {exc}>"
    return evidence
