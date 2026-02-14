# BerelzDashboard - Installation Guide

## Prerequisites

1. **BerelzBridge Pro** running in MetaTrader 5 ([Get it on MQL5 Market](https://www.mql5.com/en/market))
2. **Python 3.8+** installed
3. **MetaTrader 5** with at least one chart open

## Step 1: Download

```bash
git clone https://github.com/berelzbeheer/BerelzDashboard.git
cd BerelzDashboard
```

Or download as ZIP from the [releases page](https://github.com/berelzbeheer/BerelzDashboard/releases).

## Step 2: Install BerelzBridge Pro in MT5

1. Purchase **BerelzBridge Pro** from the [MQL5 Market](https://www.mql5.com/en/market)
2. It installs automatically in MT5: Navigator > Indicators > Market
3. Drag **BerelzBridge Pro** onto any chart
4. Enable the timeframes you need, click OK
5. The JSON file appears in `MQL5/Files/` (e.g. `xaueur_stream.json`)

## Step 3: Start the Dashboard

```bash
./START.sh
```

Choose option 1 (foreground), 2 (background) or 3 (auto-start at boot).

The dashboard opens at **http://localhost:8080**

## Where is my MT5 data?

The server auto-detects your MT5 files at:

| Platform | Path |
|----------|------|
| **macOS** | `~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files/` |
| **Windows** | `C:\Users\YOU\AppData\Roaming\MetaQuotes\Terminal\YOUR_ID\MQL5\Files\` |
| **VPS** | Same as Windows, check your terminal ID in MT5 Help > About |

## Auto-Start at Boot (macOS)

```bash
./INSTALL.sh
```

This installs a LaunchAgent that starts the dashboard automatically when you log in.

To uninstall:
```bash
launchctl unload ~/Library/LaunchAgents/com.berelz.dashboard.plist
rm ~/Library/LaunchAgents/com.berelz.dashboard.plist
```

## Service Management

```bash
./auto-start.sh start     # Start in background
./auto-start.sh stop      # Stop
./auto-start.sh restart   # Restart
./auto-start.sh status    # Check if running
./auto-start.sh logs      # View live logs
```

## No Data Yet?

If BerelzBridge Pro is not running, the dashboard shows sample data so you can preview all features. Once BerelzBridge Pro starts exporting JSON, the dashboard picks it up automatically.

## Support

- **BerelzBridge Pro**: [MQL5 Market Support](https://www.mql5.com/en/market)
- **Dashboard issues**: [GitHub Issues](https://github.com/berelzbeheer/BerelzDashboard/issues)

---

(c) 2025 Berelz Capital Engineering
