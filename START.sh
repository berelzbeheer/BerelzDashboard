#!/bin/bash
# Berelz Analyzer - Quick Start

cd "$(dirname "$0")"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  🚀 Berelz XAUEUR Analyzer - Quick Start               ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Check if already running
if [ -f "dashboard.pid" ]; then
    PID=$(cat "dashboard.pid")
    if ps -p $PID > /dev/null 2>&1; then
        echo "✅ Dashboard is already running!"
        echo "   PID: $PID"
        echo "   Access at: http://localhost:8080"
        echo ""
        open "http://localhost:8080" 2>/dev/null || true
        exit 0
    fi
fi

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed"
    echo "   Install it with: brew install python3"
    exit 1
fi

echo "🔍 Choose startup method:"
echo ""
echo "  1) Quick Start (manual, foreground)"
echo "  2) Background Service (keeps running)"
echo "  3) Install Auto-Start (starts at boot)"
echo ""
read -p "Enter choice [1-3]: " choice

case $choice in
    1)
        echo ""
        echo "🚀 Starting dashboard in foreground..."
        echo "   Press Ctrl+C to stop"
        echo ""
        sleep 1
        python3 server.py
        ;;
    2)
        echo ""
        ./auto-start.sh start
        ;;
    3)
        echo ""
        ./INSTALL.sh
        ;;
    *)
        echo ""
        echo "❌ Invalid choice. Starting in foreground mode..."
        echo ""
        sleep 1
        python3 server.py
        ;;
esac
