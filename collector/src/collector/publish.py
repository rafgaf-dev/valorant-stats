"""Writes summaries where CloudFront serves them (or to a local directory for development)."""

import json
from pathlib import Path
from typing import Any, Protocol

SUMMARY_CACHE_CONTROL = "public, max-age=300"


def summary_key(player_id: str) -> str:
    return f"data/players/{player_id}/summary.json"


def _encode(summary: dict[str, Any]) -> bytes:
    return (json.dumps(summary, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


class Publisher(Protocol):
    def publish(self, player_id: str, summary: dict[str, Any]) -> None: ...


class S3Publisher:
    def __init__(self, s3_client: Any, bucket: str) -> None:
        self._s3 = s3_client
        self._bucket = bucket

    def publish(self, player_id: str, summary: dict[str, Any]) -> None:
        self._s3.put_object(
            Bucket=self._bucket,
            Key=summary_key(player_id),
            Body=_encode(summary),
            ContentType="application/json",
            CacheControl=SUMMARY_CACHE_CONTROL,
        )


class DirectoryPublisher:
    def __init__(self, root: Path) -> None:
        self._root = root

    def publish(self, player_id: str, summary: dict[str, Any]) -> None:
        path = self.path_for(player_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_encode(summary))

    def path_for(self, player_id: str) -> Path:
        return self._root / summary_key(player_id)
