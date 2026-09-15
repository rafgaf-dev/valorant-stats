# Valorant Stats Implementation Plan

## 1. Product goal

Build a small gag-style dashboard for one or more friends' Valorant statistics.
The first supported profile is the friend who primarily plays Neon. The first
screen should show:

- Neon artwork and the friend's display name.
- KDA, with recent and lifetime values.
- Win rate, with recent and lifetime values.
- Headshot percentage, with recent and lifetime values.

"Recent" should have one explicit definition, such as the last 20 competitive
matches or the last 30 days. The initial recommendation is the last 20 matches,
because it remains meaningful when the player takes a break. "Lifetime" means
all stored matches in the selected supported game mode, starting at the first
successful import. Display the sample size and the time of the last refresh so
the comparison is not misleading.

The browser must never call the Riot API. It calls the application's read API,
which serves data collected and cached by the backend.

## 2. Target architecture

```text
Browser (React)
        |
        v
CloudFront -> private S3 bucket (static frontend)
        |
        +--> API Gateway HTTP API -> API Lambda -> PostgreSQL (private subnets)

EventBridge Scheduler -> Collector Lambda -> Riot API
                                      |
                                      v
                              PostgreSQL (private subnets)

API and Collector Lambdas -> Secrets Manager (Riot API key/database credentials)
CloudWatch Logs/Metrics/Alarms monitor both Lambdas and the API
```

### AWS components

1. **S3** stores the built React assets. Keep the bucket private and expose it
   through CloudFront using Origin Access Control. Add a custom error response
   or SPA fallback for client-side routes if routes are added later.
2. **CloudFront** provides HTTPS, caching, compression, and the public frontend
   entry point. Use an ACM certificate in `us-east-1` if a custom domain is used.
3. **API Gateway HTTP API** exposes a small read-only API. Configure CORS for the
   CloudFront origin, throttling, access logs, and a stage with an environment
   specific API URL.
4. **API Lambda** validates request parameters, queries PostgreSQL, and returns
   the latest precomputed metrics. It does not call Riot.
5. **Collector Lambda** runs on a schedule, calls Riot's supported endpoints,
   calculates/upserts match data, and records an import run. It is the only
   component that needs the Riot API key.
6. **RDS PostgreSQL** is the relational store. Use private subnets and a security
   group that permits database traffic only from the Lambda security group. For
   the learning project, begin with a small single-AZ instance and automated
   backups; consider Multi-AZ only when availability is a real requirement.
7. **VPC networking** includes private application/database subnets, route
   tables, and the smallest egress design needed by the collector. A Lambda in
   private subnets needs controlled outbound access to Riot, commonly through a
   NAT Gateway. Document the NAT hourly and data-processing cost before enabling
   it. An alternative is a public collector Lambda with no inbound access, but
   private subnets are the cleaner production shape.
8. **EventBridge Scheduler** invokes the collector, for example hourly or every
   six hours. Use a Lambda resource policy so only the scheduler can invoke it.
9. **Secrets Manager** stores the Riot key and database secret. Never place
   either value in React code, Terraform variables committed to git, logs, or
   Lambda responses. Grant each Lambda only the secret reads it needs.
10. **CloudWatch** collects logs and metrics. Alarm on collector failures,
    API 5xx responses, database storage/CPU pressure, and stale data.

## 3. Backend contract

Start with these endpoints:

### `GET /v1/players/{playerId}/summary`

Returns the display profile, selected agent, three metric comparisons, sample
counts, and refresh metadata:

```json
{
  "player": { "id": "neon-main", "displayName": "Example", "agent": "Neon" },
  "metrics": {
    "kda": { "recent": 1.42, "lifetime": 1.18, "recentSampleSize": 20, "lifetimeSampleSize": 312 },
    "winRate": { "recent": 0.55, "lifetime": 0.51, "recentSampleSize": 20, "lifetimeSampleSize": 312 },
    "headshotPercentage": { "recent": 0.23, "lifetime": 0.19, "recentSampleSize": 20, "lifetimeSampleSize": 312 }
  },
  "lastUpdatedAt": "2026-09-15T12:00:00Z"
}
```

