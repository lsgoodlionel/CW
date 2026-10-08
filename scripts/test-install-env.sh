#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

cd "$TMP_DIR"

info() { :; }
warn() { :; }
err() { echo "$*" >&2; }

awk '
  /^set_env\(\) \{/ {capture=1}
  /^run_deploy\(\) \{/ {exit}
  capture {print}
' "$ROOT_DIR/install.sh" > install-env-functions.sh

# shellcheck disable=SC1091
source ./install-env-functions.sh

assert_env() {
  local key="$1" expected="$2" actual
  actual="$(grep -E "^${key}=" .env | cut -d= -f2- || true)"
  if [ "$actual" != "$expected" ]; then
    echo "Expected ${key}=${expected}, got ${actual}" >&2
    exit 1
  fi
}

cat > .env <<'ENV'
HTTP_PORT=127.0.0.1:18080
POSTGRES_USER=finance
POSTGRES_PASSWORD=existing-db-password
POSTGRES_DB=finance_db
DEPLOY_MODE=saas
ALLOW_SELF_REGISTRATION=false
ADMIN_PASSWORD=existing-admin
PIP_INDEX_URL=https://mirror.example/simple
ENV

HTTP_PORT=8080 \
POSTGRES_USER=wrong-user \
POSTGRES_PASSWORD=wrong-password \
POSTGRES_DB=wrong-db \
DEPLOY_MODE=private \
ALLOW_SELF_REGISTRATION=true \
ADMIN_PASSWORD=new-admin \
PIP_INDEX_URL=https://new-mirror.example/simple \
apply_env_overrides

assert_env HTTP_PORT "127.0.0.1:18080"
assert_env POSTGRES_USER "finance"
assert_env POSTGRES_PASSWORD "existing-db-password"
assert_env POSTGRES_DB "finance_db"
assert_env DEPLOY_MODE "saas"
assert_env ALLOW_SELF_REGISTRATION "false"
assert_env ADMIN_PASSWORD "existing-admin"
assert_env PIP_INDEX_URL "https://mirror.example/simple"

rm .env
cat > .env.example <<'ENV'
HTTP_PORT=8080
POSTGRES_USER=finance
POSTGRES_PASSWORD=change-me
POSTGRES_DB=finance
DEPLOY_MODE=private
ALLOW_SELF_REGISTRATION=false
ADMIN_PASSWORD=admin123
PIP_INDEX_URL=
ENV

HTTP_PORT=127.0.0.1:18080 DEPLOY_MODE=saas ALLOW_SELF_REGISTRATION=true ADMIN_PASSWORD= PIP_INDEX_URL=https://mirror.example/simple apply_env_overrides

assert_env HTTP_PORT "127.0.0.1:18080"
assert_env POSTGRES_USER "finance"
assert_env POSTGRES_DB "finance"
assert_env DEPLOY_MODE "saas"
assert_env ALLOW_SELF_REGISTRATION "true"
assert_env ADMIN_PASSWORD ""
assert_env PIP_INDEX_URL "https://mirror.example/simple"

generated_password="$(grep -E '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)"
if [ "$generated_password" = "change-me" ] || [ -z "$generated_password" ]; then
  echo "Expected fresh install to generate a database password" >&2
  exit 1
fi

echo "install.sh env override tests passed"
