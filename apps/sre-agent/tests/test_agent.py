from agent.analysis import parse_response
from agent.report import render_markdown


def test_parse_response_extracts_json_and_fills_defaults():
    text = 'Here it is: {"summary": "API errors", "confidence": "very", "evidence": ["5xx at 20%"]} done'
    report = parse_response(text)
    assert report["summary"] == "API errors"
    assert report["confidence"] == "low"  # invalid value normalized
    assert report["evidence"] == ["5xx at 20%"]
    assert report["recommended_actions"] == []
    assert report["proposed_command"] == ""


def test_render_markdown_marks_fix_as_requiring_approval():
    alert = {"labels": {"alertname": "OrdersApiAvailabilityFastBurn", "severity": "page"},
             "annotations": {"summary": "errors"}, "startsAt": "now"}
    report = {"summary": "Fault injection enabled", "impact": "20% of orders fail",
              "root_cause": "FAULT_ERROR_RATE=0.2 on orders-api", "confidence": "high",
              "evidence": ["env FAULT_ERROR_RATE=0.2"], "recommended_actions": ["Remove the variable"],
              "proposed_command": "kubectl -n orders set env deployment/orders-api FAULT_ERROR_RATE-",
              "risk": "Low: triggers a rolling restart"}
    evidence = {"slis": {"error_ratio_5m": 0.2}, "queues": {"orders": {"ApproximateNumberOfMessages": 0}}}
    body = render_markdown(alert, report, evidence, {"model": "nova", "inputTokens": 900, "outputTokens": 200})
    assert "Nothing has been changed" in body
    assert "requires approval" in body
    assert "FAULT_ERROR_RATE-" in body
    assert "| `error_ratio_5m` | 0.2 |" in body


def test_detect_signals_flags_fault_injection_missing_replicas_and_dlq():
    from agent.evidence import detect_signals

    evidence = {
        "kubernetes": {
            "deployments": [
                {"name": "orders-api", "replicas_desired": 2, "replicas_ready": 2,
                 "env": {"FAULT_ERROR_RATE": "0.5", "FAULT_LATENCY_MS": "0"}},
                {"name": "worker", "replicas_desired": 1, "replicas_ready": 0, "env": {}},
            ],
            "pods": [{"name": "worker-abc", "waiting_reasons": ["CrashLoopBackOff"]}],
        },
        "queues": {"orders-dlq": {"ApproximateNumberOfMessages": 3}, "orders": {"ApproximateNumberOfMessages": 9}},
    }
    signals = detect_signals(evidence)
    assert "Deployment orders-api has fault injection enabled: FAULT_ERROR_RATE=0.5" in signals
    assert not any("FAULT_LATENCY_MS" in s for s in signals)  # zero means disabled
    assert "Deployment worker has 0/1 replicas ready" in signals
    assert "Pod worker-abc is waiting: CrashLoopBackOff" in signals
    assert "Dead Letter Queue orders-dlq has 3 messages" in signals
    assert len(signals) == 4


def test_detect_signals_tolerates_unavailable_evidence():
    from agent.evidence import detect_signals

    assert detect_signals({"kubernetes": "<unavailable: boom>", "queues": "<unavailable>"}) == []
