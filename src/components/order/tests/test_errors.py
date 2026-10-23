from uuid import UUID
from src.components.common.errors import NotFoundError
from src.components.order.errors import InvalidUpgradeError, OrderNotFoundError


def test_order_not_found_error_message():
    err = OrderNotFoundError(entity_id= UUID("12312312-3123-1231-2312-312312312312"))

    assert isinstance(err, NotFoundError)
    assert str(err) == "Order not found, id: 12312312-3123-1231-2312-312312312312"


def test_invalid_upgrade_error_instantiation():
    err = InvalidUpgradeError("Invalid upgrade rule")

    assert isinstance(err, Exception)
    assert str(err) == "Invalid upgrade rule"
