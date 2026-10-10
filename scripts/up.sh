#!/usr/bin/env bash
# 環境を起動し、Lambda が呼び出せる状態になるまで待つ。
set -euo pipefail
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"

require_docker

log "コンテナをビルド・起動します"
docker compose up -d --build

log "初期データ投入（moto-init）の完了を待機中"
# docker compose wait はコンテナの終了コードをそのまま返す（timeout 時は 124）
if ! timeout "$WAIT_TIMEOUT_SEC" docker compose wait moto-init >/dev/null; then
  err "moto-init が失敗またはタイムアウトしました"
  docker compose logs moto-init >&2 || true
  exit 1
fi
log "初期データ投入: OK"

wait_until "Lambda (register-order) の起動" lambda_ready
log "起動完了: Lambda=${REGISTER_ORDER_URL} moto=${MOTO_URL}"
