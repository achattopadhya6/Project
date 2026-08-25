"""Interactive read-eval-print loop for driving the matching engine.

The only module doing stdin/stdout I/O: it parses a command line, validates
arity, forwards to the engine, and formats the result. Business-rule validation
(quantity/price positivity, etc.) stays in the engine and is surfaced from the
returned ``ValidationError``.
"""

from decimal import Decimal, InvalidOperation

from matching_engine import MatchingEngine
from models import OrderType, Side

USAGE = {
    "limit": "Usage: limit <buy|sell> <qty> <price>",
    "market": "Usage: market <buy|sell> <qty>",
    "cancel": "Usage: cancel <order_id>",
    "book": "Usage: book",
    "trades": "Usage: trades",
    "help": "Usage: help",
    "exit": "Usage: exit",
}

# ``quit`` is accepted by the dispatcher as an alias for ``exit``.
SUPPORTED_COMMANDS = ("limit", "market", "cancel", "book", "trades", "help", "exit")


def _parse_side(text: str) -> Side | None:
    """Map case-insensitive ``buy``/``sell`` text to a ``Side`` (else ``None``)."""
    lowered = text.lower()
    if lowered == "buy":
        return Side.BUY
    if lowered == "sell":
        return Side.SELL
    return None


def _parse_int(text: str) -> int | None:
    """Parse a base-10 integer, returning ``None`` when not parseable."""
    try:
        return int(text)
    except ValueError:
        return None


def _parse_decimal(text: str) -> Decimal | None:
    """Parse a ``Decimal``, returning ``None`` when not parseable."""
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def format_submission(result) -> str:
    """Format a ``SubmissionResult``: the error message, or the accepted id
    followed by any fills and an unfilled-market-remainder note."""
    if not result.accepted:
        return result.error.message

    lines = [f"Accepted order {result.order_id}"]
    for fill in result.fills:
        lines.append(f"Trade {fill.trade_id}: {fill.quantity} @ {fill.price}")
    if result.discarded_quantity > 0:
        lines.append(f"Discarded {result.discarded_quantity} unfilled")
    return "\n".join(lines)


def format_cancellation(result) -> str:
    """Format a ``CancellationResult``: a success line, a not-found message, or
    the underlying ``ValidationError.message``."""
    if result.success:
        return f"Cancelled order {result.order_id} (removed {result.removed_quantity})"
    if result.error is not None and result.error.code == "ORDER_NOT_FOUND":
        return f"No order {result.order_id} exists"
    return result.error.message


def _format_level(label: str, level) -> str:
    """Format a single top-of-book side; unavailable side shows ``-- (none)``."""
    if level.price is None:
        return f"{label}: -- (none)"
    return f"{label}: {level.price} x {level.aggregate_quantity}"


def format_top_of_book(top) -> str:
    """Format a ``TopOfBook`` as ``Bid: ... | Ask: ...``."""
    bid = _format_level("Bid", top.best_bid)
    ask = _format_level("Ask", top.best_ask)
    return f"{bid} | {ask}"


def format_trades(trades) -> str:
    """Format the trade history; an empty history prints ``No trades yet``."""
    if not trades:
        return "No trades yet"
    lines = []
    for trade in trades:
        lines.append(
            f"Trade {trade.trade_id}: {trade.quantity} @ {trade.price} "
            f"({trade.aggressor_side.value})"
        )
    return "\n".join(lines)


def format_help() -> str:
    """List the supported commands with their syntax."""
    lines = ["Supported commands:"]
    for command in SUPPORTED_COMMANDS:
        lines.append(f"  {USAGE[command]}")
    lines.append("  quit  (alias for exit)")
    return "\n".join(lines)


def _format_unknown(command: str) -> str:
    """Error for an unrecognized keyword plus the supported-command list."""
    lines = [f"Unknown command '{command}'", "Supported commands:"]
    for name in SUPPORTED_COMMANDS:
        lines.append(f"  {name}")
    return "\n".join(lines)


def _handle_limit(engine, args, output_fn) -> None:
    if len(args) != 3:
        output_fn(USAGE["limit"])
        return
    side = _parse_side(args[0])
    quantity = _parse_int(args[1])
    price = _parse_decimal(args[2])
    if side is None or quantity is None or price is None:
        output_fn(USAGE["limit"])
        return
    result = engine.submit(side, OrderType.LIMIT, quantity, price)
    output_fn(format_submission(result))


def _handle_market(engine, args, output_fn) -> None:
    if len(args) != 2:
        output_fn(USAGE["market"])
        return
    side = _parse_side(args[0])
    quantity = _parse_int(args[1])
    if side is None or quantity is None:
        output_fn(USAGE["market"])
        return
    result = engine.submit(side, OrderType.MARKET, quantity)
    output_fn(format_submission(result))


def _handle_cancel(engine, args, output_fn) -> None:
    if len(args) != 1:
        output_fn(USAGE["cancel"])
        return
    order_id = _parse_int(args[0])
    if order_id is None:
        output_fn(USAGE["cancel"])
        return
    result = engine.cancel(order_id)
    output_fn(format_cancellation(result))


def _handle_book(engine, args, output_fn) -> None:
    if len(args) != 0:
        output_fn(USAGE["book"])
        return
    output_fn(format_top_of_book(engine.top_of_book()))


def _handle_trades(engine, args, output_fn) -> None:
    if len(args) != 0:
        output_fn(USAGE["trades"])
        return
    output_fn(format_trades(engine.trade_history()))


def _handle_help(engine, args, output_fn) -> None:
    if len(args) != 0:
        output_fn(USAGE["help"])
        return
    output_fn(format_help())


def run(engine: MatchingEngine, input_fn=input, output_fn=print) -> None:
    """Read-eval-print loop driving ``engine``.

    Blank lines are ignored. Unrecognized keywords print an error plus the
    supported-command list without calling the engine. ``exit``/``quit`` — or
    an ``EOFError`` from ``input_fn`` — ends the loop.
    """
    handlers = {
        "limit": _handle_limit,
        "market": _handle_market,
        "cancel": _handle_cancel,
        "book": _handle_book,
        "trades": _handle_trades,
        "help": _handle_help,
    }

    while True:
        try:
            line = input_fn()
        except EOFError:
            return

        tokens = line.split()
        if not tokens:
            continue

        command, args = tokens[0], tokens[1:]

        if command in ("exit", "quit"):
            return

        handler = handlers.get(command)
        if handler is None:
            output_fn(_format_unknown(command))
            continue

        handler(engine, args, output_fn)


def main() -> None:
    """Construct a fresh engine and launch the interactive REPL."""
    engine = MatchingEngine()
    run(engine)


if __name__ == "__main__":
    main()
