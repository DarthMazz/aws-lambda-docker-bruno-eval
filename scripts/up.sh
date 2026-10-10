#!/usr/bin/env bash
# 環境を起動し、Lambda が呼び出せる状態になるまで待つ。
set -euo pipefail
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"

require_docker

log "コンテナをビルド・起動します（初期データ投入の完了まで待機、最大 ${WAIT_TIMEOUT_SEC} 秒）"
# register-order は moto-init の正常終了を待って起動するため、--wait で初期データ投入の完了まで待てる。
# macOS には GNU の timeout がないので、タイムアウトは compose の --wait-timeout に任せる
if ! docker compose up -d --build --wait --wait-timeout "$WAIT_TIMEOUT_SEC"; then
  err "起動に失敗またはタイムアウトしました"
  docker compose ps -a >&2 || true
  docker compose logs moto-init >&2 || true
  exit 1
fi
log "初期データ投入: OK"

wait_until "Lambda (register-order) の起動" lambda_ready
log "起動完了: Lambda=${REGISTER_ORDER_URL} moto=${MOTO_URL}"