Use stable JSON field names and return `404` for an unknown player, `503` when
cached data is unavailable, and `500` only for unexpected failures. Add a health
endpoint that checks application availability without exposing database details.

Do not allow arbitrary SQL, Riot endpoint proxying, or arbitrary player lookup
from the browser. Start with an allowlisted internal `playerId` and add more
profiles deliberately.

## 4. Relational data model

Use migrations rather than having the Lambda silently create tables at runtime.
The initial schema can be:

- `players`: internal ID, Riot region, encrypted/secret-managed PUUID reference,
  display name, preferred agent, enabled flag, created/updated timestamps.
- `matches`: Riot match ID, player ID, queue/mode, played timestamp, win flag,
  kills, deaths, assists, headshots, shots if available, and raw-source version.
  Add a unique constraint on `(player_id, riot_match_id)` for idempotent imports.
- `import_runs`: start/end time, status, matches discovered/updated, and a
  sanitized error code/message for operational visibility.
- Optional `metric_snapshots`: player ID, recent-window definition, calculated
  values, sample sizes, and calculation timestamp. This makes API reads cheap
  and gives a reproducible cache record.

Define the formulas explicitly in code and documentation:

- KDA: `(kills + assists) / deaths`, with a documented zero-deaths rule.
- Win rate: wins divided by completed matches.
- Headshot percentage: headshots divided by recorded shots or the Riot-provided
  headshot denominator, depending on the endpoint's actual fields.

Do not mix queues, modes, or incomplete matches without making that choice
visible in the response. Store UTC timestamps and calculate the recent window
using UTC.

## 5. Riot API and compliance requirements

Before implementation, confirm the current Riot Developer Portal policies and
Valorant API availability for the intended region and data. The collector should:

- Keep the developer/API key server-side and rotate it through Secrets Manager.
- Identify the application honestly and follow Riot's rate limits, headers, and
  endpoint-specific terms.
- Cache responses and use incremental match imports instead of repeatedly
  downloading the same history.
- Implement retries with exponential backoff for transient responses, but do not
  retry rate-limit or authorization failures aggressively.
- Stop or alert on `401`, `403`, and sustained `429` responses.
- Store only the minimum player/match data needed for this private dashboard and
  support deleting a player's cached data.
- Display a visible, accurate Riot/Valorant attribution and a disclaimer that
  the app is unofficial and not endorsed by Riot Games. Do not use Riot logos or
  assets as though the app were official.
- Use Neon artwork only from an asset source whose usage is permitted for this
  personal project, and keep attribution/license notes with the asset.

The noncommercial intent does not replace compliance with Riot's current terms.
Re-check those terms before deploying and whenever the API or app scope changes.

## 6. Collector behavior

1. Scheduler invokes the collector with a configured player allowlist.
2. Collector reads its secret and opens a database connection using a bounded
   connection strategy. Reuse a connection during one invocation where safe.
3. For each enabled player, resolve the configured Riot identity and fetch only
   new match IDs/details after the newest stored match, subject to rate limits.
4. Normalize API responses into the `matches` table with idempotent upserts.
5. Recalculate the recent and lifetime snapshots in one transaction per player.
6. Write an `import_runs` record, emit structured logs, and return a summary.
7. On partial failure, leave prior snapshots available and mark the import run
   failed or partial. The API should continue serving the last known good cache.

Use a small connection pool or a managed proxy if connection pressure becomes a
problem. Do not add RDS Proxy at the beginning unless testing demonstrates the
need; it adds cost and another AWS concept to learn.

## 7. Frontend plan

Build the React app as a single responsive dashboard with a deliberately playful
presentation that still makes the numbers easy to scan:

- `PlayerHeader`: Neon image, player name, queue/window labels, and last update.
- `StatCard`: one card each for KDA, win rate, and headshot percentage; show
  recent value prominently, lifetime value beside it, delta, and sample size.
- `RecentGames`: optional compact table/list of the latest imported matches for
  context, with no direct Riot calls.
- `api.ts`: typed fetch client with a configured API base URL and explicit error
  state handling.
