# BerelzDashboard

Free real-time trading dashboard template for **BerelzBridge Pro** users.

Reads the JSON data exported by [BerelzBridge Pro](https://www.mql5.com/en/market) and displays a full multi-indicator analysis dashboard in your browser.

## What you get

- **10 technical indicators** with weighted signal system (SMA, EMA, RSI, MACD, Bollinger Bands, Stochastic, ATR, ADX, Support/Resistance, Volume)
- **Live price feed** with bid/ask and spread
- **Signal confidence meter** (BUY / SELL / HOLD)
- **Price action pattern detection** (Engulfing, Doji, Hammer, Shooting Star)
- **News feed** from financial sources
- **Position size calculator** with risk management
- Auto-refreshes every 60 seconds

## Requirements

- **BerelzBridge Pro** indicator running in MetaTrader 5 ([Get it on MQL5 Market](https://www.mql5.com/en/market))
- Python 3.8+
- Any modern web browser

## Quick Start

```bash
git clone https://github.com/berelzbeheer/BerelzDashboard.git
cd BerelzDashboard
./START.sh
```

The dashboard opens automatically at **http://localhost:8080**

## How it works

```
MetaTrader 5 ──► BerelzBridge Pro ──► JSON file ──► server.py ──► Dashboard
                  (MQL5 Market)       (MQL5/Files/)   (localhost:8080)
```

1. **BerelzBridge Pro** exports live market data to a JSON file every 2 seconds
2. **server.py** reads the JSON and serves the dashboard + API
3. **BerelzDashboard.html** displays everything in a real-time web interface

## Start Options

| Method | Command | Description |
|--------|---------|-------------|
| Foreground | `./START.sh` → choose 1 | Run in terminal, Ctrl+C to stop |
| Background | `./START.sh` → choose 2 | Runs as background process |
| Auto-start | `./START.sh` → choose 3 | Starts automatically at boot (macOS) |

## File Structure

```
BerelzDashboard/
├── BerelzDashboard.html    # Main dashboard UI
├── server.py              # Python server + data processing
├── MT5_LiveExport.mq5     # Optional: standalone MT5 data exporter
├── START.sh               # One-command launcher
├── INSTALL.sh             # Auto-start installer (macOS)
├── auto-start.sh          # Background service manager
├── com.berelz.dashboard.plist  # macOS LaunchAgent config
├── index.html             # Browser-based launcher
└── graphics/              # Logos and assets
```

## Configuration

The server auto-detects your MT5 data files at:

- **macOS**: `~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files/`
- **Windows**: `C:\Users\YOU\AppData\Roaming\MetaQuotes\Terminal\YOUR_ID\MQL5\Files\`

If no BerelzBridge Pro data is found, the dashboard runs with sample data so you can preview it.

## Service Management (macOS)

```bash
./auto-start.sh start     # Start in background
./auto-start.sh stop      # Stop
./auto-start.sh restart   # Restart
./auto-start.sh status    # Check status
./auto-start.sh logs      # View live logs
```

## Get BerelzBridge Pro

This dashboard is designed to work with **BerelzBridge Pro**, a MetaTrader 5 indicator that exports live market data (9 timeframes, account info, spread, daily stats) to a clean JSON file.

**[Get BerelzBridge Pro on MQL5 Market](https://www.mql5.com/en/market)**

---

(c) 2025 Berelz Capital Engineering
