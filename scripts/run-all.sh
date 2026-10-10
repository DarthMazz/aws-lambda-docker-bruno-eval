#!/usr/bin/env bash
# 起動 → リセット・初期データ投入 → テスト → 後片付け を一括で行う。
# 終了コードはテスト結果。テストが失敗しても後片付けは必ず行う。
#   KEEP_UP=1 ./scripts/run-all.sh   # 終了後もコンテナを残す（調査用）
set -euo pipefail
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"

cleanup() {
  if [[ "${KEEP_UP:-0}" == "1" ]]; then
    echo "KEEP_UP=1 のためコンテナを残します（停止: ./scripts/down.sh）"
  else
    "$SCRIPTS_DIR/down.sh"
  fi
}
trap cleanup EXIT

"$SCRIPTS_DIR/up.sh"
"$SCRIPTS_DIR/test.sh" "$@"
