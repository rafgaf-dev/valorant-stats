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

The browser never calls the Riot API. A scheduled collector fetches data from
Riot, stores it, and publishes a precomputed JSON summary that the frontend
reads as a static file.

### Non-goals

- No arbitrary player lookup, search, or user accounts.
- No match history browser. The page shows only the summary.
- No custom domain for now. The generated CloudFront URL is enough.
- No multi-environment setup (dev/stage/prod). There is one environment.

## 2. Gate zero: confirm Riot API access

Everything else depends on this, so do it before writing any more backend code.

1. Check the Riot Developer Portal for the key types that can call
   `val-match-v1` (match data). Valorant match endpoints have historically
   required an approved **production** key. Valorant products have also been
   required to use **Riot Sign On (RSO)**, so each tracked player opts in
   themselves. Development keys expire every 24 hours, so a scheduled collector
   can't run on one.
2. Register the app honestly as a small, noncommercial fan dashboard for a
   friend group, and apply for the key type that the portal says is required.
3. Once you have a working key, fetch one real account, match list, and match
   by hand. Save the sanitized responses as test fixtures
   (`collector/tests/fixtures/`). All parsing code is written against these
   files, not against assumptions.
4. Ask the friend for consent. Their Riot ID, their stats, and the jokes about
   them will be on a public URL. If RSO is required, they have to opt in anyway.

**If access is denied or requires RSO**, stop and choose one of these before
continuing:

- Add an RSO opt-in flow as an extra milestone. This needs a small callback
  endpoint (one Lambda function URL) and token storage.
- Use a third-party Valorant data API as the data source. Read its terms first.
  Only the `riot.py` client module would change.

### Riot endpoint facts to verify against the fixtures

| Purpose | Host | Path |
| --- | --- | --- |
| Riot ID → PUUID | `europe.api.riotgames.com` (account-v1 uses regional routing) | `/riot/account/v1/accounts/by-riot-id/{gameName}/{tagLine}` |
| Match list | `eu.api.riotgames.com` (Valorant uses shard routing) | `/val/match/v1/matchlists/by-puuid/{puuid}` |
| Match detail | `eu.api.riotgames.com` | `/val/match/v1/matches/{matchId}` |

- Competitive matches have `matchInfo.queueId == "competitive"`.
- Remakes and abandoned games have `matchInfo.isCompleted == false`. Exclude them.
- Wins come from `teams[].won`. If no team won, the match was a draw. Confirm
  how draws appear in the fixture.
