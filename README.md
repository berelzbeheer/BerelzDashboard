# BerelzDashboard

Free real-time trading dashboard template for **BerelzBridge Pro** users.

Reads the JSON data exported by [BerelzBridge Pro](https://www.mql5.com/en/market) and displays a full multi-indicator analysis dashboard in your browser.

![BerelzDashboard](graphics/screenshots/BerelzDasboard%20Main.png)

## What you get

- **10 technical indicators** with weighted signal system (SMA, EMA, RSI, MACD, Bollinger Bands, Stochastic, ATR, ADX, Support/Resistance, Volume)
- **Live price feed** with bid/ask and spread
- **Signal confidence meter** (BUY / SELL / HOLD)
- **Price action pattern detection** (Engulfing, Doji, Hammer, Shooting Star)
- **News feed** from financial sources
- **Position size calculator** with risk management
- Auto-refreshes every 60 seconds

## Free vs Pro

| Feature | BerelzBridge Free | BerelzBridge Pro |
|---------|-------------------|------------------|
| Dashboard main page | Yes (limited data) | Yes (full data) |
| Multi-timeframe analysis | No (1 timeframe only) | Yes (all 9 timeframes) |
| Account & equity monitoring | No | Yes |
| Spread & daily stats | No | Yes |
| Position calculator (live) | No (manual input) | Yes (auto from account) |
| Bars for indicators | 50 | 500 (configurable) |

The dashboard works with the **Free version** but only the main page with basic price data is available. For the full experience (multi-timeframe analysis, account monitoring, position calculator with live data), **BerelzBridge Pro** is required.

**[Get BerelzBridge Pro on MQL5 Market](https://www.mql5.com/en/market)**

## Requirements

- **BerelzBridge Pro** or **BerelzBridge Free** running in MetaTrader 5
- Python 3.8+
- Any modern web browser
- **macOS**, **Windows** or **Linux**

## Quick Start

```bash
git clone https://github.com/berelzbeheer/BerelzDashboard.git
cd BerelzDashboard
python3 server.py
```

The dashboard opens at **http://localhost:8080**

macOS users can also run `./START.sh` for guided setup.

## How it works

```
MetaTrader 5 ──> BerelzBridge Pro ──> JSON file ──> server.py ──> Dashboard
                  (MQL5 Market)       (MQL5/Files/)   (localhost:8080)
```

1. **BerelzBridge** exports live market data to a JSON file
2. **server.py** reads the JSON and serves the dashboard + API
3. **BerelzDashboard.html** displays everything in a real-time web interface

## Installation

See [INSTALL.md](INSTALL.md) for detailed setup instructions for all platforms.

## File Structure

```
BerelzDashboard/
├── BerelzDashboard.html         # Main dashboard UI
├── server.py                    # Python server + data processing
├── START.sh                     # One-command launcher (macOS)
├── INSTALL.sh                   # Auto-start installer (macOS)
├── auto-start.sh                # Background service manager (macOS)
├── com.berelz.dashboard.plist   # macOS LaunchAgent config
├── index.html                   # Browser-based launcher
├── INSTALL.md                   # Installation guide
└── graphics/                    # Screenshots
```

## Configuration

The server auto-detects your MT5 data files at:

| Platform | Path |
|----------|------|
| **macOS** | `~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files/` |
| **Windows** | `C:\Users\YOU\AppData\Roaming\MetaQuotes\Terminal\YOUR_ID\MQL5\Files\` |
| **Linux** | `~/.wine/drive_c/Program Files/MetaTrader 5/MQL5/Files/` |

If no BerelzBridge data is found, the dashboard runs with sample data so you can preview it.

## Service Management (macOS only)

```bash
./auto-start.sh start     # Start in background
./auto-start.sh stop      # Stop
./auto-start.sh restart   # Restart
./auto-start.sh status    # Check status
./auto-start.sh logs      # View live logs
```

## Disclaimer

This dashboard is a **free community template** provided as-is. It is **not officially supported** by Berelz Capital Engineering. No warranty, no guaranteed updates, no support obligations. Use at your own risk.

For support with **BerelzBridge Pro** (the MT5 indicator), use the [MQL5 Market support page](https://www.mql5.com/en/market).

---

(c) 2025 Berelz Capital Engineering
