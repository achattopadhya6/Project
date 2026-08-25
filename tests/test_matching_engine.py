"""Deterministic unit tests for matching_engine.py (Task 5.6).

Covers the Requirement 8 matching scenarios plus validation rejection,
id/trade-id monotonicity, trade-history ordering, and cancellation error
paths. Assertions target observable outputs only — recorded trades, resting
orders (via top_of_book / cancel), and submission results — never private
engine internals. Deterministic tests only; no property-based testing.
"""

from decimal import Decimal

from matching_engine import MatchingEngine
from models import OrderType, Side


# --- Requirement 8 scenarios ------------------------------------------------


def test_crossing_limits_single_trade():
    """Crossing buy/sell limits produce exactly one trade at the RESTING price
    with qty = min of the two. _Req 8.1, 3.6, 3.7_"""
    engine = MatchingEngine()
    # Resting sell 10 @ 100 (resting order -> its price is the execution price).
    engine.submit(Side.SELL, OrderType.LIMIT, 10, Decimal("100"))
    # Aggressor buy 4 @ 101 crosses; smaller quantity determines matched qty.
    result = engine.submit(Side.BUY, OrderType.LIMIT, 4, Decimal("101"))

    trades = engine.trade_history()
    assert len(trades) == 1
    assert trades[0].price == Decimal("100")  # resting price, not 101
    assert trades[0].quantity == 4  # min(4, 10)
    assert result.accepted is True
    assert len(result.fills) == 1
    assert result.fills[0].price == Decimal("100")
    assert result.fills[0].quantity == 4
    assert result.resting_quantity == 0
    assert result.discarded_quantity == 0


def test_time_priority_within_level():
    """Two resting orders same price; incoming aggressor matches earliest
    arrival first; trades' resting_order_ids ascending by arrival. _Req 8.2, 3.3_"""
    engine = MatchingEngine()
    first = engine.submit(Side.SELL, OrderType.LIMIT, 5, Decimal("100"))
    second = engine.submit(Side.SELL, OrderType.LIMIT, 5, Decimal("100"))
    # Aggressor sweeps both resting orders.
    engine.submit(Side.BUY, OrderType.LIMIT, 10, Decimal("100"))

    trades = engine.trade_history()
    assert len(trades) == 2
    # Earliest arrival (lower id) matched first.
    assert trades[0].resting_order_id == first.order_id
    assert trades[1].resting_order_id == second.order_id
    assert first.order_id < second.order_id


def test_sweep_multiple_resting():
    """Aggressor larger than one resting order sweeps multiple; trade count ==
    number of resting orders consumed. _Req 8.3, 3.9, 3.11_"""
    engine = MatchingEngine()
    engine.submit(Side.SELL, OrderType.LIMIT, 3, Decimal("100"))
    engine.submit(Side.SELL, OrderType.LIMIT, 3, Decimal("101"))
    engine.submit(Side.SELL, OrderType.LIMIT, 3, Decimal("102"))
    # Buy 9 @ 102 crosses all three levels.
    result = engine.submit(Side.BUY, OrderType.LIMIT, 9, Decimal("102"))

    trades = engine.trade_history()
    assert len(trades) == 3  # one per resting order consumed
    # Swept from best (lowest ask) to worst.
    assert [t.price for t in trades] == [Decimal("100"), Decimal("101"), Decimal("102")]
    assert result.resting_quantity == 0
    # Opposite side fully consumed.
    top = engine.top_of_book()
    assert top.best_ask.price is None
    assert top.best_ask.aggregate_quantity == 0


def test_partial_fill_rests_remainder():
    """Partially filled incoming LIMIT rests remainder = submitted - matched.
    _Req 8.4, 2.7, 3.8_"""
    engine = MatchingEngine()
    engine.submit(Side.SELL, OrderType.LIMIT, 4, Decimal("100"))
    # Buy 10 @ 100: 4 matched, 6 rests as a bid at 100.
    result = engine.submit(Side.BUY, OrderType.LIMIT, 10, Decimal("100"))

    assert result.resting_quantity == 6  # 10 - 4
    assert result.discarded_quantity == 0
    top = engine.top_of_book()
    assert top.best_bid.price == Decimal("100")
    assert top.best_bid.aggregate_quantity == 6
    # Ask side fully consumed.
    assert top.best_ask.price is None


