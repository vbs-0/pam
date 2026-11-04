# Development database

The database lives on the server (`vbs`, Postgres 14, listening on localhost only). Local work reaches it
through an SSH tunnel; nothing is exposed publicly.

```bash
ssh -N -L 15432:127.0.0.1:5432 vbs
```

`backend/.env` (git-ignored) points `DATABASE_URL` / `TEST_DATABASE_URL` at `127.0.0.1:15432` with the `pam`
role. Role `pam` owns databases `pam` and `pam_test` only; `CONNECT` is revoked from `PUBLIC` on both.

```bash
cd backend && uv run alembic upgrade head && uv run pytest
```

The test fixture resets `pam_test` by dropping only tables the `pam` role owns (on Postgres <= 14 the `public`
schema belongs to `postgres`).
