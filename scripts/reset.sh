#!/usr/bin/env bash
# moto の状態をリセットし、テーブル・バケット・初期データを作り直す。
set -euo pipefail
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"

require_docker

log "moto をリセットします"
curl -fsS -X POST "${MOTO_URL}/moto-api/reset" >/dev/null

log "初期データを投入します"
docker compose run --rm --no-deps moto-init
