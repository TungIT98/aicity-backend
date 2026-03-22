#!/bin/bash
# AI City - Uptime Monitoring Script
# Run via cron: */5 * * * * /app/scripts/uptime_monitor.sh

set -euo pipefail

# Configuration
BACKEND_URL="${BACKEND_URL:-https://aicity-backend-deploy.vercel.app}"
FRONTEND_URL="${FRONTEND_URL:-https://ai-city-booking.vercel.app}"
LOG_FILE="/var/log/aicity-uptime.log"
ALERT_THRESHOLD=3
SLACK_WEBHOOK="${SLACK_WEBHOOK_URL:-}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

alert() {
    local message="$1"
    local severity="${2:-WARNING}"

    log "${RED}[${severity}]${NC} $message"

    if [[ -n "$SLACK_WEBHOOK" ]]; then
        curl -s -X POST "$SLACK_WEBHOOK" \
            -H 'Content-Type: application/json' \
            -d "{\"text\":\"[AI City $severity] $message\"}" \
            > /dev/null 2>&1 || true
    fi
}

check_endpoint() {
    local url="$1"
    local name="$2"
    local timeout="${3:-10}"

    local start=$(date +%s%3N)
    local http_code=$(curl -s -o /dev/null -w "%{http_code}" \
        --max-time "$timeout" \
        --connect-timeout 5 \
        "$url" 2>/dev/null || echo "000")
    local end=$(date +%s%3N)
    local latency=$((end - start))

    if [[ "$http_code" == "200" ]]; then
        echo "OK|$latency"
        return 0
    elif [[ "$http_code" == "000" ]]; then
        echo "DOWN|0"
        return 2
    else
        echo "DEGRADED|$latency|$http_code"
        return 1
    fi
}

# Main monitoring loop
log "=== Starting Uptime Check ==="

declare -A services
services["backend"]="$BACKEND_URL"
services["frontend"]="$FRONTEND_URL"
services["health"]="$BACKEND_URL/health"
services["api-docs"]="$BACKEND_URL/api/docs"

declare -A failure_count
overall_status=0

for name in "${!services[@]}"; do
    url="${services[$name]}"
    log "Checking $name: $url"

    result=$(check_endpoint "$url" "$name")
    IFS='|' read -r status latency http_code <<< "$result"

    case $status in
        OK)
            log "  ${GREEN}✓${NC} $name - ${latency}ms"
            unset failure_count[$name]
            ;;
        DEGRADED)
            log "  ${YELLOW}⚠${NC} $name - ${latency}ms (HTTP $http_code)"
            failure_count[$name]=$((failure_count[$name]+1))
            if [[ ${failure_count[$name]} -ge $ALERT_THRESHOLD ]]; then
                alert "$name responding with HTTP $http_code (${latency}ms)" "WARNING"
            fi
            overall_status=1
            ;;
        DOWN)
            log "  ${RED}✗${NC} $name - DOWN"
            failure_count[$name]=$((failure_count[$name]+1))
            if [[ ${failure_count[$name]} -ge $ALERT_THRESHOLD ]]; then
                alert "CRITICAL: $name is DOWN!" "CRITICAL"
            fi
            overall_status=2
            ;;
    esac
done

# Check for SLA compliance
log "Checking SLA metrics..."

# Get today's uptime from API
if uptime_data=$(curl -s "$BACKEND_URL/monitoring/stats" 2>/dev/null); then
    error_rate=$(echo "$uptime_data" | grep -o '"error_rate":[0-9.]*' | cut -d: -f2 || echo "0")
    avg_latency=$(echo "$uptime_data" | grep -o '"avg_latency_ms":[0-9.]*' | cut -d: -f2 || echo "0")

    if (( $(echo "$error_rate > 0.1" | bc -l) )); then
        alert "Error rate above SLA threshold: $error_rate%" "WARNING"
    fi

    if (( $(echo "$avg_latency > 1000" | bc -l) )); then
        alert "High latency detected: ${avg_latency}ms" "WARNING"
    fi
fi

log "=== Uptime Check Complete ==="

exit $overall_status
