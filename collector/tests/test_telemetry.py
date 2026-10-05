import io
import json
import logging
import sys

from collector.telemetry import JsonFormatter, configure_logging, emit_metrics


def test_json_formatter_includes_extra_fields_and_exceptions():
    logger = logging.getLogger("test")
    record = logger.makeRecord("test", logging.WARNING, __file__, 1, "match_unparseable", (), None)
    record.player = "neon-main"
    try:
        raise ValueError("bad data")
    except ValueError:
        record.exc_info = sys.exc_info()

    entry = json.loads(JsonFormatter().format(record))

    assert entry["event"] == "match_unparseable"
    assert entry["level"] == "WARNING"
    assert entry["player"] == "neon-main"
    assert "ValueError: bad data" in entry["exception"]
    assert "msg" not in entry
    assert "args" not in entry


def test_emit_metrics_writes_an_embedded_metric_format_document():
    stream = io.StringIO()

    emit_metrics({"SuccessfulRuns": 1, "MatchesImported": 3}, stream)

    document = json.loads(stream.getvalue())
    directive = document["_aws"]["CloudWatchMetrics"][0]
    assert directive["Namespace"] == "ValorantStats"
    assert directive["Dimensions"] == [["Service"]]
    assert [m["Name"] for m in directive["Metrics"]] == ["SuccessfulRuns", "MatchesImported"]
    assert (document["Service"], document["SuccessfulRuns"], document["MatchesImported"]) == (
        "collector",
        1,
        3,
    )


def test_configure_logging_quiets_aws_sdk_internals(monkeypatch):
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", list(root.handlers))
    monkeypatch.setattr(root, "level", root.level)
    for name in ("boto3", "botocore", "urllib3"):
        monkeypatch.setattr(logging.getLogger(name), "level", logging.NOTSET)

    configure_logging()

    assert logging.getLogger("botocore.credentials").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("collector.collect").getEffectiveLevel() == logging.INFO
