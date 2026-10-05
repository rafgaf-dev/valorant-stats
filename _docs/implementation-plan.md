# Valorant Stats Implementation Plan

## 1. Product goal

A small, playful dashboard showing a friend's Valorant performance. The first
profile is a friend who mostly plays Neon. The page shows:

- Neon artwork, the player's display name, region (EU), and queue (Competitive).
- **K/D**, with the full K/D/A totals beside it.
- **Win rate**, with the W–L–D record.
- **Headshot %**.

Each metric compares **Recent** (the last 15 completed competitive matches)
with **Since tracking** (all stored competitive matches since the first
successful import). Every metric shows its sample size, and the page shows
when the data was last refreshed.

The browser never calls a stats API. A scheduled collector fetches match data
from the HenrikDev API (section 2), stores it, and publishes a precomputed JSON
summary that the frontend reads as a static file.

### Non-goals

- No arbitrary player lookup, search, or user accounts.
- No match history browser. The page shows only the summary.
- No custom domain for now. The generated CloudFront URL is enough.
- No multi-environment setup (dev/stage/prod). There is one environment.

## 2. Data source: HenrikDev API

### Why not the official Riot API

Tested on 2026-10-04: a Riot development key can call `account-v1` but gets
`403 Forbidden` on `val-match-v1`. Riot offers no development-tier access to
Valorant match data. The only route is a production key for a registered
product, which Riot grants to public apps for a wide audience (with Riot Sign
On). A private dashboard for a friend group doesn't fit that.

### What HenrikDev is

