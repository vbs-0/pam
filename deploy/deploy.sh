#!/usr/bin/env bash
# Ship the committed backend to the server and restart it. Usage: deploy/deploy.sh [ssh-host]   (default: vbs)
# First-time setup (user, uv, .env, systemd unit, nginx site, certificate) is described in docs/deploy.md.
set -euo pipefail
HOST=${1:-vbs}
cd "$(git rev-parse --show-toplevel)"
git archive --format=tar HEAD backend docs | ssh "$HOST" 'sudo bash -c "set -e
  rm -rf /opt/pam/app/new && mkdir -p /opt/pam/app/new && tar -x -C /opt/pam/app/new
  cp -p /opt/pam/app/backend/.env /opt/pam/app/new/backend/.env
  rm -rf /opt/pam/app/backend.old && mv /opt/pam/app/backend /opt/pam/app/backend.old
  mv /opt/pam/app/new/backend /opt/pam/app/backend && rm -rf /opt/pam/app/docs && mv /opt/pam/app/new/docs /opt/pam/app/
  rmdir /opt/pam/app/new && chown -R pam:pam /opt/pam/app"
  sudo -u pam bash -c "cd /opt/pam/app/backend && export HOME=/opt/pam UV_PYTHON_INSTALL_DIR=/opt/pam/.python
    uv sync --frozen --no-dev --python 3.12 -q && uv run --no-sync alembic upgrade head"
  sudo systemctl restart pam-api
  for i in $(seq 1 20); do curl -fs 127.0.0.1:8100/readyz && echo && exit 0; sleep 1; done
  echo "API did not become ready; rolling back"; sudo bash -c "rm -rf /opt/pam/app/backend && mv /opt/pam/app/backend.old /opt/pam/app/backend"
  sudo systemctl restart pam-api; exit 1'
