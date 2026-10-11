"""注文登録 Lambda。

Step Functions から Payload を直接受け取り、DynamoDB に注文を登録して S3 に注文内容の JSON を保存する。
AWS の接続先は boto3 標準の環境変数 AWS_ENDPOINT_URL で切り替える（ローカルでは moto）。
"""

import json
import logging
import os
from datetime import UTC, datetime
from functools import cache
from typing import Any

import boto3
from botocore.exceptions import ClientError

from common.errors import OrderAlreadyExistsError, ValidationError

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

STATUS_REGISTERED = "REGISTERED"


@cache
def _orders_table():
    return boto3.resource("dynamodb").Table(os.environ["ORDERS_TABLE_NAME"])


@cache
def _s3_client():
    return boto3.client("s3")


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{key} は必須の文字列です")
    return value


def _require_int(item: dict[str, Any], key: str, index: int, minimum: int) -> int:
    value = item.get(key)
    # bool は int のサブクラスなので明示的に除外する
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValidationError(f"items[{index}].{key} は {minimum} 以上の整数です")
    return value


def _validate(event: Any) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise ValidationError("Payload は JSON オブジェクトである必要があります")

    order_id = _require_str(event, "orderId")
    customer_id = _require_str(event, "customerId")

    items = event.get("items")
    if not isinstance(items, list) or not items:
        raise ValidationError("items は 1 件以上の配列です")

    normalized_items = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValidationError(f"items[{index}] はオブジェクトです")
        sku = item.get("sku")
        if not isinstance(sku, str) or not sku.strip():
            raise ValidationError(f"items[{index}].sku は必須の文字列です")
        normalized_items.append(
            {
                "sku": sku,
                "quantity": _require_int(item, "quantity", index, minimum=1),
                "price": _require_int(item, "price", index, minimum=0),
            }
        )

    return {"orderId": order_id, "customerId": customer_id, "items": normalized_items}


def lambda_handler(event: Any, context: Any) -> dict[str, Any]:
    order = _validate(event)
    order_id = order["orderId"]
    total_amount = sum(i["quantity"] * i["price"] for i in order["items"])
    s3_key = f"orders/{order_id}.json"

    record = {
        **order,
        "totalAmount": total_amount,
        "status": STATUS_REGISTERED,
        "s3Key": s3_key,
        "createdAt": datetime.now(UTC).isoformat(),
    }

    # 重複チェックを兼ねて DynamoDB を先に書く（既存注文の S3 オブジェクトを上書きしないため）
    try:
        _orders_table().put_item(
            Item=record,
            ConditionExpression="attribute_not_exists(orderId)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise OrderAlreadyExistsError(f"orderId={order_id} は既に登録されています") from e
        raise

    _s3_client().put_object(
        Bucket=os.environ["ORDERS_BUCKET_NAME"],
        Key=s3_key,
        Body=json.dumps(record, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )

    logger.info("order registered: orderId=%s totalAmount=%d", order_id, total_amount)

    return {
        "orderId": order_id,
        "status": STATUS_REGISTERED,
        "totalAmount": total_amount,
        "s3Key": s3_key,
    }
