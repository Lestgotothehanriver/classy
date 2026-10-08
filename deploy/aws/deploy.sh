#!/usr/bin/env bash

# Deploys the Classy web site and Django API through the SSH host alias.
set -Eeuo pipefail

readonly DEPLOY_HOST="${DEPLOY_HOST:-classy-aws}"
readonly PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly WEB_ROOT="/var/www/classy-web"
readonly API_ROOT="/home/ubuntu/classy-aws"
readonly API_VENV="/home/ubuntu/classy_aws_venv"

usage() {
  cat <<'USAGE'
Usage:
  bash deploy/aws/deploy.sh web
  bash deploy/aws/deploy.sh api
  bash deploy/aws/deploy.sh all
  bash deploy/aws/deploy.sh rollback-web /var/www/classy-web/releases/<release>

Environment:
  DEPLOY_HOST  SSH config host alias (default: classy-aws)
USAGE
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1" >&2
    exit 1
  }
}

run_preflight() {
  require_command ssh
  require_command scp
  require_command tar
  git -C "$PROJECT_ROOT" diff --check
  ssh "$DEPLOY_HOST" "whoami"
}

deploy_web() {
  require_command npm

  (
    cd "$PROJECT_ROOT/web"
    npm ci
    npm run build
  )

  local release="web-$(date +%Y%m%d-%H%M%S)"
  echo "Uploading web release: $release"
  scp -r "$PROJECT_ROOT/web/dist" "$DEPLOY_HOST:/tmp/$release"

  ssh "$DEPLOY_HOST" "bash -s -- '$release' '$WEB_ROOT'" <<'REMOTE'
set -Eeuo pipefail
release="$1"
web_root="$2"

test -f "/tmp/$release/index.html"
previous="$(readlink -f "$web_root/current" || true)"
printf 'Previous web release: %s\n' "$previous"

sudo install -d -m 755 "$web_root/releases/$release"
sudo cp -a "/tmp/$release/." "$web_root/releases/$release/"
test -f "$web_root/releases/$release/index.html"

sudo ln -s "$web_root/releases/$release" "$web_root/.current-$release"
sudo mv -Tf "$web_root/.current-$release" "$web_root/current"
rm -rf "/tmp/$release"

readlink -f "$web_root/current"
curl -fsSI https://classystudy.com
REMOTE
}

deploy_api() {
  echo "Uploading Django source"
  tar -C "$PROJECT_ROOT" -czf - \
    --exclude='.git' \
    --exclude='.env' \
    --exclude='.aws' \
    --exclude='.venv' \
    --exclude='venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.sqlite3' \
    --exclude='media' \
    --exclude='staticfiles' \
    --exclude='web/node_modules' \
    --exclude='web/dist' \
    . | ssh "$DEPLOY_HOST" "tar -xzf - -C '$API_ROOT'"

  ssh "$DEPLOY_HOST" "bash -s -- '$API_ROOT' '$API_VENV'" <<'REMOTE'
set -Eeuo pipefail
api_root="$1"
api_venv="$2"

cd "$api_root"
export DJANGO_SETTINGS_MODULE=config.settings.aws

"$api_venv/bin/pip" install -r requirements.txt
"$api_venv/bin/python" manage.py check --deploy --fail-level WARNING
"$api_venv/bin/python" manage.py migrate --noinput
"$api_venv/bin/python" manage.py seed_reference_data
"$api_venv/bin/python" manage.py collectstatic --noinput

sudo systemctl restart classy
systemctl is-active classy nginx redis-server

# Nginx can return 502 briefly while the freshly restarted ASGI workers start.
for attempt in $(seq 1 30); do
  if curl -fsS --max-time 10 https://api.classystudy.com/healthz/ >/dev/null 2>&1; then
    curl -fsS --max-time 10 https://api.classystudy.com/healthz/
    exit 0
  fi

  if [ "$attempt" -eq 30 ]; then
    echo "API health check did not succeed within 60 seconds." >&2
    exit 1
  fi

  sleep 2
done
REMOTE
}

rollback_web() {
  local previous_release="${1:?A release path is required}"

  ssh "$DEPLOY_HOST" "bash -s -- '$previous_release' '$WEB_ROOT'" <<'REMOTE'
set -Eeuo pipefail
previous_release="$1"
web_root="$2"

test -f "$previous_release/index.html"
sudo ln -s "$previous_release" "$web_root/.current-rollback"
sudo mv -Tf "$web_root/.current-rollback" "$web_root/current"
readlink -f "$web_root/current"
REMOTE
}

case "${1:-}" in
  web)
    run_preflight
    deploy_web
    ;;
  api)
    run_preflight
    deploy_api
    ;;
  all)
    run_preflight
    deploy_web
    deploy_api
    ;;
  rollback-web)
    run_preflight
    rollback_web "${2:-}"
    ;;
  *)
    usage
    exit 1
    ;;
esac
