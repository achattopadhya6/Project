"""Deterministic unit tests for order_book.py (Task 3.5).

Covers add into new vs existing price levels (heap-push discipline observed via
best-level correctness), best bid/ask aggregate quantity and empty-side
BookLevel, best_opposite peek vs pop_best_opposite removal + level drop + FIFO
and price ordering, and remove/get by id including a partially-filled remainder.

Deterministic assertions only — no property-based testing. Assertions target
the observable surface (best_*_level, best_opposite, get, returned orders).
"""

from decimal import Decimal

from models import BookLevel, Order, OrderType, Side
from order_book import OrderBook


def _limit(order_id: int, side: Side, quantity: int, price: str) -> Order:
    return Order(
        order_id=order_id,
        side=side,
        order_type=OrderType.LIMIT,
        quantity=quantity,
        remaining_quantity=quantity,
        price=Decimal(price),
    )


# --- add: new vs existing price levels + heap-push discipline ---------------


def test_add_first_order_creates_level_and_is_best():
    book = OrderBook()
    o = _limit(1, Side.BUY, 5, "100.00")
    book.add(o)
    assert book.best_bid_level() == BookLevel(Decimal("100.00"), 5)


def test_add_same_price_shares_one_level():
    book = OrderBook()
    book.add(_limit(1, Side.BUY, 5, "100.00"))
    book.add(_limit(2, Side.BUY, 3, "100.00"))
    # Both orders share the single price level; aggregate reflects both.
    assert book.best_bid_level() == BookLevel(Decimal("100.00"), 8)


def test_add_new_price_creates_new_level_and_updates_best_bid():
    book = OrderBook()
    book.add(_limit(1, Side.BUY, 5, "100.00"))
    book.add(_limit(2, Side.BUY, 4, "101.00"))
    # Higher buy price becomes the best bid.
    assert book.best_bid_level() == BookLevel(Decimal("101.00"), 4)


def test_add_new_price_creates_new_level_and_updates_best_ask():
    book = OrderBook()
    book.add(_limit(1, Side.SELL, 5, "101.00"))
    book.add(_limit(2, Side.SELL, 4, "100.00"))
    # Lower sell price becomes the best ask.
    assert book.best_ask_level() == BookLevel(Decimal("100.00"), 4)


# --- best bid / best ask levels + empty side --------------------------------


def test_best_bid_level_aggregates_across_orders_at_level():
    book = OrderBook()
    book.add(_limit(1, Side.BUY, 5, "100.00"))
    book.add(_limit(2, Side.BUY, 7, "100.00"))
    book.add(_limit(3, Side.BUY, 2, "99.00"))
    level = book.best_bid_level()
    assert level.price == Decimal("100.00")
    assert level.aggregate_quantity == 12


def test_best_ask_level_picks_lowest_price():
    book = OrderBook()
    book.add(_limit(1, Side.SELL, 5, "101.00"))
    book.add(_limit(2, Side.SELL, 6, "102.00"))
    assert book.best_ask_level() == BookLevel(Decimal("101.00"), 5)


def test_empty_side_returns_none_book_level():
    book = OrderBook()
    assert book.best_bid_level() == BookLevel(price=None, aggregate_quantity=0)
    assert book.best_ask_level() == BookLevel(price=None, aggregate_quantity=0)


# --- best_opposite peek vs pop_best_opposite removal ------------------------


def test_best_opposite_returns_none_when_opposite_empty():
    book = OrderBook()
    # No resting sells, so an incoming buy has no opposite order.
    assert book.best_opposite(Side.BUY) is None


def test_best_opposite_peeks_lowest_ask_for_incoming_buy():
    book = OrderBook()
    book.add(_limit(1, Side.SELL, 5, "101.00"))
    book.add(_limit(2, Side.SELL, 4, "100.00"))
    peeked = book.best_opposite(Side.BUY)
    assert peeked.order_id == 2  # lowest ask
    # Peek does NOT remove: level unchanged, order still retrievable.
    assert book.best_opposite(Side.BUY).order_id == 2
    assert book.get(2) is peeked