[HenrikDev](https://docs.henrikdev.xyz) is a community-run, **unofficial**
Valorant API. It serves match data by Riot ID or PUUID, with no Riot Sign On.
Trade-offs, accepted for this project:

- It isn't endorsed by Riot. It gets data from Riot's own services, and it
  could break, change, or shut down. Its compatibility with Riot's terms is
  unclear. The README and the page footer say where the data comes from.
- Keys come from the [HenrikDev dashboard](https://api.henrikdev.xyz/dashboard/)
  (joining its Discord is required). A **Basic** key allows 30 requests per
  minute. Every background request it makes to Riot for an uncached match also
  counts against that limit.
- Only `henrikdev.py` (the HTTP client) and `parse.py` know about this source.
  Switching to the official API later means replacing those two modules.

### Endpoints used

All requests send the key in the `Authorization` header. Affinity is `eu`,
platform `pc`. Specs come from the published OpenAPI document
(`https://api.henrikdev.xyz/openapi.json`, v4.6.0 at the time of writing).

| Purpose | Path | Notes |
| --- | --- | --- |
| Riot ID → PUUID | `GET /valorant/v2/account/{name}/{tag}` | `data.puuid`, `data.region`. |
| Recent matches (full) | `GET /valorant/v4/by-puuid/matches/eu/pc/{puuid}?mode=competitive&size=10` | Authoritative source for new matches. |
| Match history (light) | `GET /valorant/v1/by-puuid/stored-matches/eu/{puuid}?mode=competitive` | One-time backfill of older matches. |
| Match details (full) | `GET /valorant/v4/match/eu/{match_id}` | Only for backfilled records whose result the score can't decide (surrenders). |

### Field facts (from the OpenAPI schemas; verify against the fixtures)

- **v4 match:**
  - Competitive matches have `metadata.queue.id == "competitive"`.
  - Remakes and abandoned games have `metadata.is_completed == false`. Exclude them.
  - Start time is `metadata.started_at` (ISO-8601), and the ID is `metadata.match_id`.
  - Per-player totals are in `players[].stats`: `kills`, `deaths`, `assists`,
    `headshots`, `bodyshots`, `legshots`. These are *hits*, not shots fired.
    No per-round aggregation is needed.
  - The result comes from `teams[]`, the entry whose `team_id` matches the
    player's `team_id`: `won`, and `rounds.won`/`rounds.lost`. Equal rounds
    means a draw.
- **Stored match record:**
  - `meta.id`, `meta.started_at`, and `meta.mode` (`"Competitive"`).
  - `stats.team` with `stats.kills`/`deaths`/`assists`, and
    `stats.shots.head`/`body`/`leg`.
  - `teams.red`/`teams.blue` are round wins, and there is **no completed flag
    and no winner field**. The result is derived from the score using
    Valorant's rules:

    | Score | Meaning | Result |
    | --- | --- | --- |
    | 1 round or fewer in total | Remake (only possible in round 1) | Skip the record. |
    | One team on 13 or more, scores differ | Regulation or overtime win | Higher score wins. |
    | Equal, both on 12 or more | Overtime draw | Draw. |
    | Anything else (no team on 13) | Surrender (possible from round 5); the surrendering team loses regardless of score | Fetch match details (v4) and use `teams[].won`. |

    The captured records include one surrender (3–10) and one overtime draw
    (14–14).
- **Stored history has gaps.** HenrikDev only keeps matches that some API user
  has requested, and its docs warn there can be holes. That is acceptable for
  the long-term window, which is labelled "Since tracking" and shows its start
  date and sample size.

### Gate zero checklist

1. ✅ Confirm the official API is unavailable: Riot key → 403 on match data.
2. ✅ Get a HenrikDev Basic key, and keep it only in the shell environment
   (`HENRIKDEV_API_KEY`) and, later, in Secrets Manager.
3. ✅ Run `make capture-fixtures`. It saves the account, recent v4 matches,
   and stored history to `collector/tests/fixtures/henrikdev/`, after replacing
   Riot IDs, PUUIDs, party IDs, and match IDs, and it cross-checks the two
   sources. All parsing code is written against these files. Captured
   2026-10-05 from the project owner's own account: 5 v4 matches and 20 of 138 stored records. All 5 matches agree
   across both sources. `rounds` and `kills` are dropped from the v4 fixtures
   because the collector doesn't read them. Re-runs with `OFFLINE=1` use the
   local raw cache and cost no API requests.
4. Ask the friend for consent **before the site is deployed publicly** (it is a
   surprise until then). Their Riot ID, their stats, and the jokes about them
   will be on a public URL. Until then, development uses the owner's account.

## 3. Architecture

```text
                    ┌──────────────── CloudFront (HTTPS, generated URL) ───────────────┐
Browser ──────────► │  /*        → S3 site bucket (private, OAC)   long cache, hashed   │
                    │  /data/*   → S3 data bucket (private, OAC)   max-age 300s         │
                    └──────────────────────────────────────────────────────────────────┘
                                                        ▲
                                                        │ PutObject summary.json
EventBridge Scheduler (every 6h) ──► Collector Lambda ──┤
                                         │  │           └──► DynamoDB (matches, import runs)
                                         │  └──► HenrikDev API (api.henrikdev.xyz)
                                         └──► Secrets Manager (HenrikDev API key)

CloudWatch: collector errors, "no successful run in 12h" alarm → SNS email
AWS Budgets: monthly budget alert → email
```

Why this design:

- **No VPC, no NAT Gateway, no RDS.** A NAT Gateway alone costs about
  $32/month, and Lambdas in private subnets would also need a NAT or interface
  endpoints to reach Secrets Manager. The data is a few hundred matches, so a
  relational database isn't needed.
- **No read API.** The summary only changes when the collector runs. A static
  JSON file behind CloudFront is faster, cheaper, has no cold starts, and needs
  no CORS because it is served from the same origin as the frontend.
- **One Lambda with no third-party runtime dependencies.** The collector uses
  the standard library (`urllib.request`) and `boto3`, which the Lambda runtime
  already provides. Packaging is a plain zip, so there are no platform-specific
  wheels to build on Windows.

### AWS components

| Component | Configuration |
| --- | --- |
| S3 site bucket | Private, Block Public Access on, versioning off, served only through CloudFront OAC. |
| S3 data bucket | Private, Block Public Access on, versioning on (cheap rollback of a bad summary), OAC. |
| CloudFront | Default behavior → site bucket. `/data/*` → data bucket with a 5-minute TTL. `index.html` gets `no-cache`. Hashed assets get `immutable`. Security headers via a response headers policy. |
| DynamoDB | One table, on-demand billing, PITR on, TTL attribute for import-run records. |
| Collector Lambda | Python 3.13, arm64, 256 MB, 5-minute timeout, reserved concurrency 1 (runs never overlap), no VPC. |
| EventBridge Scheduler | `rate(6 hours)`, configurable. Retry policy: 0 retries (the next scheduled run is the retry). |
| Secrets Manager | One secret, the HenrikDev API key. Terraform creates the secret *container* only. The value is set with the AWS CLI, so it never enters Terraform state or git. |
| CloudWatch | Log group with 14-day retention. Custom metrics: `SuccessfulRuns`, `MatchesImported`, `ApiErrors`. |
| SNS | One email subscription for alarms. |
| AWS Budgets | Monthly budget (for example $5), with alerts at 80% actual and 100% forecast. |

Region: `eu-west-1`, close to the EU players. Budgets and CloudFront are
global.

## 4. Data model (DynamoDB, single table)

| Item | PK | SK | Attributes |
| --- | --- | --- | --- |
| Match | `PLAYER#<playerId>` | `MATCH#<playedAt ISO-8601 UTC>#<matchId>` | `matchId`, `queue`, `playedAt`, `result` (`win`/`loss`/`draw`), `kills`, `deaths`, `assists`, `headshots`, `bodyshots`, `legshots`, `agent`, `source` (`v4`/`stored`), `parserVersion` |
| Import run | `PLAYER#<playerId>` | `RUN#<startedAt ISO-8601 UTC>` | `status` (`success`/`partial`/`failed`), `matchesFound`, `matchesImported`, `errorCode`, `durationMs`, `expiresAt` (TTL, 90 days) |

- The sort key starts with the timestamp, so "latest 15 matches" is one
  `Query` with `ScanIndexForward=false`.
- The API fills in `playedAt` and `matchId`, so the key is the same on every
  import. Writes use `PutItem` with the condition
  `attribute_not_exists(SK) OR source = stored`. Re-imports are idempotent,
  and a full v4 record replaces a lighter stored record for the same match.
- `parserVersion` makes it possible to re-parse stored matches if the parsing
  logic changes. For that, also store the raw match JSON in the data bucket
  under `raw/<matchId>.json` (not served by CloudFront).
- PUUIDs are not secret and don't need encryption. They are resolved from the
  Riot ID on every run and never stored or published.

### Player configuration

The tracked players live in `config/players.json`. This file is **gitignored**
because it contains real Riot IDs. `config/players.example.json` is committed
to show the format:

```json
[
  {
    "id": "neon-main",
    "gameName": "Example",
    "tagLine": "EUW",
    "displayName": "The Neon Menace",
    "agent": "Neon"
  }
]
```

Terraform reads the file with `jsondecode(file(...))` and passes it to the
Lambda as the `PLAYERS` environment variable. CI falls back to the example file
so that `terraform validate` works without the real one.

## 5. Metric definitions

All metrics use **completed competitive matches only**. Both windows are
computed from summed totals, never by averaging per-match ratios.

| Metric | Formula | Edge cases |
| --- | --- | --- |
| K/D | `Σkills / max(Σdeaths, 1)` | Zero deaths count as one. K/D/A totals are shown beside it. |
| Win rate | `wins / completed matches` | Draws count as matches but not wins. The W–L–D record is shown. |
| Headshot % | `Σheadshot hits / Σ(head + body + leg hits)` | No hits → `null`. |

- **Recent** = the 15 most recent matches. **Since tracking** = all stored
  matches, plus the date of the earliest one.
- A window with zero matches publishes `null` values, not `0`. The UI shows
  "not enough data".
- Values are published unrounded. Rounding is a display concern handled by the
  frontend.
- The definitions live in one module (`collector/src/collector/metrics.py`),
  are unit-tested, and are explained in a small info note in the UI.

## 6. Published contract: `/data/players/{playerId}/summary.json`

```json
{
  "schemaVersion": 1,
  "player": { "id": "neon-main", "displayName": "The Neon Menace", "agent": "Neon", "region": "eu" },
  "queue": "competitive",
  "generatedAt": "2026-10-04T12:00:00Z",
  "windows": {
    "recent": {
      "matches": 15, "wins": 9, "losses": 5, "draws": 1,
      "kills": 156, "deaths": 110, "assists": 74,
      "headshots": 120, "bodyshots": 380, "legshots": 22,
      "kd": 1.4181818, "winRate": 0.6, "headshotRate": 0.2298850
    },
    "sinceTracking": {
      "since": "2026-06-01T18:22:00Z",
      "matches": 312, "wins": 160, "losses": 148, "draws": 4,
      "kills": 1842, "deaths": 1561, "assists": 903,
      "headshots": 1400, "bodyshots": 5600, "legshots": 400,
      "kd": 1.1800128, "winRate": 0.5128205, "headshotRate": 0.1891892
    }
  },
  "lastImport": { "status": "success", "finishedAt": "2026-10-04T12:00:00Z" }
}
```

- The summary is written with `Cache-Control: public, max-age=300` and
  `Content-Type: application/json`.
- The schema is defined once as a TypeScript type in `frontend/src/api.ts` and
  checked by a contract test: the collector's output for a fixture is compared
  with `collector/tests/fixtures/summary.expected.json`, and the frontend tests
  load the same file.
- The frontend treats `generatedAt` older than 24 hours as **stale** and shows
  a banner, but still renders the numbers.
- Any change to the schema increments `schemaVersion`.

## 7. Collector behavior

Code layout: pure logic is kept separate from I/O so that most of it can be
tested without AWS or the network.

```text
collector/src/collector/
  henrikdev.py HTTP client: auth header, timeouts, rate limits, error mapping
  records.py   MatchRecord, Result, Source (shared data types)
  parse.py     v4 match / stored record JSON → MatchRecord (pure)
  metrics.py   list[MatchRecord] → windows (pure)
  store.py     DynamoDB reads and writes
  publish.py   writes summary.json and raw match JSON to S3
  handler.py   orchestration, structured logging, metrics
```

For each run:

1. Read the HenrikDev key from Secrets Manager (cached for the life of the Lambda
   container) and load `PLAYERS`.
2. For each player, handled **independently** so that one failure doesn't
   affect the others:
   1. Resolve the Riot ID to a PUUID (account v2).
   2. **First run only** (no matches stored yet): backfill from stored matches
      (v1) and write them with `source = stored`. Records whose result the
      score can't decide (surrenders, see section 2) get one match-details
      request each.
   3. Fetch the 10 most recent competitive matches (v4). Six-hour runs mean
      a player would have to play more than 10 ranked games between runs to
      miss one.
   4. Parse, skip matches with `is_completed == false`, and write them
      idempotently with `source = v4`.
   5. Query all of the player's matches, compute both windows, and publish
      `summary.json`. If nothing new was imported and a summary exists, skip
      the publish.
   6. Write an import-run item.
3. Emit one structured JSON log line per player and per run, and the CloudWatch
   metrics through Embedded Metric Format (no extra API calls).
4. The run status is `success` if all players succeeded, `partial` if some
   did, and `failed` if none did. The handler raises only on `failed`, so the
   Lambda error metric means something.

### API error handling

| Response | Behavior |
| --- | --- |
| `200` | Continue. |
| `404` (error code 22, 23, or 24) | Account not found or has no region yet. Mark this player failed (`account_not_found`) and continue with the next player. |
| `401` / `403` | Key missing or invalid. Stop the whole run, status `failed`, error code `api_auth`. Don't retry. |
| `429` | Wait for `Retry-After` / `X-RateLimit-Reset` once if it is ≤ 60s. Otherwise stop the run cleanly. Previously published summaries stay unchanged. |
| `400` | A bug in the request. Fail this player with the API's error code in the log. |
| `5xx` / timeout | Up to 2 retries with exponential backoff and jitter, then fail this player. HenrikDev returns `500` (code 9) when Riot itself is unavailable. |

Requests are spaced at least 2.1s apart, which stays under the Basic key's 30
requests per minute even when HenrikDev has to fetch uncached matches from Riot.

The previous `summary.json` is only overwritten after a successful computation,
so the site always shows the last good data.

### Data deletion

`make delete-player PLAYER=<id>` runs a script that deletes the player's
DynamoDB items and their objects under `data/players/<id>/`, then invalidates
`/data/players/<id>/*` in CloudFront. Removing the player from
`config/players.json` stops future collection.

## 8. Frontend plan

- **Data loading:** `api.ts` fetches `/data/players/${PLAYER_ID}/summary.json`
  as a relative URL, so there is no API base URL to configure.
  `VITE_PLAYER_ID` selects the profile at build time.
- **Local development:** a small dev-only Vite middleware in `vite.config.ts`
  serves `frontend/dev-data/` under `/data`. It contains sample summaries for
  the normal, empty (`null` metrics), and stale states. This replaces
  `lambda/api/local_server.py`, and `make dev` becomes just `vite`.
- **Components:**
  - `PlayerHeader`: art, name, and metadata (region, queue, last updated),
    taken from the summary instead of hardcoded.
  - `StatCard`: recent value, since-tracking value, delta, sample size, and
    K/D/A or W–L–D detail.
  - `MetricNotes`: replaces `RecentGames`, which is really a footnote. It
    explains the formulas and the zero-death rule.
  - `Verdict`: the playful "cooking/trolling" ruling. Its logic lives in a
    tested pure function.
- **States:** loading, error (fetch failed or unknown schema version), empty
  (no matches yet), stale (older than 24h), and normal.
- **Artwork:** download the Neon portrait into `frontend/src/assets/` and add
  `frontend/src/assets/ASSETS.md` with its source and the attribution. Don't
  hotlink a community CDN. The art belongs to Riot and is used under Riot's
  fan-content policy ("Legal Jibber Jabber"), which allows free fan projects
  with the disclaimer. It is not open source.
- **Footer disclaimer** (required wording style): "valorant-stats isn't
  endorsed by Riot Games and doesn't reflect the views or opinions of Riot
  Games or anyone officially involved in producing or managing Riot Games
  properties. Riot Games and all associated properties are trademarks or
  registered trademarks of Riot Games, Inc." Followed by: "Match data from
  the unofficial [HenrikDev API](https://docs.henrikdev.xyz)."
- **Accessibility:** use real `<table>` or `<dl>` semantics for the numbers,
  give deltas a text label (don't rely on colour alone), make the info note
  keyboard-accessible, and support `prefers-reduced-motion` for decorative
  effects.
- **Tooling:** move `vite`, `typescript`, and `@vitejs/plugin-react` to
  `devDependencies`. Add ESLint (typescript-eslint, react-hooks) and Vitest
  with Testing Library.

## 9. Repository layout

```text
.github/workflows/
  ci.yml                  lint, test, build, terraform fmt/validate on every PR and push to main
  deploy.yml              manual dispatch: terraform apply + frontend publish via OIDC
_docs/implementation-plan.md
collector/
  pyproject.toml          ruff, pytest, moto (dev only); no runtime deps
  src/collector/...
  tests/
    fixtures/henrikdev/   pseudonymized real API responses + expected summary
  scripts/
    capture_fixtures.py   saves the fixtures (make capture-fixtures)
config/
  players.example.json    committed; players.json is gitignored
frontend/
  dev-data/               sample summaries for local development
  src/...
infrastructure/
  bootstrap/              one-time: state bucket (local state, run once)
  versions.tf             terraform + provider pins, S3 backend (use_lockfile = true)
  variables.tf  outputs.tf
  storage.tf              DynamoDB table, site + data buckets
  secrets.tf
  collector.tf            Lambda, its IAM role/policy, log group
  scheduler.tf            schedule + its IAM role
  frontend.tf             CloudFront, OAC, bucket policies, cache/headers policies
  monitoring.tf           SNS, alarms, budget
  github_oidc.tf          OIDC provider + deploy role scoped to this repo's main branch
scripts/
  delete_player.py
LICENSE                   MIT
Makefile
README.md
```

Changes from the current tree:

- `lambda/` moves to `collector/`.
- `lambda/api/`, `lambda/schema.sql`, `scripts/build.sh`, and
  `scripts/deploy.sh` are deleted.
- The empty `api.tf`, `database.tf`, `lambdas.tf`, `iam.tf`, and
  `providers.tf` are deleted. `terraform.tf` becomes `versions.tf`.

## 10. Terraform

- Format with `terraform fmt` (2-space indentation). Pin the provider with a
  `~>` constraint and commit `.terraform.lock.hcl`.
- **Bootstrap once:** `infrastructure/bootstrap/` creates the versioned,
  encrypted state bucket with local state. The main config uses an S3 backend
  with `use_lockfile = true`, so no DynamoDB lock table is needed.
- **IAM is defined next to its resource,** with the narrowest scope possible:
  - Collector: `secretsmanager:GetSecretValue` on one secret ARN, DynamoDB
    read/write on one table, and `s3:PutObject` on `data/players/*` and
    `raw/*` of the data bucket.
  - Scheduler: `lambda:InvokeFunction` on the collector only.
  - Bucket policies allow `s3:GetObject` only from this CloudFront
    distribution (OAC with an `AWS:SourceArn` condition).
- **The HenrikDev key never touches state.** After the first apply, set it with
  `aws secretsmanager put-secret-value --secret-id <output> --secret-string file://-`.
- **CI deploys without access keys.** GitHub OIDC assumes a role restricted to
  `repo:<owner>/valorant-stats:ref:refs/heads/main`. No long-lived AWS keys are
  stored in GitHub.
- **Lambda packaging** uses the `archive_file` data source over
  `collector/src/`, with `source_code_hash` so a change in the code triggers a
  redeploy.
- Default tags on every resource: `Project = valorant-stats`, `ManagedBy = terraform`.
- **Teardown:** `terraform destroy` removes everything except the state bucket.
  Empty the versioned data bucket first (`force_destroy = true` on both
  buckets is acceptable for this project).

### Expected cost

| Item | Monthly |
| --- | --- |
| Lambda, Scheduler, DynamoDB on-demand, S3, CloudFront (low traffic) | ~$0 (free tier or cents) |
| Secrets Manager (1 secret) | $0.40 |
| CloudWatch logs and custom metrics (3) | ~$0.90 |
| **Total** | **≈ $1–2** |

The budget alarm catches anything unexpected.

## 11. Quality gates

### CI (`ci.yml`, required to pass before merging)

- Collector: `ruff check`, `ruff format --check`, `pytest` (with coverage report).
- Frontend: `npm ci`, `eslint`, `tsc --noEmit`, `vitest run`, `vite build`.
- Infrastructure: `terraform fmt -check -recursive`, `terraform init -backend=false`, `terraform validate`.
- Dependabot for npm, pip, GitHub Actions, and Terraform.

### Tests

- **`metrics.py`:** zero deaths, zero matches (`null`s), zero hits, fewer than
  15 matches, draws, and sums vs per-match ratios.
- **`parse.py`:** the real fixtures for both v4 matches and stored records,
  an incomplete match (skipped), a draw, and the player not found in the match
  (error, not a silent zero).
- **`henrikdev.py`:** 401/403/404/429 (with and without `Retry-After`), 5xx with
  retries, and timeouts. Uses a stubbed opener, with no network access.
- **`handler.py`:** with moto for DynamoDB, S3, and Secrets Manager. Checks
  idempotent re-runs (no duplicates), partial failure (one player fails, the
  other publishes), backfill only on the first run, a v4 record replacing a
  stored one, and that the summary isn't
  overwritten on failure.
- **Contract:** the collector output for the fixtures equals
  `summary.expected.json`, and the frontend renders that same file.
- **Frontend:** loading, error, empty, stale, and normal states, plus the
  verdict function.

### Deployment checks

- `terraform plan` is reviewed before each apply. The deploy workflow prints it.
- The first collector run is invoked manually (`make invoke`) before the
  schedule is enabled. Check the logs and the published summary.
- `grep` the built `dist/` for API key prefixes (`HDEV-`, `RGAPI-`) in CI. The build
  must not contain it.
- Revoke the key or point `PLAYERS` at a bad Riot ID. The `failed` run should
  raise the alarm email and the site should keep showing the last summary.
- Check CloudFront response headers: HTTPS redirect, caching as specified, and
  security headers present.

## 12. Milestones

Each milestone is one or more small PRs that pass CI.

0. **Data access:** official API ruled out, HenrikDev key obtained, real
   fixtures captured (section 2). Add a match-details fixture for the
   surrender case when `parse.py` is written (about 2 API requests).
1. **Repo hygiene:**
   - LICENSE, the new layout, `pyproject.toml`, and ESLint/Vitest.
   - `ci.yml`.
   - Fix `.gitignore`: remove the duplicated Terraform block and overly broad
     patterns (`build/`, `*.bin`, `env/`), and add `config/players.json`.
2. **Collector core:** `parse.py` and `metrics.py` against the fixtures, with
   tests.
3. **Collector I/O:** `henrikdev.py`, `store.py`, `publish.py`, and `handler.py`
   with moto tests. A `make collect-local` target runs the collector against
   real data with `HENRIKDEV_API_KEY` from the shell environment and writes the
   summary to `frontend/dev-data/`.
4. **Frontend:** move to the new contract and dev data, update the components,
   add the states, local art and ASSETS.md, and tests.
5. **Infrastructure:** bootstrap, storage, secrets, collector, and scheduler
   (disabled). Apply, set the secret, invoke manually.
6. **Delivery:** CloudFront, the frontend publish (`aws s3 sync --delete`
   on the site bucket plus an `index.html` invalidation), and the GitHub OIDC
   deploy workflow.
7. **Operations:** alarms, budget, and the delete-player script. Enable the
   schedule.
8. **README:** architecture diagram, screenshot, how to run locally, how to
   deploy, cost, data source, disclaimer. Get the friend's consent, and
   re-check Riot's fan-content policy and HenrikDev's terms, before sharing the
   URL.

## 13. Decision log

| Decision | Choice | Reason |
| --- | --- | --- |
| Region / queue | EU, Competitive only | Where the friend plays; the other queues aren't comparable. |
| Player list | `config/players.json` (gitignored) | Editable list without committing real Riot IDs. |
| Recent window | Last 15 completed matches | Still meaningful after a break, unlike a time window. |
| Main stat | K/D (`max(deaths,1)`), K/D/A shown | Chosen by the owner. Named `kd`, never "KDA". |
| Data source | HenrikDev API (unofficial) | The official API has no Valorant match access for a private app (403 on a development key; production keys are for public products). |
| Long-term window | "Since tracking", not "Career" | Stored history has gaps and doesn't go back to the start of the account. |
| Storage | DynamoDB + static summary JSON | ~$1/month. No VPC, NAT, RDS, or read API needed for this data volume. |
| API key | Shell env locally, Secrets Manager in AWS | Never in git, the bundle, or Terraform state. |
| Domain | CloudFront-generated URL | A custom domain isn't worth the cost yet. |
| Artwork | Local copy under Riot's fan-content policy | Avoids hotlinking. Licensing is stated accurately. |
| Database availability | N/A (DynamoDB is multi-AZ by default) | Replaces the earlier single-AZ RDS decision. |
