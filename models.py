"""Domain enums, the Order/Trade records, result value types, and submission validation."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum


class Side(Enum):
    BUY = "Buy"
    SELL = "Sell"


class OrderType(Enum):
    LIMIT = "Limit"
    MARKET = "Market"


@dataclass
class Order:
    """A live order tracked by the engine.

    ``remaining_quantity`` starts equal to ``quantity`` and is decremented as
    fills occur. ``price`` is ``None`` for market orders.
    """

    order_id: int
    side: Side
    order_type: OrderType
    quantity: int
    remaining_quantity: int
    price: Decimal | None = None


@dataclass(frozen=True)
class Trade:
    """An immutable record of a single execution between two orders."""

    trade_id: int
    price: Decimal
    quantity: int
    aggressor_order_id: int
    resting_order_id: int
    aggressor_side: Side
    timestamp: datetime


@dataclass(frozen=True)
class ValidationError:
    """A structured, human-readable reason a request was rejected."""

    code: str
    message: str


@dataclass(frozen=True)
class Fill:
    """One execution produced during a single submission."""

    trade_id: int
    price: Decimal
    quantity: int
    resting_order_id: int


@dataclass(frozen=True)
class SubmissionResult:
    accepted: bool
    order_id: int | None
    fills: list[Fill]
    resting_quantity: int
    discarded_quantity: int
    error: ValidationError | None = None


@dataclass(frozen=True)
class CancellationResult:
    success: bool
    order_id: int | None
    removed_quantity: int | None
    error: ValidationError | None = None


@dataclass(frozen=True)
class BookLevel:
    price: Decimal | None
    aggregate_quantity: int


@dataclass(frozen=True)
class TopOfBook:
    best_bid: BookLevel
    best_ask: BookLevel


@dataclass(frozen=True)
class NormalizedSubmission:
    """The validated, normalized fields the engine uses to build an ``Order``.

    ``order_id`` is deliberately absent: id assignment is owned by the engine
    and happens only after validation succeeds.
    """

    side: Side
    order_type: OrderType
    quantity: int
    price: Decimal | None


def _is_positive_int(value: object) -> bool:
    """True only for a genuine positive ``int`` (``bool`` is rejected)."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def validate_submission(
    side: object,
    order_type: OrderType,
    quantity: object,
    price: object = None,
) -> tuple[NormalizedSubmission | None, ValidationError | None]:
    """Validate a submission before matching.

    Returns a ``(normalized, error)`` tuple with exactly one element populated:
    a :class:`NormalizedSubmission` on success, or a :class:`ValidationError`
    describing the first problem found. The book is never touched and no
    ``order_id`` is assigned. Limit prices are normalized to :class:`~decimal.Decimal`.
    """
    if side is not Side.BUY and side is not Side.SELL:
        return None, ValidationError(
            code="INVALID_SIDE",
            message="Side must be Buy or Sell.",
        )

    if quantity is None:
        return None, ValidationError(
            code="MISSING_FIELD",
            message="Missing required field: quantity.",
        )

    if order_type is OrderType.LIMIT and price is None:
        return None, ValidationError(
            code="MISSING_FIELD",
            message="Missing required field: price.",
        )

    if not _is_positive_int(quantity):
        return None, ValidationError(
            code="INVALID_QUANTITY",
            message="Quantity must be a positive integer.",
        )

    normalized_price: Decimal | None = None
    if order_type is OrderType.LIMIT:
        if isinstance(price, Decimal):
            normalized_price = price
        else:
            try:
                normalized_price = Decimal(str(price))
            except (InvalidOperation, ValueError, TypeError):
                return None, ValidationError(
                    code="INVALID_PRICE",
                    message="Limit price must be a positive number.",
                )
        if normalized_price <= 0:
            return None, ValidationError(
                code="INVALID_PRICE",
                message="Limit price must be a positive number.",
            )
    else:
        if price is not None:
            return None, ValidationError(
                code="INVALID_PRICE",
                message="Market orders must not carry a price.",
            )

    return (
        NormalizedSubmission(
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=normalized_price,
        ),
        None,
    )
