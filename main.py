"""Slow-trend cbBTC bot for make.fun btc-race-24h-20261118-1444.

Protocol: agent-fun/bars-replay/v1 (NDJSON stdin/stdout, one reply per batch).
Python 3.13, standard library only. Fully deterministic: integer arithmetic
only, no clock, no randomness, no file or network access.

Strategy (v2): slow SMA trend-following, long only, one position at a time.
  - Entry: SMA(120) crosses above SMA(240) on 1-minute closes -> buy 100%
    of cash. The slow pair is deliberate: 1-minute cbBTC is noisy (about
    7 bps per bar), so fast crosses whipsaw and each round trip costs
    roughly 26-32 bps in fee + slippage + impact. A 120/240 cross only
    fires on a multi-hour trend, so the bot trades a few times per day.
  - Exit:
      * partial profit: sell half the position at +1.2% of cost, so a
        gain is banked while the rest keeps riding the trend;
      * the rest exits (whole) on whichever comes first: SMA(120)
        crosses back below SMA(240), stop loss at -1.0% of cost, or a
        trailing stop (close falls 0.8% below the best close since
        entry). The harness cuts a position's cost proportionally on a
        partial sell, so the value/cost ratio keeps working for the
        remaining half.
  - Sells use a wider slippage cap (300 bps) than buys (100 bps) so an
    exit is not refused in a fast move; a refused sell is simply retried
    on the next bar while its reason still holds.
"""

import json
import sys

FAST_BARS = 120
SLOW_BARS = 240
TAKE_PROFIT_NUM = 1012  # value >= cost * 1012 / 1000  (+1.2%)
STOP_LOSS_NUM = 990     # value <= cost * 990 / 1000   (-1.0%)
TRAIL_NUM = 992         # close <= peak * 992 / 1000   (-0.8% from peak)
BUY_SLIPPAGE_BPS = 100
SELL_SLIPPAGE_BPS = 300


def main():
    symbol = None
    price_scale = 5
    qty_scale = 8
    quote_scale = 6
    warmup_bars = 0
    min_notional = 1000000
    cash = 0
    equity = 0
    closes = []          # CBBTC closes, raw integer units, in bar order
    prev_fast_above = None  # SMA120 > SMA240 on the previous bar
    peak_close = 0       # best close since the current position opened
    half_taken = False   # partial profit already sold for this position
    prev_held_qty = 0    # held qty on the previous batch
    order_no = 0

    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        kind = msg.get("type")
        if kind == "hello":
            sym = msg["symbols"][0]
            symbol = sym["symbol"]
            price_scale = int(sym["price_scale"])
            qty_scale = int(sym["qty_scale"])
            quote_scale = int(msg["capital"]["quote_scale"])
            warmup_bars = int(msg.get("warmup_bars") or 0)
            min_notional = int(msg["fees"]["min_notional_quote_units"])
            cash = int(msg["capital"]["quote_units"])
            equity = cash
            continue
        if kind == "done":
            break
        if kind != "batch":
            raise ValueError("unknown message type: %r" % (kind,))

        seq = int(msg["seq"])
        # Fold the account in first: cash, equity and the held position.
        account = msg["account"]
        cash = int(account["cash_quote_units"])
        equity = int(account["equity_quote_units"])
        held_qty = 0
        held_cost = 0
        for pos in account["positions"]:
            if pos["symbol"] == symbol:
                held_qty = int(pos["qty"])
                held_cost = int(pos["cost_quote_units"])
                break

        # Fold this batch's bar in (a missing minute carries no bar).
        fresh = False
        for bar in msg["bars"]:
            if bar["symbol"] == symbol:
                closes.append(int(bar["c"]))
                fresh = True
        if not fresh:
            out.write(json.dumps({"type": "reply", "seq": seq, "orders": []},
                                 separators=(",", ":")) + "\n")
            out.flush()
            continue

        orders = []
        if len(closes) >= SLOW_BARS and seq >= warmup_bars:
            # SMA120 > SMA240  <=>  sum120 * 2 > sum240  (integer exact).
            sum_fast = sum(closes[-FAST_BARS:])
            sum_slow = sum(closes[-SLOW_BARS:])
            fast_above = sum_fast * 2 > sum_slow
            close_now = closes[-1]

            if held_qty > 0:
                # A newly opened position resets the peak / partial state.
                if prev_held_qty == 0:
                    peak_close = close_now
                    half_taken = False
                # Track the best close since entry for the trailing stop.
                if close_now > peak_close:
                    peak_close = close_now
                # Position value at this close, in quote units (integers).
                value = held_qty * close_now * (10 ** quote_scale) // (
                    10 ** (qty_scale + price_scale))
                cross_down = (
                    prev_fast_above is not None
                    and prev_fast_above
                    and not fast_above
                )
                take_profit = value * 1000 >= held_cost * TAKE_PROFIT_NUM
                stop_loss = value * 1000 <= held_cost * STOP_LOSS_NUM
                trailing = close_now * 1000 <= peak_close * TRAIL_NUM
                if not half_taken and take_profit and held_qty // 2 > 0:
                    order_no += 1
                    orders.append({
                        "side": "sell",
                        "client_id": "o%d" % order_no,
                        "symbol": symbol,
                        "qty": str(held_qty // 2),
                        "max_slippage_bps": SELL_SLIPPAGE_BPS,
                    })
                    half_taken = True
                elif cross_down or stop_loss or trailing:
                    order_no += 1
                    orders.append({
                        "side": "sell",
                        "client_id": "o%d" % order_no,
                        "symbol": symbol,
                        "qty": str(held_qty),
                        "max_slippage_bps": SELL_SLIPPAGE_BPS,
                    })
            else:
                cross_up = (
                    prev_fast_above is not None
                    and not prev_fast_above
                    and fast_above
                )
                if cross_up and cash >= min_notional:
                    order_no += 1
                    orders.append({
                        "side": "buy",
                        "client_id": "o%d" % order_no,
                        "symbol": symbol,
                        "notional_quote_units": str(cash),
                        "max_slippage_bps": BUY_SLIPPAGE_BPS,
                    })
                    # The buy fills at the next open; peak starts there.
                    peak_close = close_now
            prev_fast_above = fast_above
        elif held_qty > 0 and closes:
            # Not enough history for a signal: keep the trailing peak fresh.
            if closes[-1] > peak_close:
                peak_close = closes[-1]

        prev_held_qty = held_qty
        out.write(json.dumps({"type": "reply", "seq": seq, "orders": orders},
                             separators=(",", ":")) + "\n")
        out.flush()


if __name__ == "__main__":
    main()