def test_best_opposite_peeks_highest_bid_for_incoming_sell():
    book = OrderBook()
    book.add(_limit(1, Side.BUY, 5, "99.00"))
    book.add(_limit(2, Side.BUY, 4, "100.00"))
    assert book.best_opposite(Side.SELL).order_id == 2  # highest bid


def test_best_opposite_fifo_within_level():
    book = OrderBook()
    book.add(_limit(1, Side.SELL, 5, "100.00"))
    book.add(_limit(2, Side.SELL, 3, "100.00"))
    # Earliest arrival at the best price surfaces first.
    assert book.best_opposite(Side.BUY).order_id == 1


def test_pop_best_opposite_removes_front_and_updates_by_id():
    book = OrderBook()
    book.add(_limit(1, Side.SELL, 5, "100.00"))
    book.add(_limit(2, Side.SELL, 3, "100.00"))
    popped = book.pop_best_opposite(Side.BUY)
    assert popped.order_id == 1
    assert book.get(1) is None            # removed from by_id
    assert book.best_opposite(Side.BUY).order_id == 2  # next in FIFO
    assert book.best_ask_level() == BookLevel(Decimal("100.00"), 3)


def test_pop_best_opposite_drops_empty_level_and_advances_price():
    book = OrderBook()
    book.add(_limit(1, Side.SELL, 5, "100.00"))
    book.add(_limit(2, Side.SELL, 4, "101.00"))
    # Consume the only order at the best (lowest) price level.
    assert book.pop_best_opposite(Side.BUY).order_id == 1
    # Level dropped; next best ask is the higher price.
    assert book.best_ask_level() == BookLevel(Decimal("101.00"), 4)
    assert book.best_opposite(Side.BUY).order_id == 2


def test_pop_best_opposite_returns_none_when_empty():
    book = OrderBook()
    assert book.pop_best_opposite(Side.SELL) is None


def test_pop_best_opposite_price_ordering_across_levels_for_sell():
    book = OrderBook()
    # Incoming sell matches against bids: highest bid first.
    book.add(_limit(1, Side.BUY, 5, "99.00"))
    book.add(_limit(2, Side.BUY, 4, "100.00"))
    assert book.pop_best_opposite(Side.SELL).order_id == 2
    assert book.pop_best_opposite(Side.SELL).order_id == 1
    assert book.pop_best_opposite(Side.SELL) is None


# --- remove(order_id) and get(order_id) -------------------------------------


def test_get_returns_resting_order_then_none_after_removal():
    book = OrderBook()
    o = _limit(1, Side.BUY, 5, "100.00")
    book.add(o)
    assert book.get(1) is o
    book.remove(1)
    assert book.get(1) is None


def test_get_missing_returns_none():
    book = OrderBook()
    assert book.get(999) is None


def test_remove_missing_returns_none():
    book = OrderBook()
    book.add(_limit(1, Side.BUY, 5, "100.00"))
    assert book.remove(999) is None


def test_remove_non_front_order_in_level():
    book = OrderBook()
    book.add(_limit(1, Side.BUY, 5, "100.00"))
    book.add(_limit(2, Side.BUY, 3, "100.00"))
    book.add(_limit(3, Side.BUY, 2, "100.00"))
    # Remove the middle (not front) order.
    removed = book.remove(2)
    assert removed.order_id == 2
    assert book.get(2) is None
    # Remaining aggregate excludes the removed order; FIFO front unchanged.
    assert book.best_bid_level() == BookLevel(Decimal("100.00"), 7)
    assert book.best_opposite(Side.SELL).order_id == 1


def test_remove_partially_filled_remainder():
    book = OrderBook()
    o = _limit(1, Side.SELL, 10, "100.00")
    o.remaining_quantity = 4  # simulate a partial fill leaving a remainder
    book.add(o)
    removed = book.remove(1)
    assert removed is o
    assert removed.remaining_quantity == 4
    assert book.get(1) is None
    assert book.best_ask_level() == BookLevel(price=None, aggregate_quantity=0)


def test_remove_drops_level_when_last_order_removed():
    book = OrderBook()
    book.add(_limit(1, Side.BUY, 5, "100.00"))
    book.add(_limit(2, Side.BUY, 3, "99.00"))
    book.remove(1)
    # Best bid falls to the surviving lower level.
    assert book.best_bid_level() == BookLevel(Decimal("99.00"), 3)
