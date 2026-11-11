"""AI SRE agent: receives Alertmanager webhooks and investigates firing alerts."""

import logging
import os
import time
from collections import deque

from fastapi import BackgroundTasks, FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from . import analysis, evidence, report

logging.basicConfig(level=logging.INFO, format='{"level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
log = logging.getLogger("sre-agent")

COOLDOWN_SECONDS = int(os.environ.get("COOLDOWN_SECONDS", "900"))

INVESTIGATIONS = Counter("sre_agent_investigations_total", "Investigations run", ["alertname", "outcome"])
TOKENS = Counter("sre_agent_llm_tokens_total", "LLM tokens used", ["direction"])
LLM_LATENCY = Histogram("sre_agent_llm_latency_seconds", "Bedrock call latency")

app = FastAPI(title="AI SRE agent")
last_seen: dict[str, float] = {}
reports: deque = deque(maxlen=20)


def investigate(alert: dict) -> None:
    name = alert.get("labels", {}).get("alertname", "unknown")
    try:
        ev = evidence.collect()
        result, usage = analysis.analyze(alert, ev)
        TOKENS.labels("input").inc(usage.get("inputTokens", 0))
        TOKENS.labels("output").inc(usage.get("outputTokens", 0))
        LLM_LATENCY.observe(usage.get("latency_seconds", 0))
        body = report.render_markdown(alert, result, ev, usage)
        url = report.publish(alert, result, body)
        reports.appendleft({"alert": name, "at": time.time(), "issue": url, "report": result})
        log.info(f"investigation of {name} done: {result['summary']} (issue: {url})")
        INVESTIGATIONS.labels(name, "ok").inc()
    except Exception:
        log.exception(f"investigation of {name} failed")
        INVESTIGATIONS.labels(name, "error").inc()


@app.post("/alertmanager")
def alertmanager_webhook(payload: dict, background: BackgroundTasks):
    started = []
    for alert in payload.get("alerts", []):
        if alert.get("status") != "firing":
            continue
        key = alert.get("fingerprint") or alert.get("labels", {}).get("alertname", "")
        now = time.time()
        if now - last_seen.get(key, 0) < COOLDOWN_SECONDS:
            continue  # already investigated recently: avoid duplicate issues and LLM cost
        last_seen[key] = now
        background.add_task(investigate, alert)
        started.append(alert.get("labels", {}).get("alertname"))
    return {"investigating": started}


@app.get("/reports")
def list_reports():
    return list(reports)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
