#!/bin/bash
# BerelzDashboard - Auto-Start Installer

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_FILE="com.berelz.dashboard.plist"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  BerelzDashboard - Auto-Start Installer         ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Make scripts executable
chmod +x "$SCRIPT_DIR/auto-start.sh"
chmod +x "$SCRIPT_DIR/START.sh"

# Create LaunchAgents directory if it doesn't exist
mkdir -p "$LAUNCH_AGENTS_DIR"

# Copy plist to LaunchAgents
echo "📦 Installing auto-start service..."
cp "$SCRIPT_DIR/$PLIST_FILE" "$LAUNCH_AGENTS_DIR/"

# Load the service
echo "🚀 Loading service..."
launchctl unload "$LAUNCH_AGENTS_DIR/$PLIST_FILE" 2>/dev/null
launchctl load "$LAUNCH_AGENTS_DIR/$PLIST_FILE"

# Wait a moment
sleep 2

# Check if running
if curl -s http://localhost:8080/api/data > /dev/null 2>&1; then
    echo ""
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║  ✅ AUTO-START INSTALLED & RUNNING!                     ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo ""
    echo "✨ Dashboard will now start automatically:"
    echo "   • At system boot"
    echo "   • At login"
    echo "   • After crashes (auto-restart)"
    echo ""
    echo "📊 Access dashboard at: http://localhost:8080"
    echo ""
    echo "🛠️  Manage service:"
    echo "   ./auto-start.sh status    - Check status"
    echo "   ./auto-start.sh stop      - Stop service"
    echo "   ./auto-start.sh restart   - Restart service"
    echo "   ./auto-start.sh logs      - View logs"
    echo ""
    echo "🗑️  To uninstall:"
    echo "   launchctl unload ~/Library/LaunchAgents/$PLIST_FILE"
    echo "   rm ~/Library/LaunchAgents/$PLIST_FILE"
    echo ""

    # Auto-open browser
    open "http://localhost:8080" 2>/dev/null || true
else
    echo ""
    echo "⚠️  Service installed but not responding yet."
    echo "   Check logs: $SCRIPT_DIR/dashboard.log"
    echo "   Or manually start: ./auto-start.sh start"
fi
