# Gold Desk

Paper-trading bot for gold. One decision per day: be long GLD, or be in cash. Python, free tools, fake money only (Alpaca paper account).

Strategy: 3-month momentum. If gold (GLD) is higher than it was 3 months ago, hold it. If not, go to cash. Never shorts, never uses leverage.

Safety rails, always on:
- Max 1% of capital at risk per trade ($100 on a $10,000 account)
- Volatility stop: 2 ATR below entry on every position
- Daily loss limit: halts if the account drops 2% in one day
- Kill switch: 5% below peak equity, the bot flattens and stops until you delete KILL_SWITCH.txt
- DRY_RUN on by default: prints decisions, sends nothing, until you turn it off

Backtest: monthly spot-gold dataset 1833 to Sept 2026 (datasets/gold-prices on GitHub), in-sample through 2022, out-of-sample 2023 to Sept 2026: +158%, Sharpe 2.15, max drawdown -6%, desk score 23/25. Caveats: monthly data, only 2 out-of-sample trades, and past performance guarantees nothing. Paper trading and a learning tool, not financial advice.

Setup (no coding experience needed):
1. Install Python 3.11+ from python.org
2. Terminal: pip install pandas requests
3. Free account at alpaca.markets (starts in paper mode). Generate a paper API key and secret
4. Set environment variables ALPACA_KEY and ALPACA_SECRET
5. Run: python gold_momentum_bot.py (DRY_RUN on = just prints today's decision)
6. Run once a day after the US market close (Task Scheduler on Windows, cron on Mac/Linux, or manually)
7. After watching it a while: set DRY_RUN = False. Still paper only.

To stop the bot: create an empty file named KILL_SWITCH.txt next to the script. To resume: delete it.

A proactive-module experiment: a bot that watches, decides, and acts daily while you sleep.
