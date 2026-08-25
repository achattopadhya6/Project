"""The matching engine that orchestrates validation, matching, and queries.

Owns the ``OrderBook``, an in-memory trade log, and monotonic order/trade id
counters. It validates a submission, assigns an id only to accepted orders,
runs the price-time-priority matching loop (executing at the resting order's
price), rests any unfilled limit remainder, discards any unfilled market
remainder, and exposes cancellation plus top-of-book / trade-history queries.
"""

from datetime import datetime, timezone

from models import (
    CancellationResult,
    Fill,
    Order,
    OrderType,
    Side,
    SubmissionResult,
    TopOfBook,
    Trade,
    ValidationError,
    validate_submission,
)
from order_book import OrderBook


def _is_positive_int(value: object) -> bool:
    """True only for a genuine positive ``int`` (``bool`` is rejected)."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


class MatchingEngine:
    """Continuous double-auction matching engine for a single instrument.

    Matching uses price-time priority: an incoming order matches the
    best-priced, earliest-arriving resting order on the opposite side,
    executing at the resting order's limit price.
    """

    def __init__(self) -> None:
        self._book = OrderBook()
        self._trades: list[Trade] = []
        self._next_order_id = 1
        self._next_trade_id = 1

    def submit(
        self,
        side,
        order_type,
        quantity,
        price=None,
    ) -> SubmissionResult:
        """Validate, assign an id, match, then rest (limit) or discard (market).

        On validation failure the book is unchanged, no id is consumed, and a
        rejected result carrying the :class:`ValidationError` is returned.
        """
        normalized, error = validate_submission(side, order_type, quantity, price)
        if error is not None:
            return SubmissionResult(
                accepted=False,
                order_id=None,
                fills=[],
                resting_quantity=0,
                discarded_quantity=0,
                error=error,
            )

        order_id = self._next_order_id
        self._next_order_id += 1

        incoming = Order(
            order_id=order_id,
            side=normalized.side,
            order_type=normalized.order_type,
            quantity=normalized.quantity,
            remaining_quantity=normalized.quantity,
            price=normalized.price,
        )

        fills = self._match(incoming)

        resting_quantity = 0
        discarded_quantity = 0
        if incoming.remaining_quantity > 0:
            if incoming.order_type is OrderType.LIMIT:
                self._book.add(incoming)
                resting_quantity = incoming.remaining_quantity
            else:
                # A market remainder is discarded, never rested.
                discarded_quantity = incoming.remaining_quantity

        return SubmissionResult(
            accepted=True,
            order_id=order_id,
            fills=fills,
            resting_quantity=resting_quantity,
            discarded_quantity=discarded_quantity,
            error=None,
        )

    def _match(self, incoming: Order) -> list[Fill]:
        """Run the price-time-priority matching loop for ``incoming``.

        Returns the fills produced, in match order, and appends each trade to
        the log. A fully filled resting order is removed from the front of its
        level via ``pop_best_opposite`` (popleft) rather than a by-id scan.
        """
        fills: list[Fill] = []
        while incoming.remaining_quantity > 0:
            resting = self._book.best_opposite(incoming.side)
            if resting is None:
                break
            if not self._price_eligible(incoming, resting):
                break

            matched_qty = min(incoming.remaining_quantity, resting.remaining_quantity)
            exec_price = resting.price  # execution at the resting price

            trade = Trade(
                trade_id=self._next_trade_id,
                price=exec_price,
                quantity=matched_qty,
                aggressor_order_id=incoming.order_id,
                resting_order_id=resting.order_id,
                aggressor_side=incoming.side,
                timestamp=datetime.now(timezone.utc),
            )
            self._next_trade_id += 1
            self._trades.append(trade)
            fills.append(
                Fill(
                    trade_id=trade.trade_id,
                    price=exec_price,
                    quantity=matched_qty,
                    resting_order_id=resting.order_id,
                )
            )

            incoming.remaining_quantity -= matched_qty
            resting.remaining_quantity -= matched_qty

            if resting.remaining_quantity == 0:
                # Fully filled resting order is the front order: popleft it.
                self._book.pop_best_opposite(incoming.side)

        return fills

    @staticmethod
    def _price_eligible(incoming: Order, resting: Order) -> bool:
        """Whether ``incoming`` may match ``resting`` on price.

        Market orders are always eligible. A buy limit at ``L`` matches a
        resting sell at ``P`` when ``L >= P``; a sell limit matches when ``L <= P``.
        """
        if incoming.order_type is OrderType.MARKET:
            return True
        if incoming.side is Side.BUY:
            return incoming.price >= resting.price
        return incoming.price <= resting.price

    def cancel(self, order_id) -> CancellationResult:
        """Remove a resting order by id; report the removed remaining quantity.

        A malformed id yields ``INVALID_ID`` and an unknown id yields
        ``ORDER_NOT_FOUND``, leaving the book unchanged in both cases.
        """
        if not _is_positive_int(order_id):
            return CancellationResult(
                success=False,
                order_id=order_id,
                removed_quantity=None,
                error=ValidationError(
                    code="INVALID_ID",
                    message="Order id must be a positive integer.",
                ),
            )

        removed = self._book.remove(order_id)
        if removed is None:
            return CancellationResult(
                success=False,
                order_id=order_id,
                removed_quantity=None,
                error=ValidationError(
                    code="ORDER_NOT_FOUND",
                    message=f"No resting order with id {order_id}.",
                ),
            )

        return CancellationResult(
            success=True,
            order_id=order_id,
            removed_quantity=removed.remaining_quantity,
            error=None,
        )

    def top_of_book(self) -> TopOfBook:
        """Best bid/ask levels with aggregate quantity (nulls when empty)."""
        return TopOfBook(
            best_bid=self._book.best_bid_level(),
            best_ask=self._book.best_ask_level(),
        )

    def trade_history(self) -> list[Trade]:
        """All recorded trades in ascending occurrence order (may be empty)."""
        return list(self._trades)
