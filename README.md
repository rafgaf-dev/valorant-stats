# valorant-stats

A small React and AWS application that displays a friend's Valorant K/D, win rate,
and headshot percentage, comparing their last 15 competitive matches with all
matches since tracking began. A scheduled collector retrieves data from the Riot
API, stores matches in DynamoDB, and publishes a precomputed JSON summary that
the frontend reads through CloudFront.

The implementation and infrastructure plan lives in [_docs/implementation-plan.md](_docs/implementation-plan.md).

## Repository layout

| Path | Contents |
| --- | --- |
| `collector/` | Python collector Lambda (source in `src/collector/`, tests in `tests/`) |
| `frontend/` | React + Vite dashboard; `dev-data/` holds sample summaries for local development |
| `infrastructure/` | Terraform for AWS |
| `config/` | `players.example.json`; copy it to the gitignored `players.json` with real Riot IDs |

## Local development

Requirements (Linux, macOS, or WSL on Windows): GNU Make, Node.js 22.12+ with
Corepack, Python 3.13+ with `venv`, and Terraform 1.16+.

```bash
make dev
```

Open http://127.0.0.1:5173. Vite serves the React app and, in development only,
the sample summary in `frontend/dev-data/` under `/data`, the same path the
production app reads from CloudFront.

Before pushing, run the same checks as CI:

```bash
make check
```

Run `make help` for the individual targets (`lint`, `format`, `test`,
`typecheck`, `build`, `validate-infra`).

## License

[MIT](LICENSE). This is an unofficial fan project and is not endorsed by Riot
Games. VALORANT and all related imagery are property of Riot Games, Inc.
