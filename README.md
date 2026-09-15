# valorant-stats

A small React and AWS application that displays a friend's Valorant KDA, win rate,
and headshot percentage, comparing recent performance with lifetime averages.
The app reads cached statistics from its backend; a scheduled collector retrieves
fresh data from the Riot API and stores it in a relational database.

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
