#!/usr/bin/env bash
# Bruno CLI でテストを実行する。既定では実行前に reset.sh で moto を初期化する。
#   SKIP_RESET=1 ./scripts/test.sh                  # リセットせずに実行
#   ./scripts/test.sh register-order                # フォルダを指定して実行
#   ./scripts/test.sh register-order/01_正常系_注文登録.bru
# 追加の引数はそのまま bru run に渡す。
set -euo pipefail
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"

require_cmd node npx curl

if [[ "${SKIP_RESET:-0}" != "1" ]]; then
  "$ROOT_DIR/scripts/reset.sh"
fi

REPORT_DIR="$ROOT_DIR/bruno/reports"
mkdir -p "$REPORT_DIR"

paths=("$@")
if ((${#paths[@]} == 0)); then
  paths=(.)
fi

log "Bruno CLI ${BRUNO_CLI_VERSION} でテストを実行します"
cd "$ROOT_DIR/bruno"
set +e
npx --yes "@usebruno/cli@${BRUNO_CLI_VERSION}" run "${paths[@]}" -r \
  --env local \
  --env-var "registerOrderUrl=${REGISTER_ORDER_URL}" \
  --env-var "getOrderUrl=${GET_ORDER_URL}" \
  --env-var "motoUrl=${MOTO_URL}" \
  --reporter-junit "$REPORT_DIR/junit.xml" \
  --reporter-html "$REPORT_DIR/report.html"
status=$?
set -e

if ((status == 0)); then
  log "テスト成功"
else
  err "テスト失敗（終了コード ${status}）"
fi
log "レポート: bruno/reports/report.html, bruno/reports/junit.xml"
exit "$status"
