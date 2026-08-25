"""Deterministic unit tests for cli.py (Task 7.4).

The REPL is exercised through injected ``input_fn``/``output_fn``: a scripted
list of command lines is fed in, and every ``output_fn`` call is captured into a
list so assertions target observable output strings only. A ``real`` engine is
used (no mocks) so results reflect genuine matching behavior; a lightweight spy
engine is used only to assert the CLI does NOT call the engine on
malformed/unknown input. Deterministic assertions only — no property testing.
"""

from decimal import Decimal

import pytest

import cli
from matching_engine import MatchingEngine
from models import OrderType, Side


# --- Test harness -----------------------------------------------------------


def make_input_fn(lines):
    """Build an ``input_fn`` yielding each line then raising ``EOFError``."""
    iterator = iter(lines)

    def input_fn():
        try:
            return next(iterator)
        except StopIteration:
            raise EOFError

    return input_fn


class OutputCapture:
    """Collects every ``output_fn`` call and exposes joined text for assertions."""

    def __init__(self):
        self.lines = []

    def __call__(self, text):
        self.lines.append(text)

    @property
    def text(self):
        return "\n".join(self.lines)


class SpyEngine:
    """Records whether any engine method was invoked (to prove the CLI abstained)."""

    def __init__(self):
        self.called = False

    def submit(self, *args, **kwargs):
        self.called = True
        raise AssertionError("engine.submit should not have been called")

    def cancel(self, *args, **kwargs):
        self.called = True
        raise AssertionError("engine.cancel should not have been called")

    def top_of_book(self, *args, **kwargs):
        self.called = True
        raise AssertionError("engine.top_of_book should not have been called")

    def trade_history(self, *args, **kwargs):
        self.called = True
        raise AssertionError("engine.trade_history should not have been called")


def drive(engine, lines):
    """Run the REPL over ``lines`` and return the captured output helper."""
    out = OutputCapture()
    cli.run(engine, input_fn=make_input_fn(lines), output_fn=out)
    return out


# --- limit submission -------------------------------------------------------


def test_limit_submit_shows_order_id():
    engine = MatchingEngine()
    out = drive(engine, ["limit buy 10 100.50"])
    assert out.text == "Accepted order 1"


def test_limit_case_insensitive_side():
    engine = MatchingEngine()
    out = drive(engine, ["limit SELL 5 101"])
    assert "Accepted order 1" in out.text


# --- market submission ------------------------------------------------------


def test_market_submit_shows_fills_and_discarded():
    engine = MatchingEngine()
    # Rest a sell limit of 5 @ 100, then a market buy of 8 -> fill 5, discard 3.
    out = drive(
        engine,
        [
            "limit sell 5 100",
            "market buy 8",
        ],
    )
    assert "Accepted order 1" in out.text
    assert "Trade 1: 5 @ 100" in out.text
    assert "Discarded 3 unfilled" in out.text


def test_market_no_fill_all_discarded():
    engine = MatchingEngine()
    out = drive(engine, ["market buy 4"])
    assert "Accepted order 1" in out.text
    assert "Discarded 4 unfilled" in out.text


# --- cancel -----------------------------------------------------------------


def test_cancel_success():
    engine = MatchingEngine()
    out = drive(
        engine,
        [
            "limit buy 7 99",
            "cancel 1",
        ],
    )
    assert "Cancelled order 1 (removed 7)" in out.text


def test_cancel_not_found():
    engine = MatchingEngine()
    out = drive(engine, ["cancel 42"])
    assert out.text == "No order 42 exists"


# --- book -------------------------------------------------------------------


def test_book_populated_both_sides():
    engine = MatchingEngine()
    out = drive(
        engine,
        [
            "limit buy 12 100.50",
            "limit sell 8 101.00",
            "book",
        ],
    )
    assert "Bid: 100.50 x 12 | Ask: 101.00 x 8" in out.lines


def test_book_empty_side_indicator():
    engine = MatchingEngine()
    out = drive(engine, ["book"])
    assert out.text == "Bid: -- (none) | Ask: -- (none)"


def test_book_one_empty_side():
    engine = MatchingEngine()
    out = drive(
        engine,
        [
            "limit buy 3 50",
            "book",
        ],
    )
    assert "Bid: 50 x 3 | Ask: -- (none)" in out.lines


# --- trades -----------------------------------------------------------------


def test_trades_empty_indicator():
    engine = MatchingEngine()
    out = drive(engine, ["trades"])
    assert out.text == "No trades yet"


def test_trades_populated():
    engine = MatchingEngine()
    out = drive(
        engine,
        [
            "limit sell 5 100",
            "limit buy 5 100",
            "trades",
        ],
    )
    assert "Trade 1: 5 @ 100 (Buy)" in out.text


# --- help -------------------------------------------------------------------


def test_help_lists_commands():
    engine = MatchingEngine()
    out = drive(engine, ["help"])
    for keyword in ("limit", "market", "cancel", "book", "trades", "help", "exit"):
        assert keyword in out.text


