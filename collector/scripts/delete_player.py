"""Deletes everything stored about one player: `make delete-player PLAYER=<id>`.

Removes the player's DynamoDB items (matches and import runs), every version of their
published files (summary and photo) from the versioned data bucket, and CloudFront's cached
copies. Remove the player from config/players.json and apply Terraform as well, or the next
collector run recreates the data.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import boto3

from collector.config import PLAYER_ID_PATTERN

REPO_ROOT = Path(__file__).resolve().parents[2]
S3_DELETE_BATCH = 1000  # DeleteObjects limit


def delete_items(table: Any, player_id: str) -> int:
    """Deletes every item in the player's partition; returns how many were deleted."""
    query: dict[str, Any] = {
        "KeyConditionExpression": "PK = :pk",
        "ExpressionAttributeValues": {":pk": f"PLAYER#{player_id}"},
        "ProjectionExpression": "PK, SK",
    }
    deleted = 0
    with table.batch_writer() as batch:
        while True:
            page = table.query(**query)
            for item in page["Items"]:
                batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
                deleted += 1
            if "LastEvaluatedKey" not in page:
                return deleted
            query["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def delete_objects(s3: Any, bucket: str, player_id: str) -> int:
    """Deletes every version and delete marker under the player's prefix."""
    prefix = f"data/players/{player_id}/"  # the trailing slash keeps "neon" from matching "neon-2"
    deleted = 0
    for page in s3.get_paginator("list_object_versions").paginate(Bucket=bucket, Prefix=prefix):
        versions = page.get("Versions", []) + page.get("DeleteMarkers", [])
        keys = [{"Key": v["Key"], "VersionId": v["VersionId"]} for v in versions]
        for start in range(0, len(keys), S3_DELETE_BATCH):
            batch = keys[start : start + S3_DELETE_BATCH]
            response = s3.delete_objects(Bucket=bucket, Delete={"Objects": batch, "Quiet": True})
            if response.get("Errors"):
                raise RuntimeError(f"S3 refused to delete {len(response['Errors'])} object(s)")
            deleted += len(batch)
    return deleted


def invalidate(cloudfront: Any, distribution_id: str, player_id: str) -> str:
    response = cloudfront.create_invalidation(
        DistributionId=distribution_id,
        InvalidationBatch={
            "Paths": {"Quantity": 1, "Items": [f"/data/players/{player_id}/*"]},
            # Unique per call: CloudFront treats a repeated reference as the same request.
            "CallerReference": f"delete-player-{player_id}-{time.time_ns()}",
        },
    )
    return response["Invalidation"]["Id"]


def still_configured(player_id: str, players_file: Path) -> bool:
    if not players_file.exists():
        return False
    try:
        players = json.loads(players_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return any(isinstance(p, dict) and p.get("id") == player_id for p in players)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--player", required=True)
    parser.add_argument("--table", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--distribution", required=True)
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args(argv)

    if not PLAYER_ID_PATTERN.fullmatch(args.player):
        print(f"Invalid player id {args.player!r}.", file=sys.stderr)
        return 2
    if not args.yes:
        answer = input(
            f"Permanently delete all matches, runs, summaries, and photos for "
            f"{args.player!r}? Type the player id to confirm: "
        )
        if answer.strip() != args.player:
            print("Nothing deleted.")
            return 1

    items = delete_items(boto3.resource("dynamodb").Table(args.table), args.player)
    objects = delete_objects(boto3.client("s3"), args.bucket, args.player)
    invalidation = invalidate(boto3.client("cloudfront"), args.distribution, args.player)
    print(f"Deleted {items} DynamoDB item(s) and {objects} S3 object version(s).")
    print(f"CloudFront invalidation {invalidation} clears cached copies within minutes.")
    if still_configured(args.player, REPO_ROOT / "config" / "players.json"):
        print(
            f"Warning: {args.player!r} is still in config/players.json. Remove it and run "
            "make infra-plan and make infra-apply, or the next collector run recreates the data.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
