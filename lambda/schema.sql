CREATE TABLE IF NOT EXISTS players (
    id TEXT PRIMARY KEY,
    game_name TEXT NOT NULL,
    tag_line TEXT NOT NULL,
    region TEXT NOT NULL DEFAULT 'europe',
    puuid TEXT,
    display_name TEXT NOT NULL,
    preferred_agent TEXT NOT NULL DEFAULT 'Neon',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS matches (
    player_id TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    riot_match_id TEXT NOT NULL,
    queue TEXT NOT NULL,
    played_at TIMESTAMPTZ NOT NULL,
    won BOOLEAN NOT NULL,
    kills INTEGER NOT NULL,
    deaths INTEGER NOT NULL,
    assists INTEGER NOT NULL,
    headshots INTEGER NOT NULL,
    shots INTEGER NOT NULL,
    source_version TEXT NOT NULL DEFAULT 'val-match-v1',
    PRIMARY KEY (player_id, riot_match_id)
);

CREATE INDEX IF NOT EXISTS matches_player_played_idx
    ON matches (player_id, played_at DESC);

CREATE TABLE IF NOT EXISTS metric_snapshots (
    player_id TEXT PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
    recent_kda NUMERIC NOT NULL,
    lifetime_kda NUMERIC NOT NULL,
    recent_kills INTEGER NOT NULL,
    recent_deaths INTEGER NOT NULL,
    recent_assists INTEGER NOT NULL,
    lifetime_kills INTEGER NOT NULL,
    lifetime_deaths INTEGER NOT NULL,
    lifetime_assists INTEGER NOT NULL,
    recent_win_rate NUMERIC NOT NULL,
    lifetime_win_rate NUMERIC NOT NULL,
    recent_headshot_percentage NUMERIC NOT NULL,
    lifetime_headshot_percentage NUMERIC NOT NULL,
    recent_sample_size INTEGER NOT NULL,
    lifetime_sample_size INTEGER NOT NULL,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS import_runs (
    id BIGSERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    matches_discovered INTEGER NOT NULL DEFAULT 0,
    matches_updated INTEGER NOT NULL DEFAULT 0,
    error_code TEXT
);