import boto3
import pytest
from moto import mock_aws

from handler import get_order_function, register_order_function

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
    register_order_function._orders_table.cache_clear()
    register_order_function._s3_client.cache_clear()
    get_order_function._orders_table.cache_clear()

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
