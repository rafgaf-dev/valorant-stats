"""Structured JSON logs and CloudWatch Embedded Metric Format (no extra API calls)."""

import json
import logging
import sys
import time
from typing import Any, TextIO

METRIC_NAMESPACE = "ValorantStats"
SERVICE = "collector"

# Attributes every LogRecord has; anything else was passed through `extra=`.
_STANDARD_ATTRIBUTES = frozenset(vars(logging.makeLogRecord({}))) | {"message", "taskName"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "level": record.levelname,
            "event": record.getMessage(),
            "logger": record.name,
        }
        entry |= {k: v for k, v in vars(record).items() if k not in _STANDARD_ATTRIBUTES}
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]  # replaces the Lambda runtime's plain-text handler
    root.setLevel(level)
    # AWS SDK internals ("Found credentials in environment variables.") aren't useful here.
    for noisy in ("boto3", "botocore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def emit_metrics(values: dict[str, int], stream: TextIO | None = None) -> None:
    """Prints one EMF document; CloudWatch turns it into metrics from the log line."""
    document = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": METRIC_NAMESPACE,
                    "Dimensions": [["Service"]],
                    "Metrics": [{"Name": name, "Unit": "Count"} for name in values],
                }
            ],
        },
        "Service": SERVICE,
        **values,
    }
    print(json.dumps(document), file=stream or sys.stdout, flush=True)
