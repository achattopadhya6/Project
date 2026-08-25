"""Deterministic unit tests for models.py (Task 2.6).

Covers enum values, Order/Trade construction, the result/response value types,
and every branch of validate_submission. Deterministic assertions only — no
property-based testing.
"""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from models import (
    BookLevel,
    CancellationResult,
    Fill,
    NormalizedSubmission,
    Order,
    OrderType,
    Side,
    SubmissionResult,
    TopOfBook,
    Trade,
    ValidationError,
    validate_submission,
)


# --- Enums ------------------------------------------------------------------


def test_side_enum_values():
    assert Side.BUY.value == "Buy"
    assert Side.SELL.value == "Sell"


def test_order_type_enum_values():
    assert OrderType.LIMIT.value == "Limit"
    assert OrderType.MARKET.value == "Market"


# --- Order ------------------------------------------------------------------


def test_order_construction_limit():
    order = Order(
        order_id=1,
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        remaining_quantity=10,
        price=Decimal("100.50"),
    )
    assert order.order_id == 1
    assert order.side is Side.BUY
    assert order.order_type is OrderType.LIMIT
    assert order.quantity == 10
    assert order.remaining_quantity == 10
    assert order.price == Decimal("100.50")


def test_order_construction_market_price_none():
    order = Order(
        order_id=2,
        side=Side.SELL,
        order_type=OrderType.MARKET,
        quantity=5,
        remaining_quantity=5,
    )
    assert order.price is None


def test_order_is_mutable_remaining_quantity():
    order = Order(
        order_id=3,
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        remaining_quantity=10,
        price=Decimal("1"),
    )
    order.remaining_quantity = 4
    assert order.remaining_quantity == 4


# --- Trade ------------------------------------------------------------------


def test_trade_construction():
    ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    trade = Trade(
        trade_id=1,
        price=Decimal("100.50"),
        quantity=5,
        aggressor_order_id=2,
        resting_order_id=1,
        aggressor_side=Side.BUY,
        timestamp=ts,
    )
    assert trade.trade_id == 1
    assert trade.price == Decimal("100.50")
    assert trade.quantity == 5
    assert trade.aggressor_order_id == 2
    assert trade.resting_order_id == 1
    assert trade.aggressor_side is Side.BUY
    assert trade.timestamp == ts


