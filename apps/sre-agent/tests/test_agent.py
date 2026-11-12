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


def test_parse_response_discards_interactive_commands():
    text = '{"summary": "errors", "recommended_actions": ["Disable fault injection"], "proposed_command": "kubectl edit deployment orders-api --namespace orders"}'
    report = parse_response(text)
    assert report["proposed_command"] == ""
    assert report["recommended_actions"][0] == "Disable fault injection"
    assert "kubectl edit" in report["recommended_actions"][-1]


def test_parse_response_keeps_exact_commands():
    text = '{"proposed_command": "kubectl -n orders set env deployment/orders-api FAULT_ERROR_RATE-"}'
    assert parse_response(text)["proposed_command"] == "kubectl -n orders set env deployment/orders-api FAULT_ERROR_RATE-"


def test_detect_signals_flags_deployment_scaled_to_zero():
    from agent.evidence import detect_signals

    evidence = {"kubernetes": {"deployments": [
        {"name": "worker", "replicas_desired": 0, "replicas_ready": 0, "env": {}},
        {"name": "orders-api", "replicas_desired": 2, "replicas_ready": 2, "env": {}},
    ], "pods": []}}
    assert detect_signals(evidence) == ["Deployment worker is scaled to 0 replicas: nothing is running it"]


def test_render_markdown_redacts_aws_account_ids():
    alert = {"labels": {"alertname": "OrdersWorkerUnavailable", "severity": "page"}, "annotations": {}, "startsAt": "now"}
    report = {"summary": "worker down", "impact": "", "root_cause": "", "confidence": "high",
              "evidence": ["image 123456789012.dkr.ecr.us-east-1.amazonaws.com/worker"], "recommended_actions": [],
              "proposed_command": "", "risk": ""}
    body = render_markdown(alert, report, {}, {"model": "nova"})
    assert "123456789012" not in body
    assert "<account-id>.dkr.ecr" in body


def test_parse_response_discards_scale_with_image_flag():
    text = '{"proposed_command": "kubectl -n orders scale deployment/worker --replicas=2 --image=repo/worker:1"}'
    assert parse_response(text)["proposed_command"] == ""
