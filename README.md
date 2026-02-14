# BerelzDashboard

Free real-time trading dashboard for **BerelzBridge Pro** users.

Reads the JSON data exported by [BerelzBridge Pro](https://www.mql5.com/en/market) and displays a full multi-indicator analysis dashboard in your browser. No coding required.

![BerelzDashboard](graphics/screenshots/BerelzDasboard%20Main.png)

---

## For Traders

### What you get

- Live price feed with bid/ask and spread
- Signal confidence meter (BUY / SELL / HOLD) based on 10 technical indicators
- Price action pattern detection (Engulfing, Doji, Hammer, Shooting Star)
- News feed from financial sources
- Position size calculator with risk management
- Auto-refreshes every 60 seconds
- Works on **macOS**, **Windows** and **Linux**

### Setup in 3 steps

**Step 1** — Download this dashboard:
```bash
git clone https://github.com/berelzbeheer/BerelzDashboard.git
```
Or [download as ZIP](https://github.com/berelzbeheer/BerelzDashboard/archive/refs/heads/main.zip) and unzip.

**Step 2** — Make sure **BerelzBridge Pro** is running on a chart in MetaTrader 5.
Don't have it yet? [Get it on MQL5 Market](https://www.mql5.com/en/market)

**Step 3** — Start the dashboard:
```bash
cd BerelzDashboard
python3 server.py
```
Open **http://localhost:8080** in your browser. That's it.

macOS users can also run `./START.sh` for guided setup with auto-start option.

See [INSTALL.md](INSTALL.md) for detailed instructions and troubleshooting.

### Free vs Pro

| Feature | BerelzBridge Free | BerelzBridge Pro |
|---------|-------------------|------------------|
| Dashboard main page | Yes (limited data) | Yes (full data) |
| Multi-timeframe analysis | No (1 timeframe) | Yes (all 9 timeframes) |
| Account & equity monitoring | No | Yes |
| Spread & daily stats | No | Yes |
| Position calculator (live) | Manual input only | Auto from account data |
| Bars for indicators | 50 | 500 (configurable) |

The dashboard works with the **Free version** but only the main page with basic price data is available. For the full experience, **BerelzBridge Pro** is required.

**[Get BerelzBridge Pro on MQL5 Market](https://www.mql5.com/en/market)**

---

## For Developers

The dashboard is open source. Fork it, extend it, build your own tools on top of it.

### Architecture

```
MetaTrader 5 ──> BerelzBridge ──> JSON file ──> server.py ──> HTTP API ──> Dashboard
                  (MQL5 Market)   (MQL5/Files/)   (Python)     (REST)      (HTML/JS)
```

### API Endpoints

The server exposes these endpoints on `http://localhost:8080`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/data` | GET | Full market data: price, bars, indicators, signals, account info |
| `/api/news` | GET | Gold/forex news from multiple sources with sentiment |
| `/api/cot` | GET | CFTC Commitment of Traders data |

All endpoints return JSON.

### JSON Structure (BerelzBridge Pro output)

The JSON file written by BerelzBridge Pro to `MQL5/Files/` has this structure:

```json
{
  "symbol": "XAUEUR",
  "updated": "2025-06-15 14:30:00",
  "version": "pro",
  "bid": 2650.50,
  "ask": 2651.20,
  "spread": 7.0,
  "daily_high": 2668.40,
  "daily_low": 2635.10,
  "daily_open": 2642.80,
  "bars_m5": [
    {"time": "2025-06-15 10:00:00", "o": 2635.40, "h": 2637.10, "l": 2634.90, "c": 2636.80, "v": 892}
  ],
  "bars_h1": [ ... ],
  "bars_d1": [ ... ],
  "account": {
    "balance": 10250.00,
    "equity": 10180.50,
    "margin": 850.00,
    "free_margin": 9330.50,
    "profit": -69.50,
    "leverage": 500,
    "currency": "EUR"
  },
  "broker": {
    "name": "Your Broker",
    "server": "Broker-Server"
  }
}
```

### File Structure

```
BerelzDashboard/
├── BerelzDashboard.html         # Main dashboard UI (single-page app)
├── server.py                    # Python HTTP server + data processing
├── START.sh                     # Launcher (macOS)
├── INSTALL.sh                   # Auto-start installer (macOS)
├── auto-start.sh                # Background service manager (macOS)
├── com.berelz.dashboard.plist   # macOS LaunchAgent config
├── index.html                   # Browser-based launcher
├── INSTALL.md                   # Installation guide
└── graphics/                    # Screenshots
```

### How to extend

- **Add a new dashboard page**: edit `BerelzDashboard.html`, add a new `<section>` and nav item
- **Add a new API endpoint**: edit `server.py`, add a handler in the request handler class
- **Read BerelzBridge data directly**: parse the JSON file from `MQL5/Files/` with any language
- **Build a completely different frontend**: use `/api/data` as your data source

### MT5 data file locations

| Platform | Path |
|----------|------|
| **macOS** | `~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files/` |
| **Windows** | `C:\Users\YOU\AppData\Roaming\MetaQuotes\Terminal\YOUR_ID\MQL5\Files\` |
| **Linux** | `~/.wine/drive_c/Program Files/MetaTrader 5/MQL5/Files/` |

---

## Disclaimer

This dashboard is a **free community template** provided as-is. It is **not officially supported** by Berelz Capital Engineering. No warranty, no guaranteed updates, no support obligations. Use at your own risk.

For support with **BerelzBridge Pro** (the MT5 indicator), use the [MQL5 Market support page](https://www.mql5.com/en/market).

---

(c) 2025 Berelz Capital Engineering