- **Headshots are not in `players[].stats`.** They are per round, under
  `roundResults[].playerStats[]` (the entry matching the player's PUUID) →
  `damage[]` → `headshots`, `bodyshots`, `legshots`. These are *hits*, not
  shots fired.
- The match list returns recent history only, not the player's full career.
  That is why the long-term metric is labelled "Since tracking", not "Career".

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
                                         │  └──► Riot API (europe / eu hosts)
                                         └──► Secrets Manager (Riot API key)

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
| Secrets Manager | One secret, the Riot API key. Terraform creates the secret *container* only. The value is set with the AWS CLI, so it never enters Terraform state or git. |
| CloudWatch | Log group with 14-day retention. Custom metrics: `SuccessfulRuns`, `MatchesImported`, `RiotErrors`. |
| SNS | One email subscription for alarms. |
| AWS Budgets | Monthly budget (for example $5), with alerts at 80% actual and 100% forecast. |

Region: `eu-west-1`, close to the EU Riot hosts. Budgets and CloudFront are
global.

## 4. Data model (DynamoDB, single table)

| Item | PK | SK | Attributes |
| --- | --- | --- | --- |
| Match | `PLAYER#<playerId>` | `MATCH#<playedAt ISO-8601 UTC>#<matchId>` | `matchId`, `queue`, `playedAt`, `result` (`win`/`loss`/`draw`), `kills`, `deaths`, `assists`, `headshots`, `bodyshots`, `legshots`, `agent`, `parserVersion` |
| Import run | `PLAYER#<playerId>` | `RUN#<startedAt ISO-8601 UTC>` | `status` (`success`/`partial`/`failed`), `matchesFound`, `matchesImported`, `errorCode`, `durationMs`, `expiresAt` (TTL, 90 days) |

- The sort key starts with the timestamp, so "latest 15 matches" is one
  `Query` with `ScanIndexForward=false`.
- Riot fills in `playedAt` and `matchId`, so the key is the same on every
  import. Writes use `PutItem` with `attribute_not_exists(SK)`, which makes
  re-imports idempotent.
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
tested without AWS or Riot.

```text
collector/src/collector/
  riot.py      HTTP client: auth header, timeouts, rate limits, error mapping
  parse.py     match JSON → MatchRecord (pure)
  metrics.py   list[MatchRecord] → windows (pure)
  store.py     DynamoDB reads and writes
  publish.py   writes summary.json and raw match JSON to S3
  handler.py   orchestration, structured logging, metrics
```

For each run:

1. Read the Riot key from Secrets Manager (cached for the life of the Lambda
   container) and load `PLAYERS`.
2. For each player, handled **independently** so that one failure doesn't
   affect the others:
   1. Resolve the Riot ID to a PUUID.
   2. Fetch the match list and keep competitive entries whose IDs aren't stored
      yet.
   3. Fetch the details for at most `MAX_DETAILS_PER_RUN` (default 30) new
      matches, oldest first. The backfill finishes over several runs instead of
      exceeding rate limits.
   4. Parse, skip incomplete matches, and write them idempotently.
   5. Query all of the player's matches, compute both windows, and publish
      `summary.json`. If nothing new was imported and a summary exists, skip
      the publish.
   6. Write an import-run item.
3. Emit one structured JSON log line per player and per run, and the CloudWatch
   metrics through Embedded Metric Format (no extra API calls).
4. The run status is `success` if all players succeeded, `partial` if some
   did, and `failed` if none did. The handler raises only on `failed`, so the
   Lambda error metric means something.

### Riot error handling

| Response | Behavior |
| --- | --- |
| `200` | Continue. |
| `404` on account lookup | Mark this player failed (`riot_account_not_found`) and continue with the next player. |
| `401` / `403` | Key is invalid, expired, or lacks access. Stop the whole run, status `failed`, error code `riot_auth`. Don't retry. |
| `429` | Wait for `Retry-After` once if it is ≤ 10s. Otherwise stop the run cleanly. Previously published summaries stay unchanged. |
| `5xx` / timeout | Up to 2 retries with exponential backoff and jitter, then fail this player. |

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
  registered trademarks of Riot Games, Inc."
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
    fixtures/             sanitized real Riot responses + expected summary
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
- **The Riot key never touches state.** After the first apply, set it with
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
- **`parse.py`:** the real fixtures, an incomplete match (skipped), a draw,
  per-round headshot aggregation, and the player not found in the match
  (error, not a silent zero).
- **`riot.py`:** 401/403/404/429 (with and without `Retry-After`), 5xx with
  retries, and timeouts. Uses a stubbed opener, with no network access.
- **`handler.py`:** with moto for DynamoDB, S3, and Secrets Manager. Checks
  idempotent re-runs (no duplicates), partial failure (one player fails, the
  other publishes), the per-run detail cap, and that the summary isn't
  overwritten on failure.
- **Contract:** the collector output for the fixtures equals
  `summary.expected.json`, and the frontend renders that same file.
- **Frontend:** loading, error, empty, stale, and normal states, plus the
  verdict function.

### Deployment checks

- `terraform plan` is reviewed before each apply. The deploy workflow prints it.
- The first collector run is invoked manually (`make invoke`) before the
  schedule is enabled. Check the logs and the published summary.
- `grep` the built `dist/` for the Riot key prefix (`RGAPI-`) in CI. The build
  must not contain it.
- Revoke the key or point `PLAYERS` at a bad Riot ID. The `failed` run should
  raise the alarm email and the site should keep showing the last summary.
- Check CloudFront response headers: HTTPS redirect, caching as specified, and
  security headers present.

## 12. Milestones

Each milestone is one or more small PRs that pass CI.

0. **Riot access:** key approved, consent obtained, real fixtures captured
   (section 2).
1. **Repo hygiene:**
   - LICENSE, the new layout, `pyproject.toml`, and ESLint/Vitest.
   - `ci.yml`.
   - Fix `.gitignore`: remove the duplicated Terraform block and overly broad
     patterns (`build/`, `*.bin`, `env/`), and add `config/players.json`.
2. **Collector core:** `parse.py` and `metrics.py` against the fixtures, with
   tests.
3. **Collector I/O:** `riot.py`, `store.py`, `publish.py`, and `handler.py`
   with moto tests. A `make collect-local` target runs the collector against
   real Riot data with `RIOT_API_KEY` from the shell environment and writes the
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
   deploy, cost, disclaimer. Re-check the Riot policies before sharing the URL.

## 13. Decision log

| Decision | Choice | Reason |
| --- | --- | --- |
| Region / queue | EU, Competitive only | Where the friend plays; the other queues aren't comparable. |
| Player list | `config/players.json` (gitignored) | Editable list without committing real Riot IDs. |
| Recent window | Last 15 completed matches | Still meaningful after a break, unlike a time window. |
| Main stat | K/D (`max(deaths,1)`), K/D/A shown | Chosen by the owner. Named `kd`, never "KDA". |
| Long-term window | "Since tracking", not "Career" | Riot's match list doesn't return full history. |
| Storage | DynamoDB + static summary JSON | ~$1/month. No VPC, NAT, RDS, or read API needed for this data volume. |
| Riot key | Shell env locally, Secrets Manager in AWS | Never in git, the bundle, or Terraform state. |
| Domain | CloudFront-generated URL | A custom domain isn't worth the cost yet. |
| Artwork | Local copy under Riot's fan-content policy | Avoids hotlinking. Licensing is stated accurately. |
| Database availability | N/A (DynamoDB is multi-AZ by default) | Replaces the earlier single-AZ RDS decision. |
