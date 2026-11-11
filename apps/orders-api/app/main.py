"""Orders API: stores an order in PostgreSQL and publishes it to SQS."""

import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal

import boto3
import psycopg
from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format='{"level":"%(levelname)s","msg":"%(message)s"}')
log = logging.getLogger("orders-api")

DB_DSN = (
    f"host={os.environ['DB_HOST']} dbname={os.environ['DB_NAME']} "
    f"user={os.environ['DB_USER']} password={os.environ['DB_PASSWORD']} connect_timeout=3"
)
QUEUE_URL = os.environ["QUEUE_URL"]
sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "us-east-1"))

REQUESTS = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["method", "route", "status"]
)
ORDERS_CREATED = Counter("orders_created_total", "Orders accepted by the API")

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id          UUID PRIMARY KEY,
    item        TEXT NOT NULL,
    quantity    INTEGER NOT NULL,
    amount      NUMERIC(12, 2) NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    with psycopg.connect(DB_DSN) as conn:
        conn.execute(SCHEMA)
    log.info("schema ready")
    yield


app = FastAPI(title="Orders API", lifespan=lifespan)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    REQUESTS.labels(
        request.method, route.path if route else "unmatched", str(response.status_code)
    ).observe(time.perf_counter() - start)
    return response


class OrderIn(BaseModel):
    item: str = Field(min_length=1, max_length=100)
    quantity: int = Field(gt=0, le=1000)
    # Negative amounts are accepted on purpose: the worker rejects them,
    # which exercises the retry -> DLQ path during chaos tests.
    amount: Decimal = Field(max_digits=12, decimal_places=2)


@app.post("/orders", status_code=202)
def create_order(order: OrderIn):
    order_id = str(uuid.uuid4())
    with psycopg.connect(DB_DSN) as conn:
        conn.execute(
            "INSERT INTO orders (id, item, quantity, amount) VALUES (%s, %s, %s, %s)",
            (order_id, order.item, order.quantity, order.amount),
        )
    sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps({"order_id": order_id}))
    ORDERS_CREATED.inc()
    log.info(f"order {order_id} accepted")
    return {"id": order_id, "status": "pending"}


@app.get("/orders/{order_id}")
def get_order(order_id: uuid.UUID):
    with psycopg.connect(DB_DSN) as conn:
        row = conn.execute(
            "SELECT id, item, quantity, amount, status FROM orders WHERE id = %s", (order_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="order not found")
    return {
        "id": str(row[0]),
        "item": row[1],
        "quantity": row[2],
        "amount": str(row[3]),
        "status": row[4],
    }


@app.get("/healthz")
def healthz():
    """Liveness: the process is up."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    """Readiness: the database answers."""
    try:
        with psycopg.connect(DB_DSN) as conn:
            conn.execute("SELECT 1")
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ready"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
