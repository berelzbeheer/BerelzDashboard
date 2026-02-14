#!/bin/bash
# Berelz Analyzer - Auto-start Background Service

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$SCRIPT_DIR/dashboard.log"
PID_FILE="$SCRIPT_DIR/dashboard.pid"

case "$1" in
    start)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if ps -p $PID > /dev/null 2>&1; then
                echo "✅ Dashboard is already running (PID: $PID)"
                echo "   Access at: http://localhost:8080"
                exit 0
            fi
        fi

        echo "🚀 Starting Berelz XAUEUR Analyzer..."
        cd "$SCRIPT_DIR"
        nohup python3 server.py > "$LOG_FILE" 2>&1 &
        echo $! > "$PID_FILE"

        sleep 2

        if ps -p $(cat "$PID_FILE") > /dev/null 2>&1; then
            echo "✅ Dashboard started successfully!"
            echo "   PID: $(cat "$PID_FILE")"
            echo "   Access at: http://localhost:8080"
            echo "   Logs: $LOG_FILE"

            # Auto-open browser
            sleep 1
            open "http://localhost:8080" 2>/dev/null || true
        else
            echo "❌ Failed to start. Check logs: $LOG_FILE"
            exit 1
        fi
        ;;

    stop)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if ps -p $PID > /dev/null 2>&1; then
                echo "🛑 Stopping dashboard (PID: $PID)..."
                kill $PID
                rm -f "$PID_FILE"
                echo "✅ Dashboard stopped"
            else
                echo "⚠️  Dashboard not running"
                rm -f "$PID_FILE"
            fi
        else
            echo "⚠️  No PID file found"
        fi
        ;;

    restart)
        $0 stop
        sleep 2
        $0 start
        ;;

    status)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if ps -p $PID > /dev/null 2>&1; then
                echo "✅ Dashboard is running (PID: $PID)"
                echo "   Access at: http://localhost:8080"
            else
                echo "❌ Dashboard is not running (stale PID file)"
                rm -f "$PID_FILE"
            fi
        else
            echo "❌ Dashboard is not running"
        fi
        ;;

    logs)
        if [ -f "$LOG_FILE" ]; then
            tail -f "$LOG_FILE"
        else
            echo "⚠️  No log file found"
        fi
        ;;

    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "Commands:"
        echo "  start    - Start the dashboard in background"
        echo "  stop     - Stop the dashboard"
        echo "  restart  - Restart the dashboard"
        echo "  status   - Check if dashboard is running"
        echo "  logs     - View live logs"
        exit 1
        ;;
esac
