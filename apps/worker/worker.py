"""Worker: consumes orders from SQS and marks them as processed.

A message is deleted only after the order is processed. If processing
fails, the message becomes visible again; after maxReceiveCount attempts
SQS moves it to the Dead Letter Queue.
"""

import json
import logging
import os
import signal

import boto3
import psycopg
from prometheus_client import Counter, start_http_server

logging.basicConfig(level=logging.INFO, format='{"level":"%(levelname)s","msg":"%(message)s"}')
log = logging.getLogger("worker")

DB_DSN = (
    f"host={os.environ['DB_HOST']} dbname={os.environ['DB_NAME']} "
    f"user={os.environ['DB_USER']} password={os.environ['DB_PASSWORD']} connect_timeout=3"
)
QUEUE_URL = os.environ["QUEUE_URL"]
sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "us-east-1"))

PROCESSED = Counter("orders_processed_total", "Orders processed successfully")
FAILED = Counter("orders_failed_total", "Processing attempts that failed")

running = True


def stop(*_):
    global running
    log.info("shutdown requested, finishing current batch")
    running = False


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)


class InvalidOrder(Exception):
    pass


def process(order_id: str) -> None:
    with psycopg.connect(DB_DSN) as conn:
        row = conn.execute("SELECT amount, status FROM orders WHERE id = %s", (order_id,)).fetchone()
        if row is None:
            raise InvalidOrder(f"order {order_id} not found")
        amount, status = row
        if status == "processed":
            log.info(f"order {order_id} already processed, skipping (idempotent)")
            return
        if amount <= 0:
            raise InvalidOrder(f"order {order_id} has invalid amount {amount}")
        conn.execute(
            "UPDATE orders SET status = 'processed', updated_at = now() WHERE id = %s", (order_id,)
        )


def main() -> None:
    start_http_server(9100)
    log.info("worker started")
    while running:
        response = sqs.receive_message(
            QueueUrl=QUEUE_URL,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20,
            AttributeNames=["ApproximateReceiveCount"],
        )
        for message in response.get("Messages", []):
            order_id = json.loads(message["Body"])["order_id"]
            attempt = message["Attributes"]["ApproximateReceiveCount"]
            try:
                process(order_id)
            except Exception as exc:  # leave the message for retry / DLQ
                FAILED.inc()
                log.error(f"order {order_id} failed on attempt {attempt}: {exc}")
                continue
            sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=message["ReceiptHandle"])
            PROCESSED.inc()
            log.info(f"order {order_id} processed")


if __name__ == "__main__":
    main()
