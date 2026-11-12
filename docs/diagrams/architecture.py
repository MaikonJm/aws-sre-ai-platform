"""Architecture diagram with the official AWS icons, laid out by hand.

Every icon and arrow has a fixed position, so the picture stays readable
and can be animated frame by frame (see animate.py).

    pip install diagrams playwright      # icons come from the diagrams package
    python docs/diagrams/architecture.py # writes docs/images/architecture.png

Needs Chrome or Chromium (CHROME=/path/to/chrome to override).
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

import diagrams

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "images"
ICONS = Path(os.path.realpath(Path(diagrams.__file__).parent.parent / "resources"))
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")

W, H = 2400, 1500

COLORS = {
    "request": "#2563EB",
    "queue": "#EA580C",
    "alert": "#DC2626",
    "ai": "#7C3AED",
    "ops": "#64748B",
}
LEGEND = [
    ("request", "Request"),
    ("queue", "Queue / async"),
    ("alert", "Metrics & alerts"),
    ("ai", "AI investigation"),
    ("ops", "Delivery & access"),
]

# name: (icon, x, y, label, sub-label)  -- x, y = icon centre
NODES = {
    "repo": ("onprem/vcs/github.png", 170, 300, "Repository", "code + Terraform"),
    "actions": ("onprem/ci/github-actions.png", 170, 520, "GitHub Actions", "tests · plan · build"),
    "customer": ("aws/general/user.png", 170, 760, "Customer", "POST /orders"),
    "terraform": ("onprem/iac/terraform.png", 170, 1220, "Infra as code", "4 stacks · S3 state"),
    "role": ("aws/security/identity-and-access-management-iam-role.png", 500, 300, "CI role", "GitHub OIDC, no keys"),
    "ecr": ("aws/compute/ec2-container-registry.png", 720, 300, "Amazon ECR", "immutable · scanned"),
    "s3": ("aws/storage/simple-storage-service-s3.png", 940, 300, "S3 state", "versioned · locked"),
    "budgets": ("aws/cost/budgets.png", 1160, 300, "AWS Budgets", "50 / 80 / 100%"),
    "params": ("aws/management/systems-manager-parameter-store.png", 1600, 300, "Parameter Store", "agent's GitHub token"),
    "ssm": ("aws/management/systems-manager.png", 1860, 300, "Session Manager", "shell, no SSH"),
    "igw": ("aws/network/internet-gateway.png", 470, 760, "Internet", "Gateway"),
    "s3ep": ("aws/network/endpoint.png", 470, 1230, "S3 gateway", "endpoint"),
    "traefik": ("onprem/network/traefik.png", 690, 760, "Traefik", "ingress"),
    "api": ("programming/framework/fastapi.png", 920, 760, "Orders API", "FastAPI"),
    "worker": ("k8s/compute/pod.png", 1390, 760, "Worker", "idempotent"),
    "db": ("onprem/database/postgresql.png", 1155, 875, "PostgreSQL", "StatefulSet"),
    "prom": ("onprem/monitoring/prometheus.png", 700, 1110, "Prometheus", "SLO rules"),
    "am": ("onprem/monitoring/prometheus.png", 930, 1110, "Alertmanager", ""),
    "grafana": ("onprem/monitoring/grafana.png", 700, 1275, "Grafana", "SLO dashboard"),
    "agent": ("k8s/compute/pod.png", 1310, 1110, "AI SRE agent", "read-only RBAC"),
    "sqs": ("aws/integration/simple-queue-service-sqs.png", 1690, 600, "SQS orders", ""),
    "dlq": ("aws/integration/simple-queue-service-sqs-queue.png", 1900, 600, "Dead Letter Queue", "after 3 attempts"),
    "alarm": ("aws/management/cloudwatch-alarm.png", 1900, 795, "CloudWatch", "DLQ alarm"),
    "sns": ("aws/integration/simple-notification-service-sns.png", 1900, 995, "Amazon SNS", "e-mail"),
    "bedrock": ("aws/ml/bedrock.png", 1790, 1205, "Amazon Bedrock", "Nova Micro"),
    "engineer": ("aws/general/user.png", 2230, 995, "On-call engineer", ""),
    "issue": ("onprem/vcs/github.png", 2230, 1330, "GitHub issue", "fix needs approval"),
}

# (x0, y0, x1, y1, title, border, fill, title colour, group icon, title on the right)
BOXES = [
    (40, 215, 300, 620, "GitHub", "#24292F", "#F6F8FA", "#24292F", None, False),
    (360, 160, 2050, 1450, "AWS Cloud · us-east-1", "#232F3E", "#FFFFFF", "#232F3E", "aws/aws.png", False),
    (390, 205, 2020, 400, "Delivery, access and guardrails", "#7AA116", "#F5FAEE", "#4D6B0A", None, False),
    (390, 430, 1540, 1420, "VPC 10.20.0.0/16 · 2 AZs · no NAT gateway", "#8C4FFF", "#FAF7FF", "#6B2BD9", "aws/network/vpc.png", True),
    (575, 470, 1520, 1400, "Public subnet · EC2 c7i-flex.large · k3s", "#ED7100", "#FFF8F1", "#B85700", "aws/compute/ec2.png", False),
    (600, 655, 1495, 965, "namespace orders", "#2563EB", "#EFF6FF", "#1D4ED8", None, False),
    (600, 1000, 1080, 1385, "namespace monitoring", "#DC2626", "#FEF2F2", "#B91C1C", None, False),
    (1120, 1000, 1495, 1385, "namespace sre-agent", "#7C3AED", "#F5F3FF", "#6D28D9", None, False),
    (1570, 430, 2020, 1100, "Messaging", "#E7157B", "#FDF2F8", "#BE185D", None, False),
    (1570, 1130, 2020, 1310, "Generative AI", "#01A88D", "#EEFBF8", "#047A66", None, False),
]

# (id, kind, points, label, label_at, dashed)
# label_at: (x, y) or None for the middle of the longest segment
EDGES = [
    ("repo-actions", "ops", [(170, 396), (170, 474)], "push / PR", (170, 433), False),
    ("actions-role", "ops", [(215, 520), (330, 520), (330, 300), (455, 300)], "OIDC", (330, 410), False),
    ("role-ecr", "ops", [(545, 300), (675, 300)], "push", None, False),
    ("ecr-ec2", "ops", [(720, 396), (720, 468)], "pull images", (720, 432), True),
    ("tf-aws", "ops", [(215, 1220), (360, 1220)], "apply", None, True),
    ("engineer-ssm", "ops", [(2230, 950), (2230, 300), (1905, 300)], "shell", (2230, 620), True),
    ("customer-igw", "request", [(215, 760), (425, 760)], "HTTPS", None, False),
    ("igw-traefik", "request", [(515, 760), (645, 760)], "", None, False),
    ("traefik-api", "request", [(735, 760), (875, 760)], "", None, False),
    ("api-db", "request", [(965, 760), (1120, 760), (1120, 830)], "store", (1040, 760), False),
    ("api-sqs", "queue", [(920, 715), (920, 600), (1645, 600)], "publish", (1290, 600), False),
    ("sqs-worker", "queue", [(1690, 645), (1690, 760), (1435, 760)], "consume", (1560, 760), False),
    ("worker-db", "queue", [(1345, 760), (1190, 760), (1190, 830)], "processed", (1268, 760), False),
    ("sqs-dlq", "queue", [(1735, 600), (1855, 600)], "3 failures", None, True),
    ("dlq-alarm", "queue", [(1900, 694), (1900, 750)], "", None, False),
    ("alarm-sns", "queue", [(1900, 889), (1900, 950)], "", None, False),
    ("sns-engineer", "queue", [(1945, 995), (2185, 995)], "e-mail", (2080, 995), True),
    ("scrape", "alert", [(700, 965), (700, 1065)], "scrape /metrics", (700, 982), True),
    ("prom-am", "alert", [(745, 1110), (885, 1110)], "burn rate", None, False),
    ("prom-grafana", "alert", [(655, 1110), (628, 1110), (628, 1275), (655, 1275)], "", None, False),
    ("am-agent", "alert", [(975, 1110), (1265, 1110)], "webhook", (1150, 1110), False),
    ("agent-k8s", "ai", [(1310, 1065), (1310, 965)], "read pods, events, logs", (1310, 982), True),
    ("agent-bedrock", "ai", [(1355, 1110), (1555, 1110), (1555, 1205), (1745, 1205)], "signals + evidence", (1470, 1110), False),
    ("agent-issue", "ai", [(1310, 1206), (1310, 1330), (2185, 1330)], "open incident issue", (1820, 1330), False),
    ("issue-engineer", "ai", [(2230, 1286), (2230, 1092)], "review", (2230, 1190), False),
]


def icon_uri(rel: str) -> str:
    data = base64.b64encode((ICONS / rel).read_bytes()).decode()
    return f"data:image/png;base64,{data}"


def label_point(points, at):
    if at:
        return at
    best = max(zip(points, points[1:]), key=lambda s: abs(s[1][0] - s[0][0]) + abs(s[1][1] - s[0][1]))
    (x0, y0), (x1, y1) = best
    return ((x0 + x1) / 2, (y0 + y1) / 2)


def render_html(highlight: set[str] | None = None, active_nodes: set[str] | None = None,
                caption: str = "") -> str:
    """highlight: edge ids to emphasise (others dimmed); None = normal picture."""
    dim = highlight is not None
    parts = [f"""<!doctype html><html><head><meta charset="utf-8"><style>
    *{{box-sizing:border-box}} body{{margin:0;width:{W}px;height:{H}px;background:#fff;
      font-family:Inter,'Helvetica Neue',Arial,sans-serif;position:relative;overflow:hidden}}
    .box{{position:absolute;border:2.5px solid;border-radius:18px}}
    .box .t{{position:absolute;left:16px;top:10px;font-weight:700;font-size:21px;letter-spacing:.2px}}
    .n{{position:absolute;width:210px;margin-left:-105px;text-align:center;transition:opacity .2s}}
    .n img{{width:84px;height:84px;object-fit:contain;display:block;margin:0 auto 6px}}
    .n .l{{font-weight:700;font-size:20px;color:#0F172A;line-height:1.15}}
    .n .s{{font-weight:500;font-size:16px;color:#475569;line-height:1.2}}
    .el{{position:absolute;transform:translate(-50%,-50%);background:#fff;border:2px solid;border-radius:999px;
        padding:3px 12px;font-weight:700;font-size:16px;white-space:nowrap}}
    .dim{{opacity:.18}}
    </style></head><body>"""]

    parts.append(f"""<div style="position:absolute;left:40px;top:34px">
      <div style="font-size:46px;font-weight:800;color:#0F172A;letter-spacing:-.5px">AWS SRE AI Platform</div>
      <div style="font-size:22px;font-weight:500;color:#475569;margin-top:6px">
      Orders on Kubernetes (k3s) · SLO burn-rate alerting · an AI SRE agent on Amazon Bedrock · 100% Terraform</div></div>""")
    legend = "".join(
        f'<span style="display:inline-flex;align-items:center;margin-left:26px;font-size:18px;font-weight:600;color:#334155">'
        f'<span style="width:34px;height:5px;border-radius:3px;background:{COLORS[k]};margin-right:9px"></span>{t}</span>'
        for k, t in LEGEND)
    parts.append(f'<div style="position:absolute;right:40px;top:58px">{legend}</div>')

    for x0, y0, x1, y1, title, border, fill, tcol, gicon, right in BOXES:
        img = (f'<img src="{icon_uri(gicon)}" style="width:30px;height:30px;object-fit:contain;'
               f'vertical-align:middle;margin-right:9px;margin-top:-3px">') if gicon else ""
        side = "right:16px;left:auto" if right else ""
        parts.append(f'<div class="box" style="left:{x0}px;top:{y0}px;width:{x1-x0}px;height:{y1-y0}px;'
                     f'border-color:{border};background:{fill}"><div class="t" style="color:{tcol};{side}">{img}{title}</div></div>')

    # arrows
    svg = [f'<svg width="{W}" height="{H}" style="position:absolute;left:0;top:0" xmlns="http://www.w3.org/2000/svg"><defs>']
    for k, c in COLORS.items():
        svg.append(f'<marker id="a-{k}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" '
                   f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>')
    svg.append("</defs>")
    labels = []
    for eid, kind, pts, label, at, dashed in EDGES:
        on = not dim or eid in highlight
        width = 6 if (dim and on) else 3.5
        opacity = 1 if on else 0.15
        d = "M" + " L".join(f"{x},{y}" for x, y in pts)
        dash = ' stroke-dasharray="10 8"' if dashed else ""
        svg.append(f'<path d="{d}" fill="none" stroke="{COLORS[kind]}" stroke-width="{width}" stroke-linejoin="round"'
                   f'{dash} opacity="{opacity}" marker-end="url(#a-{kind})"/>')
        if label:
            x, y = label_point(pts, at)
            labels.append(f'<div class="el" style="left:{x}px;top:{y}px;color:{COLORS[kind]};border-color:{COLORS[kind]};'
                          f'opacity:{opacity}">{label}</div>')
    svg.append("</svg>")
    parts.extend(svg)
    parts.extend(labels)

    for name, (icon, x, y, label, sub) in NODES.items():
        cls = "n" + (" dim" if dim and active_nodes is not None and name not in active_nodes else "")
        sub_html = f'<div class="s">{sub}</div>' if sub else ""
        parts.append(f'<div class="{cls}" style="left:{x}px;top:{y-42}px"><img src="{icon_uri(icon)}">'
                     f'<div class="l">{label}</div>{sub_html}</div>')

    if caption:
        parts.append(f'<div style="position:absolute;left:50%;bottom:22px;transform:translateX(-50%);background:#0F172A;'
                     f'color:#fff;font-size:26px;font-weight:700;padding:12px 28px;border-radius:14px">{caption}</div>')
    parts.append("</body></html>")
    return "".join(parts)


def screenshot(pages: list[tuple[str, Path]], scale: float = 2) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME)
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=scale)
        for html, path in pages:
            page.set_content(html)
            page.wait_for_timeout(150)
            page.screenshot(path=str(path))
        browser.close()


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    screenshot([(render_html(), OUT / "architecture.png")])
    print("wrote", OUT / "architecture.png")
