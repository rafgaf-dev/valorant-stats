import json
import os

import psycopg2


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps(body, default=str),
    }


def _connection():
    return psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=5)


def _summary(player_id, connection):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT p.id, p.display_name, p.preferred_agent,
                   s.recent_kda, s.lifetime_kda,
                   s.recent_kills, s.recent_deaths, s.recent_assists,
                   s.lifetime_kills, s.lifetime_deaths, s.lifetime_assists,
                   s.recent_win_rate, s.lifetime_win_rate,
                   s.recent_headshot_percentage, s.lifetime_headshot_percentage,
                   s.recent_sample_size, s.lifetime_sample_size, s.calculated_at
            FROM players p
            LEFT JOIN metric_snapshots s ON s.player_id = p.id
            WHERE p.id = %s AND p.enabled = TRUE
            """,
            (player_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        if row[3] is None:
            return {"player": {"id": row[0], "displayName": row[1], "agent": row[2]}, "metrics": None}

        return {
            "player": {"id": row[0], "displayName": row[1], "agent": row[2]},
            "metrics": {
                "kda": {
                    "recent": float(row[3]), "lifetime": float(row[4]),
                    "recentKills": row[5], "recentDeaths": row[6], "recentAssists": row[7],
                    "lifetimeKills": row[8], "lifetimeDeaths": row[9], "lifetimeAssists": row[10],
                    "recentSampleSize": row[15], "lifetimeSampleSize": row[16],
                },
                "winRate": {"recent": float(row[11]), "lifetime": float(row[12]), "recentSampleSize": row[15], "lifetimeSampleSize": row[16]},
                "headshotPercentage": {"recent": float(row[13]), "lifetime": float(row[14]), "recentSampleSize": row[15], "lifetimeSampleSize": row[16]},
            },
            "lastUpdatedAt": row[17],
        }


def handler(event, _context):
    path = event.get("rawPath") or event.get("path", "")
    if path == "/health":
        return _response(200, {"status": "ok"})

    path_parts = [part for part in path.split("/") if part]
    if len(path_parts) != 4 or path_parts[:3] != ["v1", "players", path_parts[2]] or path_parts[3] != "summary":
        return _response(404, {"error": "not_found"})

    player_id = path_parts[2]
    try:
        with _connection() as connection:
            payload = _summary(player_id, connection)
    except Exception:
        return _response(500, {"error": "internal_error"})

    if payload is None:
        return _response(404, {"error": "player_not_found"})
    if payload["metrics"] is None:
        return _response(503, {"error": "stats_unavailable"})
    return _response(200, payload)