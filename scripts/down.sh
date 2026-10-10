#!/usr/bin/env bash
# コンテナ・ネットワーク・ボリュームを削除する。
set -euo pipefail
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"

require_docker

log "環境を停止・削除します"
docker compose down -v --remove-orphans