def test_market_fills_then_discards():
    """Market order fills against best available then discards remainder; not
    added to book. _Req 8.5, 2.4, 2.6_"""
    engine = MatchingEngine()
    engine.submit(Side.SELL, OrderType.LIMIT, 3, Decimal("100"))
    # Market buy 10: fills 3, discards 7. Never rests.
    result = engine.submit(Side.BUY, OrderType.MARKET, 10)

    assert result.accepted is True
    assert result.discarded_quantity == 7
    assert result.resting_quantity == 0
    assert len(result.fills) == 1
    assert result.fills[0].quantity == 3
    # Market remainder did NOT rest as a bid.
    top = engine.top_of_book()
    assert top.best_bid.price is None
    assert top.best_bid.aggregate_quantity == 0
    assert top.best_ask.price is None  # ask fully consumed


def test_cancel_prevents_match():
    """Cancel a resting order, then a later crossing aggressor produces no
    trade against the cancelled id. _Req 8.6, 4.4_"""
    engine = MatchingEngine()
    resting = engine.submit(Side.SELL, OrderType.LIMIT, 5, Decimal("100"))
    cancel_result = engine.cancel(resting.order_id)
    assert cancel_result.success is True
    assert cancel_result.removed_quantity == 5

    # A crossing buy now finds nothing to match; it rests instead.
    engine.submit(Side.BUY, OrderType.LIMIT, 5, Decimal("101"))
    assert engine.trade_history() == []
    top = engine.top_of_book()
    assert top.best_bid.price == Decimal("101")
    assert top.best_ask.price is None


def test_top_of_book_aggregate():
    """Best bid/ask price and summed remaining quantity at each level.
    _Req 8.7, 6.1, 6.2, 6.5_"""
    engine = MatchingEngine()
    engine.submit(Side.BUY, OrderType.LIMIT, 5, Decimal("99"))
    engine.submit(Side.BUY, OrderType.LIMIT, 7, Decimal("99"))
    engine.submit(Side.BUY, OrderType.LIMIT, 3, Decimal("98"))  # worse bid
    engine.submit(Side.SELL, OrderType.LIMIT, 4, Decimal("101"))
    engine.submit(Side.SELL, OrderType.LIMIT, 6, Decimal("101"))
    engine.submit(Side.SELL, OrderType.LIMIT, 2, Decimal("102"))  # worse ask

    top = engine.top_of_book()
    assert top.best_bid.price == Decimal("99")
    assert top.best_bid.aggregate_quantity == 12  # 5 + 7
    assert top.best_ask.price == Decimal("101")
    assert top.best_ask.aggregate_quantity == 10  # 4 + 6


def test_non_crossing_limit_rests():
    """Buy limit below best ask yields zero trades and rests in the book.
    _Req 8.8, 3.4_"""
    engine = MatchingEngine()
    engine.submit(Side.SELL, OrderType.LIMIT, 5, Decimal("100"))
    # Buy 5 @ 99 < 100 ask: no cross.
    result = engine.submit(Side.BUY, OrderType.LIMIT, 5, Decimal("99"))

    assert engine.trade_history() == []
    assert result.fills == []
    assert result.resting_quantity == 5
    top = engine.top_of_book()
    assert top.best_bid.price == Decimal("99")
    assert top.best_bid.aggregate_quantity == 5
    assert top.best_ask.price == Decimal("100")
    assert top.best_ask.aggregate_quantity == 5


# --- Validation rejection propagation ---------------------------------------


def test_invalid_quantity_rejected_and_book_unchanged():
    """Invalid quantity -> accepted False with INVALID_QUANTITY; book unchanged,
    no id consumed. _Req 1.6, 8.9_"""
    engine = MatchingEngine()
    result = engine.submit(Side.BUY, OrderType.LIMIT, 0, Decimal("100"))
    assert result.accepted is False
    assert result.order_id is None
    assert result.error is not None
    assert result.error.code == "INVALID_QUANTITY"
    # Book unchanged.
    top = engine.top_of_book()
    assert top.best_bid.price is None
    assert top.best_ask.price is None
    # No id consumed: next accepted order still gets id 1.
    accepted = engine.submit(Side.BUY, OrderType.LIMIT, 5, Decimal("100"))
    assert accepted.order_id == 1


def test_invalid_side_rejected():
    """Side not exactly Buy/Sell -> INVALID_SIDE. _Req 8.9_"""
    engine = MatchingEngine()
    result = engine.submit("buy", OrderType.LIMIT, 5, Decimal("100"))
    assert result.accepted is False
    assert result.error.code == "INVALID_SIDE"
    assert result.order_id is None


def test_invalid_price_rejected():
    """Limit price <= 0 -> INVALID_PRICE. _Req 8.9_"""
    engine = MatchingEngine()
    result = engine.submit(Side.SELL, OrderType.LIMIT, 5, Decimal("0"))
    assert result.accepted is False
    assert result.error.code == "INVALID_PRICE"
    assert result.order_id is None


