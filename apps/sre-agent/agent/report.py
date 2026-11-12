"""Turns the analysis into a GitHub issue for human review."""

import logging
import os
import re

import httpx

log = logging.getLogger("sre-agent.report")

GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")


def render_markdown(alert: dict, report: dict, evidence: dict, usage: dict) -> str:
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})
    slis = evidence.get("slis", {}) if isinstance(evidence.get("slis"), dict) else {}
    queues = evidence.get("queues", {}) if isinstance(evidence.get("queues"), dict) else {}

    lines = [
        f"> 🤖 Investigation by the AI SRE agent ({usage.get('model', '')}). "
        "**Nothing has been changed.** A human must review and approve the fix.",
        "",
        "## Alert",
        f"- **Name:** `{labels.get('alertname', '?')}` · **Severity:** `{labels.get('severity', '?')}`",
        f"- **Summary:** {annotations.get('summary', '')}",
        f"- **Started:** {alert.get('startsAt', '')}",
        "",
        "## Diagnosis",
        f"**{report['summary']}**",
        "",
        f"- **Impact:** {report['impact']}",
        f"- **Probable root cause:** {report['root_cause']}",
        f"- **Confidence:** {report['confidence']}",
        "",
        "### Evidence",
        *[f"- {item}" for item in report["evidence"]],
        "",
        "### Recommended actions",
        *[f"{i}. {item}" for i, item in enumerate(report["recommended_actions"], 1)],
        "",
    ]
    if report["proposed_command"]:
        lines += [
            "### Proposed fix (requires approval)",
            "```bash",
            report["proposed_command"],
            "```",
            f"**Risk:** {report['risk']}",
            "",
        ]
    lines += ["## SLIs at investigation time", "| SLI | Value |", "| --- | --- |"]
    lines += [f"| `{k}` | {v} |" for k, v in slis.items()]
    lines += ["", "## Queues", "| Queue | Depth |", "| --- | --- |"]
    lines += [f"| `{k}` | {v} |" for k, v in queues.items()]
    lines += [
        "",
        f"<sub>Tokens: {usage.get('inputTokens', '?')} in / {usage.get('outputTokens', '?')} out · "
        f"Bedrock latency: {usage.get('latency_seconds', '?')} s</sub>",
    ]
    # Issues can be public: never publish an AWS account ID, even when the
    # model copies one from an image URL (found in the second test session).
    return re.sub(r"\b\d{12}\b", "<account-id>", "\n".join(lines))


def publish(alert: dict, report: dict, body: str) -> str | None:
    """Opens a GitHub issue; returns its URL, or None when no token is configured."""
    if not (GITHUB_TOKEN and GITHUB_REPOSITORY):
        log.info("GITHUB_TOKEN not set: report kept in logs and at GET /reports")
        return None
    title = f"[Incident] {alert.get('labels', {}).get('alertname', 'alert')}: {report['summary']}"
    title = re.sub(r"\b\d{12}\b", "<account-id>", title)[:200]
    response = httpx.post(
        f"https://api.github.com/repos/{GITHUB_REPOSITORY}/issues",
        headers={"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"},
        json={"title": title, "body": body, "labels": ["incident", "ai-investigation"]},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["html_url"]
