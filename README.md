# valorant-stats

A small React and AWS application that displays a friend's Valorant K/D, win rate,
and headshot percentage, comparing their last 15 competitive matches with all
matches since tracking began. A scheduled collector retrieves data from the Riot
API, stores matches in DynamoDB, and publishes a precomputed JSON summary that
the frontend reads through CloudFront.

The implementation and infrastructure plan lives in [_docs/implementation-plan.md](_docs/implementation-plan.md).

## Local development

Install GNU Make in WSL if needed, then run:

```bash
make dev
```

Open http://127.0.0.1:5173. This starts a local development API with sample
metrics on port 8000 and the React frontend on port 5173. The local API is only
for viewing and developing the interface; production data comes from the Riot
collector and PostgreSQL backend.

Useful targets are `make api`, `make frontend`, `make build`, and `make check`.

Vite is the frontend development tool used by this project. It starts the local
development server, serves the React source with fast updates while you edit,
and bundles the optimized static files for production with `make build`.
