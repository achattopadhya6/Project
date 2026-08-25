# Limit Order Book & Matching Engine

A small Python simulation of an electronic exchange's limit order book and matching engine. It supports limit and market orders on a single instrument, matches incoming orders against resting ones using price-time priority, and records the resulting trades. The goal was to implement the matching logic clearly enough to explain in an interview, so it sticks to the Python standard library and avoids extra machinery.

## Features

- Buy and sell orders
- Limit orders and market orders
- Price-time priority matching
- Order cancellation by ID
- Recorded trade history
- Top-of-book view (best bid and best ask with aggregate quantities)
- Interactive command-line interface

## Price-time priority

When an incoming order matches against the other side of the book, it always takes the best price first — the lowest ask for an incoming buy, or the highest bid for an incoming sell. When several resting orders share the same price, the one that arrived earliest is matched first. Trades execute at the resting order's price. A limit order that can't be fully matched rests in the book for its remaining quantity; a market order that can't be fully filled has its leftover quantity discarded rather than rested.

## Project structure

```
models.py            # Side/OrderType enums, Order and Trade records, result types, validation
order_book.py        # Resting orders by side and price level; best bid/ask; lookup/removal by ID
matching_engine.py   # Matching loop, trade log, cancellation, top-of-book and history queries
cli.py               # Interactive REPL and entry point
tests/               # Deterministic pytest unit tests
requirements.txt     # Runtime dependencies (none — standard library only)
requirements-dev.txt # Development dependencies (pytest)
pytest.ini           # pytest configuration
```

## Setup

Requires Python 3.10 or newer. The engine itself has no third-party runtime dependencies; only the tests need `pytest`.

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

## Running the tests

```
python -m pytest
```

## Launching the CLI

```
python cli.py
```

Available commands: `limit <buy|sell> <qty> <price>`, `market <buy|sell> <qty>`, `cancel <order_id>`, `book`, `trades`, `help`, and `exit` (or `quit`).

## Example session

```
> limit sell 5 100
Accepted order 1
> limit buy 3 101
Accepted order 2
Trade 1: 3 @ 100
> book
Bid: -- (none) | Ask: 100 x 2
> trades
Trade 1: 3 @ 100 (Buy)
```

The buy order at 101 crosses the resting sell at 100 and trades 3 units at the resting price (100). That leaves 2 units resting on the ask side, which the `book` command shows, and the fill is recorded in the trade history.

## Technical notes

- **Prices use `Decimal`** so that price comparisons and price-level grouping are exact, avoiding the rounding surprises of binary floats.
- **Each price level is a `deque`**, which keeps orders in arrival order and makes it cheap to add a new order to the back and match the oldest one from the front (FIFO time priority).
- **A heap per side tracks the best price** — a max-heap for bids and a min-heap for asks — so the best bid and best ask are quick to find. Emptied price levels are cleaned out of the heap lazily when the best price is next requested.
- **Orders are indexed by ID** in a dictionary, so looking up or cancelling a specific order is a direct lookup rather than a scan of the book.
