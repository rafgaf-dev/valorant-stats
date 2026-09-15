import json
import logging
import os
from datetime import datetime, timezone
from urllib.parse import quote

import psycopg2
import requests

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from shared.metrics import Match, calculate_metrics


LOG = logging.getLogger()
LOG.setLevel(logging.INFO)
REGION = "europe"
QUEUE = "competitive"


def _riot_get(session, url, api_key):
    response = session.get(url, headers={"X-Riot-Token": api_key}, timeout=10)
    if response.status_code in (401, 403, 429):
        raise RuntimeError(f"riot_http_{response.status_code}")
    response.raise_for_status()
    return response.json()


def _account(session, api_key, player):
    url = "https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{}/{}".format(
        quote(player["gameName"], safe=""), quote(player["tagLine"], safe="")
    )
    return _riot_get(session, url, api_key)


def _match_record(detail, puuid, player_id):
    info = detail["matchInfo"]
    participant = next(item for item in detail["players"] if item["puuid"] == puuid)
    stats = participant["stats"]
    player_team = participant["teamId"]
    winning_team = next((team["teamId"] for team in detail.get("teams", []) if team.get("won")), None)
    shots = stats.get("headshots", 0) + stats.get("bodyshots", 0) + stats.get("legshots", 0)
    return {
        "player_id": player_id,
        "match_id": info["matchId"],
        "played_at": datetime.fromtimestamp(info["gameStartMillis"] / 1000, timezone.utc),
        "won": winning_team is not None and player_team == winning_team,
        "kills": stats.get("kills", 0), "deaths": stats.get("deaths", 0),
        "assists": stats.get("assists", 0), "headshots": stats.get("headshots", 0), "shots": shots,
    }


def _player_matches(session, api_key, player, puuid, connection):
    list_url = f"https://{REGION}.api.riotgames.com/val/match/v1/matchlists/by-puuid/{puuid}"
    entries = _riot_get(session, list_url, api_key).get("history", [])
    competitive = [entry for entry in entries if entry.get("queueId") == QUEUE]
    records = []
    with connection.cursor() as cursor:
        for entry in competitive:
            cursor.execute("SELECT 1 FROM matches WHERE player_id = %s AND riot_match_id = %s", (player["id"], entry["matchId"]))
            if cursor.fetchone():
                continue
            detail_url = f"https://{REGION}.api.riotgames.com/val/match/v1/matches/{entry['matchId']}"
            records.append(_match_record(_riot_get(session, detail_url, api_key), puuid, player["id"]))
    return records


def _save_player(connection, player, records):
    with connection.cursor() as cursor:
        for record in records:
            cursor.execute(
                """
                INSERT INTO matches (player_id, riot_match_id, queue, played_at, won, kills, deaths, assists, headshots, shots)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (player_id, riot_match_id) DO NOTHING
                """,
                (record["player_id"], record["match_id"], QUEUE, record["played_at"], record["won"], record["kills"], record["deaths"], record["assists"], record["headshots"], record["shots"]),
            )
        cursor.execute(
            "SELECT played_at, won, kills, deaths, assists, headshots, shots FROM matches WHERE player_id = %s ORDER BY played_at DESC",
            (player["id"],),
        )
        matches = [Match(played_at=row[0].isoformat(), won=row[1], kills=row[2], deaths=row[3], assists=row[4], headshots=row[5], shots=row[6]) for row in cursor.fetchall()]
        metrics = calculate_metrics(matches)
        recent, lifetime = metrics["recent"], metrics["lifetime"]
        cursor.execute(
            """
            INSERT INTO metric_snapshots (player_id, recent_kda, lifetime_kda, recent_kills, recent_deaths, recent_assists, lifetime_kills, lifetime_deaths, lifetime_assists, recent_win_rate, lifetime_win_rate, recent_headshot_percentage, lifetime_headshot_percentage, recent_sample_size, lifetime_sample_size)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (player_id) DO UPDATE SET recent_kda = EXCLUDED.recent_kda, lifetime_kda = EXCLUDED.lifetime_kda, recent_kills = EXCLUDED.recent_kills, recent_deaths = EXCLUDED.recent_deaths, recent_assists = EXCLUDED.recent_assists, lifetime_kills = EXCLUDED.lifetime_kills, lifetime_deaths = EXCLUDED.lifetime_deaths, lifetime_assists = EXCLUDED.lifetime_assists, recent_win_rate = EXCLUDED.recent_win_rate, lifetime_win_rate = EXCLUDED.lifetime_win_rate, recent_headshot_percentage = EXCLUDED.recent_headshot_percentage, lifetime_headshot_percentage = EXCLUDED.lifetime_headshot_percentage, recent_sample_size = EXCLUDED.recent_sample_size, lifetime_sample_size = EXCLUDED.lifetime_sample_size, calculated_at = NOW()
            """,
            (player["id"], recent["kda"], lifetime["kda"], recent["kills"], recent["deaths"], recent["assists"], lifetime["kills"], lifetime["deaths"], lifetime["assists"], recent["winRate"], lifetime["winRate"], recent["headshotPercentage"], lifetime["headshotPercentage"], recent["sampleSize"], lifetime["sampleSize"]),
        )


def handler(event, _context):
    api_key = os.environ["RIOT_API_KEY"]
    players = json.loads(os.environ["RIOT_PLAYERS"])
    connection = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=5)
    imported = 0
    try:
        with requests.Session() as session:
            for player in players:
                account = _account(session, api_key, player)
                player["gameName"], player["tagLine"] = account["gameName"], account["tagLine"]
                records = _player_matches(session, api_key, player, account["puuid"], connection)
                _save_player(connection, player, records)
                imported += len(records)
        connection.commit()
        LOG.info("collector_complete players=%s imported=%s", len(players), imported)
        return {"statusCode": 200, "imported": imported}
    except Exception:
        connection.rollback()
        LOG.exception("collector_failed")
        raise
    finally:
        connection.close()