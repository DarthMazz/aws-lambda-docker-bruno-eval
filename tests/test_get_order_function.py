import pytest

from common.errors import OrderNotFoundError, ValidationError
from handler import get_order_function as handler
from handler import register_order_function


def register(order_id="ORD-0001"):
    register_order_function.lambda_handler(
        {
            "orderId": order_id,
            "customerId": "CUST-001",
            "items": [{"sku": "SKU-001", "quantity": 2, "price": 1200}],
        },
        None,
    )


def test_get_order_returns_registered_order():
    register()

    result = handler.lambda_handler({"orderId": "ORD-0001"}, None)

    assert result["orderId"] == "ORD-0001"
    assert result["customerId"] == "CUST-001"
    assert result["status"] == "REGISTERED"
    assert result["s3Key"] == "orders/ORD-0001.json"
    # Decimal ではなく int で返ること（Step Functions に JSON として渡すため）
    assert result["totalAmount"] == 2400 and type(result["totalAmount"]) is int
    assert result["items"] == [{"sku": "SKU-001", "quantity": 2, "price": 1200}]
    assert type(result["items"][0]["quantity"]) is int


def test_get_order_not_found():
    with pytest.raises(OrderNotFoundError):
        handler.lambda_handler({"orderId": "ORD-404"}, None)


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("not-an-object", id="payload-not-object"),
        pytest.param({}, id="orderId-missing"),
        pytest.param({"orderId": "  "}, id="orderId-blank"),
        pytest.param({"orderId": 1}, id="orderId-not-str"),
    ],
)
def test_invalid_payload_raises_validation_error(payload):
    with pytest.raises(ValidationError):
        handler.lambda_handler(payload, None)
