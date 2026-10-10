#!/usr/bin/env bash
# 各スクリプト共通の設定と関数。source して使う。
# 変数は source 元のスクリプトで使うため SC2034 を無効化する。
# shellcheck disable=SC2034

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR" || exit 1

# .env があれば読み込む（compose.yaml と同じ値を使うため）
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

MOTO_PORT="${MOTO_PORT:-5000}"
REGISTER_ORDER_PORT="${REGISTER_ORDER_PORT:-9000}"
MOTO_URL="http://localhost:${MOTO_PORT}"
REGISTER_ORDER_URL="http://localhost:${REGISTER_ORDER_PORT}/2015-03-31/functions/function/invocations"

BRUNO_CLI_VERSION="${BRUNO_CLI_VERSION:-4.2.0}"
WAIT_TIMEOUT_SEC="${WAIT_TIMEOUT_SEC:-120}"

log() { echo "[$(date +%H:%M:%S)] $*"; }
err() { echo "[$(date +%H:%M:%S)] ERROR: $*" >&2; }

require_cmd() {
  local cmd
  for cmd in "$@"; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      err "'${cmd}' が見つかりません。README の「前提ツール」を確認してください"
      exit 1
    fi
  done
}

require_docker() {
  require_cmd docker curl
  if ! docker compose version >/dev/null 2>&1; then
    err "Docker Compose v2（docker compose）が使えません"
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    err "Docker デーモンに接続できません。Docker が起動しているか確認してください"
    exit 1
  fi
}

# 条件コマンドが成功するまで待つ。タイムアウト時はコンテナログを表示して失敗する
# 使い方: wait_until <説明> <コマンド...>
wait_until() {
  local desc="$1"
  shift
  local deadline=$((SECONDS + WAIT_TIMEOUT_SEC))
  log "${desc} を待機中（最大 ${WAIT_TIMEOUT_SEC} 秒）"
  until "$@" >/dev/null 2>&1; do
    if ((SECONDS >= deadline)); then
      err "${desc} がタイムアウトしました。コンテナの状態とログ:"
      docker compose ps -a >&2 || true
      # moto はヘルスチェックのアクセスログが多いので、サービスごとに末尾だけ表示する
      local service
      for service in $(docker compose config --services); do
        docker compose logs --tail 20 "$service" >&2 || true
      done
      return 1
    fi
    sleep 1
  done
  log "${desc}: OK"
}

# Lambda（RIE）が応答するか。空の Payload は ValidationError になるだけで副作用がない
lambda_ready() {
  curl -fsS -X POST "$REGISTER_ORDER_URL" -d '{}' | grep -q '"errorType"'
}
