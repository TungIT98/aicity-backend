#!/usr/bin/env python3
"""
AI City - Health Check Script
Standalone health monitoring script for self-healing infrastructure
Can be run via cron or monitoring system
"""

import requests
import sys
import os
import json
import time
from datetime import datetime

BACKEND_URL = os.getenv("BACKEND_URL", "https://aicity-backend-deploy.vercel.app")
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_alert(message: str, severity: str = "WARNING"):
    """Send alert via configured channels"""
    timestamp = datetime.utcnow().isoformat()
    full_message = f"[{severity}] {timestamp}\n{message}"

    print(full_message, file=sys.stderr)

    # Slack
    if SLACK_WEBHOOK:
        try:
            requests.post(SLACK_WEBHOOK, json={
                "text": full_message,
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": f"AI City Alert - {severity}"}
                    },
                    {"type": "section", "text": {"type": "mrkdwn", "text": full_message}}
                ]
            }, timeout=5)
        except Exception as e:
            print(f"Slack alert failed: {e}", file=sys.stderr)

    # Telegram
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": full_message},
                timeout=5
            )
        except Exception as e:
            print(f"Telegram alert failed: {e}", file=sys.stderr)


def check_endpoint(url: str, timeout: int = 10) -> tuple[bool, dict]:
    """Check a single endpoint"""
    try:
        start = time.time()
        resp = requests.get(url, timeout=timeout)
        latency_ms = (time.time() - start) * 1000

        return True, {
            "status_code": resp.status_code,
            "latency_ms": round(latency_ms, 2),
            "success": resp.status_code < 500
        }
    except requests.exceptions.Timeout:
        return False, {"error": "timeout"}
    except requests.exceptions.ConnectionError:
        return False, {"error": "connection_refused"}
    except Exception as e:
        return False, {"error": str(e)}


def main():
    """Run health checks on all endpoints"""
    print(f"=== AI City Health Check - {datetime.utcnow().isoformat()} ===")

    endpoints = [
        ("/health", "basic"),
        ("/leads", "database"),
        ("/", "root"),
        ("/api/demo", "demo"),  # Requires POST, tested separately
    ]

    results = {}
    all_healthy = True

    for path, check_type in endpoints:
        url = f"{BACKEND_URL}{path}"
        print(f"\nChecking: {url}")

        healthy, details = check_endpoint(url)
        results[path] = details

        if healthy:
            print(f"  ✓ OK - Status: {details.get('status_code')}, Latency: {details.get('latency_ms')}ms")
        else:
            print(f"  ✗ FAIL - {details.get('error')}")
            all_healthy = False

    # Check response time thresholds
    for path, details in results.items():
        latency = details.get("latency_ms", 0)
        if latency > 2000:
            send_alert(f"Slow response on {path}: {latency}ms (> 2000ms threshold)")
        elif latency > 1000:
            print(f"WARNING: {path} is slow ({latency}ms)")

    # Summary
    print(f"\n=== Summary ===")
    if all_healthy:
        print("All checks passed ✓")
        return 0
    else:
        send_alert("Health check failed - one or more endpoints unreachable", "CRITICAL")
        return 2


if __name__ == "__main__":
    sys.exit(main())
