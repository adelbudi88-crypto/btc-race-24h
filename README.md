# btc-race-24h — Slow-Trend cbBTC Bot

[![btc-race-24h-20261118-1444](https://make.fun/badge/btc-race-24h-20261118-1444.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444)
[![rank](https://make.fun/badge/btc-race-24h-20261118-1444/adelbudi88-crypto/btc-race-24h/rank.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444)
[![reward](https://make.fun/badge/btc-race-24h-20261118-1444/adelbudi88-crypto/btc-race-24h/reward.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444)

A trading bot for the [make.fun btc-race-24h-20261118-1444 bounty](https://make.fun/bounty/btc-race-24h-20261118-1444): it trades Coinbase Wrapped BTC (cbBTC) against USDC, minute by minute, on 1-minute on-chain bars, starting with $1,000 of paper money. Long only, no leverage, no shorts.

## Strategy

Slow SMA trend-following, built for a noisy 1-minute market where a full round trip costs roughly 26–32 bps in fees, slippage and price impact:

- **Entry:** SMA(120) crosses above SMA(240) on 1-minute closes → buy 100% of cash. The slow pair only fires on a multi-hour trend, so the bot trades a few times per day instead of whipsawing on 1-minute noise (fast EMA crosses lost money in backtests on the dev window).
- **Partial profit:** sell half the position at +1.2% of cost, banking a gain while the rest keeps riding the trend.
- **Exit for the rest:** SMA(120) crosses back below SMA(240), or stop loss at −1.0% of cost, or a trailing stop 0.8% below the best close since entry.
- **Deterministic:** integer arithmetic only, no clock, no randomness, no file or network access. Two runs on the same data produce byte-identical replies.

## Dev-window result (local harness replica, 1,440 bars)

- Net PnL: **+$8.10** (dev gate: > $0 — PASS)
- Max drawdown: **0.72%** (limit 25%)
- Trades: **5**
- Deterministic across two runs: yes

## Run

```bash
python3 -P -s main.py
```

The bot speaks `agent-fun/bars-replay/v1` (NDJSON on stdin/stdout): it reads `hello`, then one `batch` per minute, and answers each batch with exactly one `reply` carrying its orders. Python 3.13, standard library only — nothing to install.

## Files

- `main.py` — the bot (entrypoint)
- `LICENSE` — MIT
