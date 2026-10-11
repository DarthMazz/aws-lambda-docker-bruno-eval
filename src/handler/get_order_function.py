"""注文取得 Lambda。

Step Functions から Payload を直接受け取り、DynamoDB から注文を取得して返す。
AWS の接続先は boto3 標準の環境変数 AWS_ENDPOINT_URL で切り替える（ローカルでは moto）。
"""

import logging
import os
from decimal import Decimal
from functools import cache
from typing import Any

import boto3

from common.errors import OrderNotFoundError, ValidationError

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


@cache
def _orders_table():
    return boto3.resource("dynamodb").Table(os.environ["ORDERS_TABLE_NAME"])


def _to_json_compatible(value: Any) -> Any:
    # DynamoDB の数値は Decimal で返るため、Step Functions に渡せる JSON の型に戻す
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, list):
        return [_to_json_compatible(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_json_compatible(v) for k, v in value.items()}
    return value


def lambda_handler(event: Any, context: Any) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise ValidationError("Payload は JSON オブジェクトである必要があります")
    order_id = event.get("orderId")
    if not isinstance(order_id, str) or not order_id.strip():
        raise ValidationError("orderId は必須の文字列です")

    item = _orders_table().get_item(Key={"orderId": order_id}).get("Item")
    if item is None:
        raise OrderNotFoundError(f"orderId={order_id} は存在しません")

    logger.info("order found: orderId=%s", order_id)
    return _to_json_compatible(item)
