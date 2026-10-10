import json

import boto3
import pytest
from moto import mock_aws

from app import handler
from app.errors import OrderAlreadyExistsError, ValidationError

TABLE_NAME = "Orders"
BUCKET_NAME = "orders-bucket"
REGION = "ap-northeast-1"


@pytest.fixture(autouse=True)
def aws(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)
    monkeypatch.setenv("ORDERS_TABLE_NAME", TABLE_NAME)
    monkeypatch.setenv("ORDERS_BUCKET_NAME", BUCKET_NAME)

    # クライアントはキャッシュされるため、モック開始後に作り直させる
    handler._orders_table.cache_clear()
    handler._s3_client.cache_clear()

    with mock_aws():
        boto3.client("dynamodb").create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "orderId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "orderId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        boto3.client("s3").create_bucket(
            Bucket=BUCKET_NAME,
            CreateBucketConfiguration={"LocationConstraint": REGION},
        )
        yield


def valid_payload(**overrides):
    payload = {
        "orderId": "ORD-0001",
        "customerId": "CUST-001",
        "items": [
            {"sku": "SKU-001", "quantity": 2, "price": 1200},
            {"sku": "SKU-002", "quantity": 1, "price": 500},
        ],
    }
    payload.update(overrides)
    return payload


def test_register_order_returns_result():
    result = handler.lambda_handler(valid_payload(), None)

    assert result == {
        "orderId": "ORD-0001",
        "status": "REGISTERED",
        "totalAmount": 2900,
        "s3Key": "orders/ORD-0001.json",
    }


def test_register_order_writes_dynamodb_and_s3():
    handler.lambda_handler(valid_payload(), None)

    item = boto3.resource("dynamodb").Table(TABLE_NAME).get_item(Key={"orderId": "ORD-0001"})["Item"]
    assert item["customerId"] == "CUST-001"
    assert item["totalAmount"] == 2900
    assert item["status"] == "REGISTERED"
    assert len(item["items"]) == 2

    body = boto3.client("s3").get_object(Bucket=BUCKET_NAME, Key="orders/ORD-0001.json")["Body"].read()
    saved = json.loads(body)
    assert saved["orderId"] == "ORD-0001"
    assert saved["totalAmount"] == 2900
    assert saved["items"][0] == {"sku": "SKU-001", "quantity": 2, "price": 1200}


def test_duplicate_order_raises_and_keeps_original():
    handler.lambda_handler(valid_payload(), None)

    with pytest.raises(OrderAlreadyExistsError):
        handler.lambda_handler(valid_payload(customerId="CUST-999"), None)

    item = boto3.resource("dynamodb").Table(TABLE_NAME).get_item(Key={"orderId": "ORD-0001"})["Item"]
    assert item["customerId"] == "CUST-001"
    body = boto3.client("s3").get_object(Bucket=BUCKET_NAME, Key="orders/ORD-0001.json")["Body"].read()
    assert json.loads(body)["customerId"] == "CUST-001"


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("not-an-object", id="payload-not-object"),
        pytest.param(valid_payload(orderId=None), id="orderId-missing"),
        pytest.param(valid_payload(orderId="  "), id="orderId-blank"),
        pytest.param(valid_payload(customerId=123), id="customerId-not-str"),
        pytest.param(valid_payload(items=[]), id="items-empty"),
        pytest.param(valid_payload(items="SKU-001"), id="items-not-list"),
        pytest.param(valid_payload(items=["SKU-001"]), id="item-not-object"),
        pytest.param(valid_payload(items=[{"quantity": 1, "price": 100}]), id="sku-missing"),
        pytest.param(valid_payload(items=[{"sku": "A", "quantity": 0, "price": 100}]), id="quantity-zero"),
        pytest.param(valid_payload(items=[{"sku": "A", "quantity": 1.5, "price": 100}]), id="quantity-float"),
        pytest.param(valid_payload(items=[{"sku": "A", "quantity": True, "price": 100}]), id="quantity-bool"),
        pytest.param(valid_payload(items=[{"sku": "A", "quantity": 1, "price": -1}]), id="price-negative"),
    ],
)
def test_invalid_payload_raises_validation_error(payload):
    with pytest.raises(ValidationError):
        handler.lambda_handler(payload, None)

    assert boto3.client("dynamodb").scan(TableName=TABLE_NAME)["Count"] == 0


def test_free_item_is_allowed():
    result = handler.lambda_handler(valid_payload(items=[{"sku": "FREE", "quantity": 3, "price": 0}]), None)

    assert result["totalAmount"] == 0
