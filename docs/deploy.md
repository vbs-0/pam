# Deployment (pam.is-cool.dev)

Domain, VM, firewall and DNS setup are in [`infrastructure.md`](infrastructure.md).

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

### Automatic deployment (CD)

Every push to `main` that passes CI deploys itself: the `deploy` job in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)
runs only after the backend, web and mobile jobs succeed, never for pull requests, and one deploy at a time. It does
what you would do by hand:

1. `bash deploy/deploy.sh vbs`: ship `backend/` and `docs/`, migrate, restart, wait for `/readyz`, roll back on failure.
2. Build the web console (with the public `VITE_FIREBASE_*` identifiers) and unpack `dist` into `/opt/pam/www`.

It logs in over SSH with a dedicated key. Three repository secrets (Settings, Secrets and variables, Actions) hold it:

| Secret | Value |
|---|---|
| `DEPLOY_SSH_KEY` | private half of a key pair made only for this (`ssh-keygen -t ed25519 -C github-actions-pam-deploy`) |
| `DEPLOY_HOST` | the server's public IP |
| `DEPLOY_KNOWN_HOSTS` | one line, `<ip> ssh-ed25519 <host key>`, from `ssh <host> cat /etc/ssh/ssh_host_ed25519_key.pub`; the job refuses any other host |

The public half goes into `~/.ssh/authorized_keys` on the server. To stop automatic deploys, delete that line (or the
`deploy` job); manual `deploy/deploy.sh` keeps working. The APK is not built in CI (it needs the release keystore);
publish it by hand as a GitHub release and copy it to `/opt/pam/www/downloads/pam.apk`.

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

## Web console and Android app

The web build is static files served by nginx.

```bash
cd web && npm ci && npm run build
tar czf - -C dist . | ssh vbs "sudo tar xzf - -C /opt/pam/www --overwrite"
```

nginx falls back to `index.html` for unknown paths, so client routes such as `/reset` work on reload. The release
APK lives in `/opt/pam/www/downloads/pam.apk` (also attached to the GitHub release). Build it with
`cd mobile && flutter build apk --release`; signing reads a git-ignored `android/key.properties` and
`android/pam-release.jks`. Back the keystore up: without it an update cannot install over an existing install.

## Mail

Only password-reset mail is sent. Sign-up does not verify addresses, so nothing is sent on registration.

Oracle blocks outbound port 25 for the whole account (security-list rules do not lift it) and the IP has no reverse
DNS, so the VM cannot deliver mail directly. It sends through an authenticated relay on port 587 (or 2525), which the
VM can reach. Receiving mail is not set up; no inbound rules are needed. The relay can be any SMTP service.

Settings in `/opt/pam/app/backend/.env` (leave them unset to switch mail off; reset requests then do nothing):

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=<mailbox address>
SMTP_PASSWORD=<app password, never the account password>
MAIL_FROM=<same address, or a verified sender>
APP_URL=https://pam.is-cool.dev
```

**Gmail relay.** Turn on 2-Step Verification, create an app password at
<https://myaccount.google.com/apppasswords>, and put the 16 characters (no spaces) in `SMTP_PASSWORD`. Gmail allows
about 500 messages a day and rewrites the sender to the mailbox. Revoke the app password on the same page if it
leaks. A dedicated relay such as SMTP2GO or Brevo works the same way and can send from your own domain once its DNS
records are added.

Restart after editing: `sudo systemctl restart pam-api`. Check delivery without a user account:

```bash
sudo -u pam env -C /opt/pam/app/backend .venv/bin/python -c "from app import mail; print(mail.send('you@example.com', 'PAM mail test', 'hello'))"
```

Reset requests are limited to 3 per address and 10 per client per hour. A failed send is logged
(`journalctl -u pam-api`) and never fails the request (edge case A52).

## Server hygiene

The VM runs only this project: unrelated services found at the start (other sites, Redis and similar) were stopped.
Publicly listening ports: 22 (SSH), 80 and 443 (nginx). The cloud and host firewalls are wider than that, see
[`infrastructure.md`](infrastructure.md#3-security-rules-three-layers). Postgres listens on localhost only; local development reaches it through
`ssh -N -L 15432:127.0.0.1:5432 vbs` (see [`dev-setup.md`](dev-setup.md)).
