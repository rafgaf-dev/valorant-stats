"""Vote counts and per-day voter records, kept in the collector's table.

Items, in the player's partition (so `make delete-player` removes them too):
    SK = VOTES               fair, tooGenerous: running counts
    SK = VOTER#<voter-hash>  choice, expiresAt (TTL): one per viewer per day
"""

from typing import Any

CHOICES = ("fair", "tooGenerous")
COUNTS_SORT_KEY = "VOTES"


class VoteStore:
    def __init__(self, table: Any) -> None:
        self._table = table
        self._client = table.meta.client

    def counts(self, player_id: str) -> dict[str, int]:
        item = self._table.get_item(Key=_key(player_id, COUNTS_SORT_KEY)).get("Item", {})
        return {choice: int(item.get(choice, 0)) for choice in CHOICES}

    def vote_of(self, player_id: str, voter: str) -> str | None:
        item = self._table.get_item(Key=_key(player_id, f"VOTER#{voter}")).get("Item")
        return str(item["choice"]) if item else None

    def cast(self, player_id: str, voter: str, choice: str, expires_at: int) -> bool:
        """Records the vote and counts it, atomically. False if this voter already voted."""
        # The resource's client takes plain Python values, like the Table methods do.
        try:
            self._client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": self._table.name,
                            "Item": {
                                **_key(player_id, f"VOTER#{voter}"),
                                "choice": choice,
                                "expiresAt": expires_at,
                            },
                            "ConditionExpression": "attribute_not_exists(SK)",
                        }
                    },
                    {
                        "Update": {
                            "TableName": self._table.name,
                            "Key": _key(player_id, COUNTS_SORT_KEY),
                            "UpdateExpression": "ADD #choice :one",
                            "ExpressionAttributeNames": {"#choice": choice},
                            "ExpressionAttributeValues": {":one": 1},
                        }
                    },
                ]
            )
        except self._client.exceptions.TransactionCanceledException:
            if self.vote_of(player_id, voter) is None:
                raise  # cancelled for some other reason, such as a conflicting write
            return False
        return True


def _key(player_id: str, sort_key: str) -> dict[str, str]:
    return {"PK": f"PLAYER#{player_id}", "SK": sort_key}
