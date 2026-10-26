"""
gold_momentum_bot.py - Gold Desk v0.1
Strategy: 3-month momentum on gold, traded as GLD (Alpaca cannot trade spot gold).
PAPER TRADING ONLY. Never connect a real-money account. Not financial advice.

Runs once per day, best right after the US market close (4-5pm ET).
It decides one thing: be long GLD, or be in cash.
"""

import io
import json
import os
import urllib.request

import pandas as pd
import requests

# ------------- CONFIG (the only part you ever edit) -------------
DRY_RUN = True          # True: prints the decision, sends NO orders. Flip to False only when it all works.
CAPITAL = 10_000.00     # paper capital, USD
RISK_PER_TRADE = 0.01   # max 1% of capital at risk per trade
MOMENTUM_WINDOW = 63    # trading days lookback (~3 months)
ATR_WINDOW = 14         # for the volatility stop
ATR_STOP_MULT = 2.0     # stop sits 2 ATR below entry
DAILY_LOSS_LIMIT = 0.02 # halt for the day if equity drops 2%
KILL_DRAWDOWN = 0.05    # kill switch: 5% below peak equity
SYMBOL = "GLD"

ALPACA_KEY = os.environ.get("ALPACA_KEY", "")
ALPACA_SECRET = os.environ.get("ALPACA_SECRET", "")
PAPER_API = "https://paper-api.alpaca.markets"

KILL_FILE = "KILL_SWITCH.txt"
LOG_FILE = "gold_desk_log.txt"
STATE_FILE = "gold_desk_state.json"


def log(msg):
    line = f"{pd.Timestamp.now():%Y-%m-%d %H:%M} {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def fetch_gld():
    """Daily GLD prices from stooq (free, no key needed)."""
    url = "https://stooq.com/q/d/l/?s=gld.us&i=d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as r:
        df = pd.read_csv(io.StringIO(r.read().decode()))
    df["Date"] = pd.to_datetime(df["Date"])
    return df.set_index("Date").dropna()


def atr(df):
    """Average True Range: how far GLD usually moves in a day."""
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(ATR_WINDOW).mean().iloc[-1]


def momentum(closes):
    """The whole strategy in one line: is gold higher than 3 months ago?"""
    if len(closes) < MOMENTUM_WINDOW + 1:
        raise SystemExit(f"Need {MOMENTUM_WINDOW + 1} days of data, got {len(closes)}")
    return closes.iloc[-1] > closes.iloc[-1 - MOMENTUM_WINDOW]


# --- Alpaca paper API helpers ---
def _headers():
    return {"APCA-API-KEY-ID": ALPACA_KEY, "APCA-API-SECRET-KEY": ALPACA_SECRET}


def account_equity():
    r = requests.get(f"{PAPER_API}/v2/account", headers=_headers())
    r.raise_for_status()
    return float(r.json()["equity"])


def position_shares():
    r = requests.get(f"{PAPER_API}/v2/positions/{SYMBOL}", headers=_headers())
    if r.status_code == 404:
        return 0
    r.raise_for_status()
    return int(float(r.json()["qty"]))


def submit_order(side, qty):
    r = requests.post(f"{PAPER_API}/v2/orders", headers=_headers(),
                      json={"symbol": SYMBOL, "qty": qty, "side": side,
                            "type": "market", "time_in_force": "day"})
    r.raise_for_status()
    return r.json()


# --- state on disk, so the bot remembers between runs ---
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"peak_equity": CAPITAL, "last_equity": CAPITAL, "stop": None}


def save_state(s):
    with open(STATE_FILE, "w") as f:
        json.dump(s, f, indent=2)


def main():
    if os.path.exists(KILL_FILE):
        raise SystemExit("KILL SWITCH is present. Not trading. "
                         "Check the account, then delete KILL_SWITCH.txt to resume.")

    df = fetch_gld()
    price = float(df["Close"].iloc[-1])
    up = momentum(df["Close"])
    a = float(atr(df))
    log(f"GLD close {price:.2f} | ATR {a:.2f} | 3-month momentum: {'UP' if up else 'DOWN'}")

    state = load_state()
    equity = CAPITAL if DRY_RUN else account_equity()

    # safety: daily loss limit
    if equity < state["last_equity"] * (1 - DAILY_LOSS_LIMIT):
        log(f"HALT: daily loss limit hit ({equity:.0f} vs {state['last_equity']:.0f} yesterday).")
        state["last_equity"] = equity
        save_state(state)
        return

    # safety: kill switch on drawdown from peak
    peak = max(state["peak_equity"], equity)
    if equity < peak * (1 - KILL_DRAWDOWN):
        with open(KILL_FILE, "w") as f:
            f.write("kill switch tripped: drawdown from peak")
        log(f"KILL: equity {equity:.0f} is more than {KILL_DRAWDOWN:.0%} below peak {peak:.0f}.")
        if not DRY_RUN:
            held = position_shares()
            if held:
                submit_order("sell", held)
                log(f"Sold {held} {SYMBOL} to flatten.")
        return

    state["peak_equity"], state["last_equity"] = peak, equity

    held = 0 if DRY_RUN else position_shares()

    # NOTE: the stop is checked once a day when the bot runs.
    # v0.2 should place a real stop order at the broker instead.
    if up and held == 0:
        stop = round(price - ATR_STOP_MULT * a, 2)
        risk_per_share = max(price - stop, 0.01)
        qty = int((CAPITAL * RISK_PER_TRADE) / risk_per_share)
        qty = min(qty, int(CAPITAL / price))  # never use leverage
        log(f"SIGNAL UP -> BUY {qty} {SYMBOL} at ~{price:.2f}, stop {stop:.2f} "
            f"(risk about ${qty * risk_per_share:.0f})")
        if not DRY_RUN:
            submit_order("buy", qty)
            state["stop"] = stop
    elif not up and held > 0:
        log(f"SIGNAL DOWN -> SELL {held} {SYMBOL} (momentum flipped).")
        if not DRY_RUN:
            submit_order("sell", held)
            state["stop"] = None
    elif up and held > 0:
        stop = state.get("stop")
        if stop and price <= stop:
            log(f"STOP HIT at {price:.2f} (stop {stop}) -> SELL {held} {SYMBOL}.")
            if not DRY_RUN:
                submit_order("sell", held)
                state["stop"] = None
        else:
            log(f"Holding {held} {SYMBOL}, stop at {stop}.")
    else:
        log("Signal down, no position -> staying in cash.")

    save_state(state)


if __name__ == "__main__":
    main()