# --- exit / quit ------------------------------------------------------------


def test_exit_terminates_loop():
    engine = MatchingEngine()
    # The command after exit must never execute.
    out = drive(engine, ["exit", "limit buy 1 1"])
    assert out.lines == []


def test_quit_alias_terminates_loop():
    engine = MatchingEngine()
    out = drive(engine, ["quit", "limit buy 1 1"])
    assert out.lines == []


def test_eof_terminates_gracefully():
    engine = MatchingEngine()
    # No lines at all -> input_fn raises EOFError immediately.
    out = drive(engine, [])
    assert out.lines == []


def test_blank_line_ignored():
    engine = MatchingEngine()
    out = drive(engine, ["", "   ", "book"])
    # Only the book command produces output; blanks are silently skipped.
    assert out.lines == ["Bid: -- (none) | Ask: -- (none)"]


# --- unknown command --------------------------------------------------------


def test_unknown_command_error_and_list_engine_not_called():
    spy = SpyEngine()
    out = drive(spy, ["frobnicate 1 2"])
    assert "Unknown command 'frobnicate'" in out.text
    # Supported commands are listed.
    for keyword in ("limit", "market", "cancel", "book", "trades", "help", "exit"):
        assert keyword in out.text
    assert spy.called is False


# --- malformed / missing arguments (engine not called) ----------------------


def test_limit_wrong_arity_usage_engine_not_called():
    spy = SpyEngine()
    out = drive(spy, ["limit buy 10"])  # missing price
    assert out.text == cli.USAGE["limit"]
    assert spy.called is False


def test_limit_unparseable_qty_usage_engine_not_called():
    spy = SpyEngine()
    out = drive(spy, ["limit buy abc 100"])
    assert out.text == cli.USAGE["limit"]
    assert spy.called is False


def test_limit_unparseable_price_usage_engine_not_called():
    spy = SpyEngine()
    out = drive(spy, ["limit buy 10 xyz"])
    assert out.text == cli.USAGE["limit"]
    assert spy.called is False


def test_limit_bad_side_usage_engine_not_called():
    spy = SpyEngine()
    out = drive(spy, ["limit hold 10 100"])
    assert out.text == cli.USAGE["limit"]
    assert spy.called is False


def test_market_wrong_arity_usage_engine_not_called():
    spy = SpyEngine()
    out = drive(spy, ["market buy"])  # missing qty
    assert out.text == cli.USAGE["market"]
    assert spy.called is False


def test_market_unparseable_qty_usage_engine_not_called():
    spy = SpyEngine()
    out = drive(spy, ["market buy ten"])
    assert out.text == cli.USAGE["market"]
    assert spy.called is False


def test_cancel_wrong_arity_usage_engine_not_called():
    spy = SpyEngine()
    out = drive(spy, ["cancel"])  # missing id
    assert out.text == cli.USAGE["cancel"]
    assert spy.called is False


def test_cancel_unparseable_id_usage_engine_not_called():
    spy = SpyEngine()
    out = drive(spy, ["cancel notanid"])
    assert out.text == cli.USAGE["cancel"]
    assert spy.called is False


def test_book_extra_args_usage_engine_not_called():
    spy = SpyEngine()
    out = drive(spy, ["book extra"])
    assert out.text == cli.USAGE["book"]
    assert spy.called is False


def test_trades_extra_args_usage_engine_not_called():
    spy = SpyEngine()
    out = drive(spy, ["trades extra"])
    assert out.text == cli.USAGE["trades"]
    assert spy.called is False


# --- validation-rejection surfacing -----------------------------------------


def test_limit_zero_qty_rejected_by_engine_no_order_id():
    engine = MatchingEngine()
    # "0" parses fine at the CLI; the engine rejects qty <= 0.
    out = drive(engine, ["limit buy 0 100"])
    assert "Quantity must be a positive integer." in out.text
    assert "Accepted order" not in out.text


def test_limit_negative_qty_forwarded_then_rejected():
    engine = MatchingEngine()
    # "-5" parses as an int fine and is forwarded; engine rejects it.
    out = drive(engine, ["limit buy -5 100"])
    assert "Quantity must be a positive integer." in out.text
    assert "Accepted order" not in out.text


def test_limit_zero_price_rejected_by_engine():
    engine = MatchingEngine()
    out = drive(engine, ["limit buy 10 0"])
    assert "Limit price must be a positive number." in out.text
    assert "Accepted order" not in out.text


def test_cancel_invalid_id_surfaces_validation_message():
    engine = MatchingEngine()
    # "-3" parses as an int; engine rejects via INVALID_ID.
    out = drive(engine, ["cancel -3"])
    assert "Order id must be a positive integer." in out.text


# --- entrypoint -------------------------------------------------------------


def test_main_is_callable_and_wires_engine(monkeypatch):
    captured = {}

    def fake_run(engine, *args, **kwargs):
        captured["engine"] = engine

    monkeypatch.setattr(cli, "run", fake_run)
    cli.main()
    assert isinstance(captured["engine"], MatchingEngine)