- `App.tsx`: loading, stale data, empty data, API error, and normal states.

Format percentages consistently, explain the zero-death KDA rule in a small
accessible label or tooltip, and make the layout usable on a phone. Keep the
Riot attribution in the page footer or about area. Do not put the Riot API key,
database credentials, or raw private configuration into the Vite/React bundle.

## 8. Terraform learning sequence

Implement the existing Terraform files in this order, committing each working
milestone separately:

1. `versions.tf`, `providers.tf`, `variables.tf`, and `outputs.tf`: pin versions,
   define environment/region/domain inputs, and expose URLs and identifiers.
2. `iam.tf`: least-privilege execution roles for API, collector, scheduler, and
   deployment. Validate policies with plan review before applying.
3. `database.tf`: VPC/subnets/security groups, RDS PostgreSQL, backups, and
   parameter groups. Keep credentials out of state where possible and understand
   the remaining state-management risk.
4. `secrets.tf`: Secrets Manager resources and explicit Lambda read permissions.
5. `lambdas.tf`: package/deploy both functions, environment variables, logging,
   VPC attachment, and source hashes for repeatable updates.
6. `api.tf`: API Gateway routes, integrations, CORS, stage, throttling, and logs.
7. `scheduler.tf`: EventBridge schedule, invocation permission, and configurable
   interval.
8. `frontend.tf`: S3 bucket, CloudFront distribution, origin access control,
   cache policy, and optional DNS/ACM resources.
9. `monitoring.tf`: log groups, metric filters, alarms, and notification wiring.

Use separate state and variable values per environment, enable state locking,
review `terraform plan`, and keep Terraform state in a protected remote backend.
Add a destroy/cost checklist because RDS, NAT Gateway, CloudFront, and public
IPv4 resources can continue generating charges.

## 9. Testing and acceptance criteria

### Local tests

- Unit test each metric formula, including zero deaths, zero matches, and missing
  denominators.
- Test Riot response normalization and idempotent match upserts with fixtures.
- Test collector handling for success, pagination, `401`, `403`, `429`, timeout,
  and partial-player failure.
- Test API response shape, validation, unknown player, stale cache, and database
  failure behavior.
- Test React loading, empty, stale, error, and populated states with mocked API
  responses.

### Deployment checks

- `terraform fmt -check`, `terraform validate`, and a reviewed `terraform plan`.
- Build the frontend and verify its API base URL is injected at build time.
- Invoke the collector against a non-production/test player or fixture before
  enabling the schedule.
- Verify browser requests go only to the application API and that no secret is
  present in generated frontend assets or logs.
- Confirm CloudFront serves the app over HTTPS and API CORS is restricted to the
  expected origin.
- Confirm a failed collector leaves the last good metrics visible and raises an
  alarm.

## 10. Suggested delivery milestones

1. Define the metric/window contract and obtain a permitted Neon asset.
2. Build the metric calculations and collector against recorded fixtures.
3. Build the API Lambda against a local PostgreSQL database or test container.
4. Build the React dashboard against mocked API data.
5. Implement the database, secrets, Lambda, and scheduler Terraform modules.
6. Deploy the API and collector, run an initial import, then deploy the frontend.
7. Add monitoring, rate-limit handling, deletion support, and cost controls.
8. Re-check Riot policy/attribution requirements before sharing the URL.

## 11. Decisions to make before coding

- Which Riot-supported region/account identity and queue(s) are in scope?
(europe, the list of accounts should be variable in a file, only competitive queue is necessary)
- Is recent performance the last 20 matches or a time-based window?
(last 15 matches)
- Should KDA be `(K+A)/D`, and how should zero deaths be displayed?
(0 deaths should count as 1, kda is just k/d but have the K/D/A there too)
- Is the database single-AZ acceptable for this personal app?
(yes)
- Will a custom domain be used, or will CloudFront/API-generated URLs suffice?
(for now generated one is fine, custom domains costs $$$)
- Which Neon image source and attribution are permitted?
(official valorant free to use and open source)
- How will the Riot API key be supplied initially without committing it to git?
(locally through environment, in the app through secret manager)