def test_rejections_do_not_consume_ids():
    """Only accepted orders consume ids; monotonic from 1. _Req 1.6_"""
    engine = MatchingEngine()
    engine.submit(Side.BUY, OrderType.LIMIT, -1, Decimal("100"))  # rejected
    first = engine.submit(Side.BUY, OrderType.LIMIT, 5, Decimal("100"))
    engine.submit(Side.SELL, OrderType.LIMIT, 5, Decimal("0"))  # rejected
    second = engine.submit(Side.SELL, OrderType.LIMIT, 5, Decimal("200"))
    assert first.order_id == 1
    assert second.order_id == 2


# --- ID / trade-id monotonicity ---------------------------------------------


def test_order_id_monotonic_from_one():
    """Accepted order ids are monotonically increasing from 1. _Req 1.6_"""
    engine = MatchingEngine()
    ids = [
        engine.submit(Side.BUY, OrderType.LIMIT, 1, Decimal("10")).order_id
        for _ in range(4)
    ]
    assert ids == [1, 2, 3, 4]


def test_trade_id_monotonic_and_unique():
    """Trade ids are monotonic and unique in occurrence order. _Req 5.4_"""
    engine = MatchingEngine()
    engine.submit(Side.SELL, OrderType.LIMIT, 2, Decimal("100"))
    engine.submit(Side.SELL, OrderType.LIMIT, 2, Decimal("101"))
    engine.submit(Side.BUY, OrderType.LIMIT, 4, Decimal("101"))  # two trades

    trades = engine.trade_history()
    trade_ids = [t.trade_id for t in trades]
    assert trade_ids == [1, 2]  # monotonic from 1
    assert len(set(trade_ids)) == len(trade_ids)  # unique


# --- Trade history ordering / empty case ------------------------------------


def test_trade_history_empty_when_no_matches():
    """trade_history is an empty list when nothing has matched. _Req 5.6_"""
    engine = MatchingEngine()
    assert engine.trade_history() == []
    engine.submit(Side.BUY, OrderType.LIMIT, 5, Decimal("100"))  # rests, no trade
    assert engine.trade_history() == []


def test_trade_history_ascending_occurrence_order():
    """Trades are returned in ascending occurrence order. _Req 5.5, 5.6_"""
    engine = MatchingEngine()
    engine.submit(Side.SELL, OrderType.LIMIT, 1, Decimal("100"))
    engine.submit(Side.BUY, OrderType.LIMIT, 1, Decimal("100"))  # trade 1
    engine.submit(Side.SELL, OrderType.LIMIT, 1, Decimal("100"))
    engine.submit(Side.BUY, OrderType.LIMIT, 1, Decimal("100"))  # trade 2

    trades = engine.trade_history()
    assert [t.trade_id for t in trades] == [1, 2]

    # Returned list is a copy: mutating it does not affect the engine.
    trades.clear()
    assert len(engine.trade_history()) == 2


# --- Cancellation error paths -----------------------------------------------


def test_cancel_invalid_id():
    """Malformed identifier -> INVALID_ID, book unchanged. _Req 4.3_"""
    engine = MatchingEngine()
    resting = engine.submit(Side.SELL, OrderType.LIMIT, 5, Decimal("100"))

    for bad in (0, -3, "abc", 1.5, True):
        result = engine.cancel(bad)
        assert result.success is False
        assert result.error.code == "INVALID_ID"
        assert result.removed_quantity is None

    # Book unchanged: the resting order is still cancellable normally.
    ok = engine.cancel(resting.order_id)
    assert ok.success is True
    assert ok.removed_quantity == 5


def test_cancel_order_not_found():
    """Unknown id -> ORDER_NOT_FOUND, book unchanged. _Req 4.2_"""
    engine = MatchingEngine()
    engine.submit(Side.SELL, OrderType.LIMIT, 5, Decimal("100"))
    result = engine.cancel(999)
    assert result.success is False
    assert result.error.code == "ORDER_NOT_FOUND"
    assert result.removed_quantity is None
    # Existing resting order untouched.
    top = engine.top_of_book()
    assert top.best_ask.price == Decimal("100")
    assert top.best_ask.aggregate_quantity == 5


def test_cancel_partial_fill_remainder():
    """Cancelling a partially filled resting order removes only the remainder,
    leaving recorded trades untouched. _Req 4.5_"""
    engine = MatchingEngine()
    resting = engine.submit(Side.SELL, OrderType.LIMIT, 10, Decimal("100"))
    engine.submit(Side.BUY, OrderType.LIMIT, 4, Decimal("100"))  # fills 4 of 10

    result = engine.cancel(resting.order_id)
    assert result.success is True
    assert result.removed_quantity == 6  # 10 - 4
    # Previously recorded trade is untouched.
    assert len(engine.trade_history()) == 1
    top = engine.top_of_book()
    assert top.best_ask.price is None