def test_trade_is_frozen():
    trade = Trade(
        trade_id=1,
        price=Decimal("100"),
        quantity=5,
        aggressor_order_id=2,
        resting_order_id=1,
        aggressor_side=Side.BUY,
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    with pytest.raises(FrozenInstanceError):
        trade.quantity = 99


# --- Result / response value types ------------------------------------------


def test_fill_construction():
    fill = Fill(trade_id=1, price=Decimal("100"), quantity=5, resting_order_id=3)
    assert fill.trade_id == 1
    assert fill.price == Decimal("100")
    assert fill.quantity == 5
    assert fill.resting_order_id == 3


def test_submission_result_construction_defaults_error_none():
    fills = [Fill(trade_id=1, price=Decimal("100"), quantity=5, resting_order_id=3)]
    result = SubmissionResult(
        accepted=True,
        order_id=7,
        fills=fills,
        resting_quantity=2,
        discarded_quantity=0,
    )
    assert result.accepted is True
    assert result.order_id == 7
    assert result.fills == fills
    assert result.resting_quantity == 2
    assert result.discarded_quantity == 0
    assert result.error is None


def test_submission_result_with_error():
    err = ValidationError(code="INVALID_QUANTITY", message="bad")
    result = SubmissionResult(
        accepted=False,
        order_id=None,
        fills=[],
        resting_quantity=0,
        discarded_quantity=0,
        error=err,
    )
    assert result.accepted is False
    assert result.order_id is None
    assert result.error is err


def test_cancellation_result_construction():
    result = CancellationResult(success=True, order_id=7, removed_quantity=4)
    assert result.success is True
    assert result.order_id == 7
    assert result.removed_quantity == 4
    assert result.error is None


def test_cancellation_result_with_error():
    err = ValidationError(code="ORDER_NOT_FOUND", message="nope")
    result = CancellationResult(
        success=False, order_id=None, removed_quantity=None, error=err
    )
    assert result.success is False
    assert result.error is err


def test_book_level_construction():
    level = BookLevel(price=Decimal("100.50"), aggregate_quantity=12)
    assert level.price == Decimal("100.50")
    assert level.aggregate_quantity == 12

    empty = BookLevel(price=None, aggregate_quantity=0)
    assert empty.price is None
    assert empty.aggregate_quantity == 0


def test_top_of_book_construction():
    bid = BookLevel(price=Decimal("100"), aggregate_quantity=5)
    ask = BookLevel(price=Decimal("101"), aggregate_quantity=8)
    top = TopOfBook(best_bid=bid, best_ask=ask)
    assert top.best_bid is bid
    assert top.best_ask is ask


def test_validation_error_construction():
    err = ValidationError(code="INVALID_SIDE", message="Side must be Buy or Sell.")
    assert err.code == "INVALID_SIDE"
    assert err.message == "Side must be Buy or Sell."


# --- validate_submission: success cases -------------------------------------


def test_validate_valid_limit_order():
    normalized, error = validate_submission(
        Side.BUY, OrderType.LIMIT, 10, Decimal("100.50")
    )
    assert error is None
    assert isinstance(normalized, NormalizedSubmission)
    assert normalized.side is Side.BUY
    assert normalized.order_type is OrderType.LIMIT
    assert normalized.quantity == 10
    assert normalized.price == Decimal("100.50")


def test_validate_valid_market_order():
    normalized, error = validate_submission(Side.SELL, OrderType.MARKET, 5)
    assert error is None
    assert isinstance(normalized, NormalizedSubmission)
    assert normalized.side is Side.SELL
    assert normalized.order_type is OrderType.MARKET
    assert normalized.quantity == 5
    assert normalized.price is None


def test_validate_limit_price_normalized_from_string():
    normalized, error = validate_submission(Side.BUY, OrderType.LIMIT, 3, "99.99")
    assert error is None
    assert normalized.price == Decimal("99.99")
    assert isinstance(normalized.price, Decimal)


def test_validate_limit_price_decimal_kept():
    price = Decimal("42.42")
    normalized, error = validate_submission(Side.BUY, OrderType.LIMIT, 3, price)
    assert error is None
    assert normalized.price == price


# --- validate_submission: invalid side --------------------------------------


def test_validate_invalid_side_string():
    normalized, error = validate_submission("Buy", OrderType.LIMIT, 10, Decimal("100"))
    assert normalized is None
    assert error is not None
    assert error.code == "INVALID_SIDE"


def test_validate_invalid_side_none():
    normalized, error = validate_submission(None, OrderType.LIMIT, 10, Decimal("100"))
    assert normalized is None
    assert error.code == "INVALID_SIDE"


# --- validate_submission: invalid quantity ----------------------------------


def test_validate_invalid_quantity_zero():
    normalized, error = validate_submission(
        Side.BUY, OrderType.LIMIT, 0, Decimal("100")
    )
    assert normalized is None
    assert error.code == "INVALID_QUANTITY"


def test_validate_invalid_quantity_negative():
    normalized, error = validate_submission(
        Side.BUY, OrderType.LIMIT, -5, Decimal("100")
    )
    assert normalized is None
    assert error.code == "INVALID_QUANTITY"


def test_validate_invalid_quantity_float():
    normalized, error = validate_submission(
        Side.BUY, OrderType.LIMIT, 10.5, Decimal("100")
    )
    assert normalized is None
    assert error.code == "INVALID_QUANTITY"


def test_validate_invalid_quantity_bool():
    normalized, error = validate_submission(
        Side.BUY, OrderType.LIMIT, True, Decimal("100")
    )
    assert normalized is None
    assert error.code == "INVALID_QUANTITY"


# --- validate_submission: invalid / missing price ---------------------------


def test_validate_invalid_limit_price_zero():
    normalized, error = validate_submission(
        Side.BUY, OrderType.LIMIT, 10, Decimal("0")
    )
    assert normalized is None
    assert error.code == "INVALID_PRICE"


def test_validate_invalid_limit_price_negative():
    normalized, error = validate_submission(
        Side.BUY, OrderType.LIMIT, 10, Decimal("-1")
    )
    assert normalized is None
    assert error.code == "INVALID_PRICE"


def test_validate_missing_limit_price():
    normalized, error = validate_submission(Side.BUY, OrderType.LIMIT, 10, None)
    assert normalized is None
    assert error.code == "MISSING_FIELD"
    assert "price" in error.message


# --- validate_submission: missing quantity ----------------------------------


def test_validate_missing_quantity():
    normalized, error = validate_submission(
        Side.BUY, OrderType.LIMIT, None, Decimal("100")
    )
    assert normalized is None
    assert error.code == "MISSING_FIELD"
    assert "quantity" in error.message


def test_validate_missing_quantity_market():
    normalized, error = validate_submission(Side.SELL, OrderType.MARKET, None)
    assert normalized is None
    assert error.code == "MISSING_FIELD"
    assert "quantity" in error.message


# --- validate_submission: market order given a price ------------------------


def test_validate_market_with_price_rejected():
    normalized, error = validate_submission(
        Side.BUY, OrderType.MARKET, 5, Decimal("100")
    )
    assert normalized is None
    assert error.code == "INVALID_PRICE"
    assert "market" in error.message.lower()
