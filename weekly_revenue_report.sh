#!/bin/bash
# Weekly Revenue Report Generator
# Runs every Friday at 9 AM to generate revenue report
# Add to crontab: 0 9 * * 5 /path/to/weekly_revenue_report.sh

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR"
LOG_FILE="$BACKEND_DIR/logs/revenue_report.log"

# Create logs directory if not exists
mkdir -p "$BACKEND_DIR/logs"

# Function to log
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "Starting weekly revenue report generation..."

# Set Python path
export PYTHONPATH="$BACKEND_DIR:$PYTHONPATH"

# Set database config
export DB_HOST="${DB_HOST:-localhost}"
export DB_PORT="${DB_PORT:-5433}"
export DB_NAME="${DB_NAME:-promptforge}"
export DB_USER="${DB_USER:-promptforge}"
export DB_PASSWORD="${DB_PASSWORD:-promptforge123}"

# Run the revenue report generator
cd "$BACKEND_DIR"
python3 -c "
import sys
sys.path.insert(0, '$BACKEND_DIR')
from revenue_report import generate_weekly_report, get_db_connection
import json
import datetime

conn = get_db_connection()
try:
    report = generate_weekly_report(conn)
    print(json.dumps(report, indent=2))
    conn.close()
    sys.exit(0)
except Exception as e:
    print(f'Error: {e}')
    conn.close()
    sys.exit(1)
" >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    log "Weekly revenue report generated successfully"
else
    log "ERROR: Failed to generate weekly revenue report"
    exit 1
fi

log "Weekly revenue report job completed"