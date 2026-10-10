#!/usr/bin/env bash
# moto にテスト用のリソースと初期データを作成する。
# amazon/aws-cli コンテナから実行する想定（AWS_ENDPOINT_URL で moto を指す）。
# 既に存在するリソースは作り直さないので、何度実行しても同じ状態になる。
set -euo pipefail

: "${AWS_ENDPOINT_URL:?AWS_ENDPOINT_URL が未設定です}"
: "${ORDERS_TABLE_NAME:?ORDERS_TABLE_NAME が未設定です}"
: "${ORDERS_BUCKET_NAME:?ORDERS_BUCKET_NAME が未設定です}"
: "${AWS_DEFAULT_REGION:?AWS_DEFAULT_REGION が未設定です}"

SEED_DIR="$(cd "$(dirname "$0")" && pwd)/seed"

log() { echo "[moto-init] $*"; }

# --- DynamoDB ---------------------------------------------------------------
if aws dynamodb describe-table --table-name "$ORDERS_TABLE_NAME" >/dev/null 2>&1; then
  log "DynamoDB テーブル ${ORDERS_TABLE_NAME} は作成済み"
else
  log "DynamoDB テーブル ${ORDERS_TABLE_NAME} を作成"
  aws dynamodb create-table \
    --table-name "$ORDERS_TABLE_NAME" \
    --attribute-definitions AttributeName=orderId,AttributeType=S \
    --key-schema AttributeName=orderId,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST >/dev/null
  aws dynamodb wait table-exists --table-name "$ORDERS_TABLE_NAME"
fi

# --- S3 ---------------------------------------------------------------------
if aws s3api head-bucket --bucket "$ORDERS_BUCKET_NAME" >/dev/null 2>&1; then
  log "S3 バケット ${ORDERS_BUCKET_NAME} は作成済み"
else
  log "S3 バケット ${ORDERS_BUCKET_NAME} を作成"
  aws s3api create-bucket \
    --bucket "$ORDERS_BUCKET_NAME" \
    --create-bucket-configuration "LocationConstraint=${AWS_DEFAULT_REGION}" >/dev/null
fi

# --- 初期データ ---------------------------------------------------------------
# 登録済み注文（重複登録エラーのテストに使う）。DynamoDB と S3 の両方に置く。
for item in "$SEED_DIR"/orders/*.dynamodb.json; do
  [ -e "$item" ] || continue
  order_id="$(basename "$item" .dynamodb.json)"
  log "初期データ投入: ${order_id}"
  aws dynamodb put-item --table-name "$ORDERS_TABLE_NAME" --item "file://${item}"
  aws s3api put-object \
    --bucket "$ORDERS_BUCKET_NAME" \
    --key "orders/${order_id}.json" \
    --body "$SEED_DIR/orders/${order_id}.json" \
    --content-type application/json >/dev/null
done

log "完了"
