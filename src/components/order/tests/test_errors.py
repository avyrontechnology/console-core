from src.components.common.errors import NotFoundError
from src.components.order.errors import InvalidUpgradeError, OrderNotFoundError


def test_order_not_found_error_message():
    err = OrderNotFoundError(entity_id=123)

    assert isinstance(err, NotFoundError)
    assert str(err) == "Order not found, id: 123"


def test_invalid_upgrade_error_instantiation():
    err = InvalidUpgradeError("Invalid upgrade rule")

    assert isinstance(err, Exception)
    assert str(err) == "Invalid upgrade rule"
