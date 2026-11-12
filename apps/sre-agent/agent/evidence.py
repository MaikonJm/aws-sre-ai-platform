"""Collects read-only evidence about an incident.

Everything here only reads: Kubernetes (pods, events, logs, deployments),
Prometheus (SLIs) and SQS (queue depth). Nothing is ever changed.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

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
EVENT_WINDOW_MINUTES = int(os.environ.get("EVENT_WINDOW_MINUTES", "15"))

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

    # Only recent warnings, oldest first: stale events (e.g. probe failures
    # during an earlier rollout) misled the model in the first chaos test.
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=EVENT_WINDOW_MINUTES)
    recent = []
    for e in core.list_namespaced_event(NAMESPACE).items:
        when = e.last_timestamp or e.event_time or e.metadata.creation_timestamp
        if e.type == "Warning" and when and when >= cutoff:
            recent.append((when, e))
    # Probe failures from a rollout that already finished point at pods that
    # are healthy now; in the second test they misled the model again.
    healthy = {p["name"] for p in pods if p["ready"] and not p["restarts"] and not p["waiting_reasons"]}
    recent = [(when, e) for when, e in recent if e.involved_object.name not in healthy]
    recent.sort(key=lambda pair: pair[0])
    events = [
        {"at": when.isoformat(), "reason": e.reason, "object": e.involved_object.name,
         "message": (e.message or "")[:300], "count": e.count}
        for when, e in recent
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

    # Unhealthy pods first, then one pod of each workload, so the worker's
    # log is always there: in the second test the two API pods filled the
    # slots and the "invalid amount" errors never reached the model.
    logs = {}
    targets = list(unhealthy)
    for prefix in ("worker", "orders-api"):
        pod = next((p["name"] for p in pods if p["name"].startswith(prefix)), None)
        if pod and pod not in targets:
            targets.append(pod)
    for name in targets[:4]:
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


def detect_signals(evidence: dict) -> list[str]:
    """Deterministic findings computed before the LLM sees anything.

    A small model can miss one line in a large JSON; plain code does not.
    These go first in the prompt so the model starts from facts.
    """
    signals = []
    k8s = evidence.get("kubernetes")
    if isinstance(k8s, dict):
        for d in k8s.get("deployments", []):
            for key, value in d.get("env", {}).items():
                if key.startswith("FAULT_") and value not in ("", "0", "0.0"):
                    signals.append(f"Deployment {d['name']} has fault injection enabled: {key}={value}")
            if d.get("replicas_desired") == 0:
                signals.append(f"Deployment {d['name']} is scaled to 0 replicas: nothing is running it")
            elif (d.get("replicas_desired") or 0) > d.get("replicas_ready", 0):
                signals.append(
                    f"Deployment {d['name']} has {d.get('replicas_ready', 0)}/{d.get('replicas_desired')} replicas ready"
                )
        for p in k8s.get("pods", []):
            for reason in p.get("waiting_reasons", []):
                if reason in ("CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "CreateContainerConfigError"):
                    signals.append(f"Pod {p['name']} is waiting: {reason}")
        for pod, text in k8s.get("logs", {}).items():
            errors = [line for line in str(text).splitlines() if "ERROR" in line or "Traceback" in line]
            if errors:
                signals.append(f"{len(errors)} error lines in {pod} logs, latest: {errors[-1][:240]}")
    queues = evidence.get("queues")
    if isinstance(queues, dict):
        for name, attrs in queues.items():
            if isinstance(attrs, dict) and name.endswith("-dlq") and attrs.get("ApproximateNumberOfMessages", 0) > 0:
                signals.append(f"Dead Letter Queue {name} has {attrs['ApproximateNumberOfMessages']} messages")
    return signals


def collect() -> dict:
    evidence = {}
    for key, fn in (("kubernetes", kubernetes_evidence), ("slis", prometheus_evidence), ("queues", sqs_evidence)):
        try:
            evidence[key] = fn()
        except Exception as exc:
            log.exception("evidence %s failed", key)
            evidence[key] = f"<unavailable: {exc}>"
    return {"signals": detect_signals(evidence), **evidence}
