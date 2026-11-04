# Deployment (pam.is-cool.dev)

One small Linux VM (Oracle Cloud, Ubuntu 22.04, 2 vCPU, 1 GB RAM). No containers: the 1 GB box is better spent on
Postgres and one API process.

| Piece | Where |
|---|---|
| API | `pam-api.service` (systemd, user `pam`): uvicorn on `127.0.0.1:8100`, 1 worker, `MemoryMax=600M`, read-only filesystem except `data/`, `reports/`, `/tmp` |
| Code | `/opt/pam/app/backend` (Python 3.12 venv made by uv), config in `/opt/pam/app/backend/.env` (mode 600) |
| Database | Postgres 14 on the same VM, localhost only; role `pam`, databases `pam` and `pam_test` |
| Web | nginx `pam` site: `/api/`, `/docs`, `/openapi.json`, `/healthz`, `/readyz` go to the API, everything else is the web console in `/opt/pam/www` |
| TLS | Let's Encrypt via certbot (`--nginx --redirect`), auto-renewed by the certbot timer |
| DNS | `pam.is-cool.dev` A record → 129.159.20.37 (Open Domains, not proxied) |

Files in this repo: [`deploy/pam-api.service`](../deploy/pam-api.service), [`deploy/nginx-pam.conf`](../deploy/nginx-pam.conf),
[`deploy/deploy.sh`](../deploy/deploy.sh).

## Updating

```bash
deploy/deploy.sh vbs
```

Ships the committed `backend/` and `docs/`, keeps the server `.env`, syncs dependencies, runs migrations, restarts
and waits for `/readyz`; if the API does not come up it puts the previous version back.

## First-time setup (what was done once)

1. `useradd --system --home-dir /opt/pam pam`; install uv to `/usr/local/bin`.
2. Copy the code as in `deploy.sh`, then `uv sync --frozen --no-dev --python 3.12` as `pam`.
3. Write `/opt/pam/app/backend/.env` from `backend/.env.example` with `ENV=prod`, a random 64-character
   `JWT_SECRET`, a random `DEMO_PASSWORD` (staff logins; the API refuses to start in prod if it is short or equals
   `HOUSEHOLD_PASSWORD`), `CORS_ORIGINS=https://pam.is-cool.dev`, `DATA_DIR=/opt/pam/app/data`.
4. `alembic upgrade head`, then `python -m app.cli generate --scale starter --out /opt/pam/app/data/starter`,
   `load`, `seed-users`, `pipeline`, `evaluate --db`.
5. Install the unit and the nginx site, `certbot --nginx -d pam.is-cool.dev --redirect`.

Staff password: `ssh vbs sudo grep DEMO_PASSWORD /opt/pam/app/backend/.env`.

## Sizing

The starter dataset (50 households, 25k transactions) runs comfortably: API ~120 MB, a full pipeline run ~10 s.
Full scale (1,000 households, 500k transactions) is generated, validated and evaluated offline with the CLI; the
admin console refuses jobs above `MAX_JOB_TRANSACTIONS` (100k) on this box (edge case A45).

## Mail

Oracle blocks outbound port 25 for the whole account (security-list rules do not lift it), and the IP has no
reverse DNS, so the VM cannot deliver mail directly. Password-reset and invite mail will go through OCI Email
Delivery on port 587 (reachable from the VM) as `no-reply@pam.is-cool.dev`.
