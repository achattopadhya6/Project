"""Resting-order storage organized by side and price level.

Each side keeps three coordinated structures: ``levels`` maps a price to a FIFO
deque of orders (time priority within a level); a ``heapq`` price index yields
the best price (the buy side negates prices to act as a max-heap, the sell side
uses plain prices as a min-heap); and ``by_id`` gives O(1) lookup/cancellation.
A price is pushed onto the heap only when its level is newly created; stale
entries for emptied levels are reaped lazily on the next best-price peek.
"""

from collections import deque
from decimal import Decimal
import heapq

from models import BookLevel, Order, Side


class _SideBook:
    """Resting orders for a single side (buy or sell)."""

    def __init__(self, buy: bool) -> None:
        self._buy = buy
        self.levels: dict[Decimal, deque[Order]] = {}
        self.price_heap: list[Decimal] = []
        self.by_id: dict[int, Order] = {}

    def _heap_key(self, price: Decimal) -> Decimal:
        # Negate on the buy side so the max price surfaces from the min-heap.
        return -price if self._buy else price

    def add(self, order: Order) -> None:
        """Rest ``order`` at its price level.

        The price is pushed onto the heap only when the level is newly created;
        orders joining an existing level share that one heap entry and deque.
        """
        price = order.price
        level = self.levels.get(price)
        if level is None:
            level = deque()
            self.levels[price] = level
            heapq.heappush(self.price_heap, self._heap_key(price))
        level.append(order)
        self.by_id[order.order_id] = order

    def _best_price(self) -> Decimal | None:
        """Return the best resting price, discarding stale heap entries.

        Lazy deletion: heap entries whose level is missing or empty are popped
        until a live level is found (or the heap is exhausted).
        """
        heap = self.price_heap
        while heap:
            price = -heap[0] if self._buy else heap[0]
            level = self.levels.get(price)
            if level:
                return price
            heapq.heappop(heap)
        return None

    def best_level(self) -> BookLevel:
        """Best price plus aggregate remaining quantity, or an empty level."""
        price = self._best_price()
        if price is None:
            return BookLevel(price=None, aggregate_quantity=0)
        aggregate = sum(o.remaining_quantity for o in self.levels[price])
        return BookLevel(price=price, aggregate_quantity=aggregate)

    def best_order(self) -> Order | None:
        """Peek the best-price, earliest-arrival resting order (no removal)."""
        price = self._best_price()
        if price is None:
            return None
        return self.levels[price][0]

    def pop_best(self) -> Order | None:
        """Remove and return the front order of the best price level.

        Uses ``deque.popleft()`` and drops the level when its deque empties (the
        heap entry is reaped lazily later). Used for full-fill removal only.
        """
        price = self._best_price()
        if price is None:
            return None
        level = self.levels[price]
        order = level.popleft()
        del self.by_id[order.order_id]
        if not level:
            del self.levels[price]
        return order

    def remove(self, order_id: int) -> Order | None:
        """Cancellation path: remove an arbitrary resting order by id.

        Scans the order's price-level deque to remove the specific object, so
        it is not used on the full-fill hot path.
        """
        order = self.by_id.get(order_id)
        if order is None:
            return None
        level = self.levels.get(order.price)
        if level is not None:
            level.remove(order)
            if not level:
                del self.levels[order.price]
        del self.by_id[order_id]
        return order

    def get(self, order_id: int) -> Order | None:
        """Return the resting order with ``order_id`` or ``None``."""
        return self.by_id.get(order_id)


class OrderBook:
    """Resting limit orders for a single instrument, split by side."""

    def __init__(self) -> None:
        self._buy = _SideBook(buy=True)
        self._sell = _SideBook(buy=False)

    def _side_book(self, side: Side) -> _SideBook:
        return self._buy if side is Side.BUY else self._sell

    def _opposite_book(self, incoming_side: Side) -> _SideBook:
        return self._sell if incoming_side is Side.BUY else self._buy

    def add(self, order: Order) -> None:
        """Rest ``order`` on its own side."""
        self._side_book(order.side).add(order)

    def best_bid_level(self) -> BookLevel:
        """Highest resting buy price with aggregate remaining quantity."""
        return self._buy.best_level()

    def best_ask_level(self) -> BookLevel:
        """Lowest resting sell price with aggregate remaining quantity."""
        return self._sell.best_level()

    def best_opposite(self, incoming_side: Side) -> Order | None:
        """Peek the top resting order on the side opposite ``incoming_side`` (no removal)."""
        return self._opposite_book(incoming_side).best_order()

    def pop_best_opposite(self, incoming_side: Side) -> Order | None:
        """Remove and return the front order on the opposite side (full fill)."""
        return self._opposite_book(incoming_side).pop_best()

    def remove(self, order_id: int) -> Order | None:
        """Cancellation path only: remove an arbitrary resting order by id."""
        return (
            self._buy.remove(order_id)
            or self._sell.remove(order_id)
        )

    def get(self, order_id: int) -> Order | None:
        """Return the resting order with ``order_id`` from either side."""
        return self._buy.get(order_id) or self._sell.get(order_id)
