#!/usr/bin/env python3
"""
AI City - Self-Healing Infrastructure
Monitors services and auto-restarts on failure
"""

import os
import sys
import time
import subprocess
import signal
import requests
import logging
from datetime import datetime
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/aicity-selfheal.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
BACKEND_URL = os.getenv("BACKEND_URL", "https://aicity-backend-deploy.vercel.app")
HEALTH_CHECK_INTERVAL = int(os.getenv("HEALTH_CHECK_INTERVAL", "60"))  # seconds
MAX_RESTART_ATTEMPTS = int(os.getenv("MAX_RESTART_ATTEMPTS", "3"))
RESTART_COOLDOWN = int(os.getenv("RESTART_COOLDOWN", "300"))  # 5 minutes
DEAD_PROCESS_THRESHOLD = int(os.getenv("DEAD_PROCESS_THRESHOLD", "3"))

# For self-hosted deployments
PROCESS_NAME = os.getenv("PROCESS_NAME", "uvicorn")
APP_DIR = os.getenv("APP_DIR", "/app")
RESTART_SCRIPT = os.getenv("RESTART_SCRIPT", "/app/restart.sh")


class SelfHealingMonitor:
    def __init__(self):
        self.restart_count = 0
        self.last_restart_time = 0
        self.health_history = []

    def check_health(self) -> bool:
        """Check if backend is healthy"""
        try:
            resp = requests.get(f"{BACKEND_URL}/health", timeout=10)
            is_healthy = resp.status_code == 200

            # Track health history for pattern detection
            self.health_history.append(is_healthy)
            if len(self.health_history) > 10:
                self.health_history.pop(0)

            return is_healthy
        except requests.exceptions.RequestException as e:
            logger.error(f"Health check failed: {e}")
            self.health_history.append(False)
            if len(self.health_history) > 10:
                self.health_history.pop(0)
            return False

    def check_dead_process(self) -> bool:
        """Check if the main process is running"""
        try:
            result = subprocess.run(
                ["pgrep", "-f", PROCESS_NAME],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return True  # Assume running if we can't check

    def should_restart(self) -> tuple[bool, str]:
        """Determine if we should restart the service"""
        now = time.time()

        # Check restart cooldown
        if now - self.last_restart_time < RESTART_COOLDOWN:
            logger.warning(f"In cooldown period, skipping restart")
            return False, "cooldown"

        # Check restart count
        if self.restart_count >= MAX_RESTART_ATTEMPTS:
            logger.error(f"Max restart attempts ({MAX_RESTART_ATTEMPTS}) reached")
            return False, "max_attempts"

        # Check health pattern - 3 consecutive failures
        if len(self.health_history) >= 3:
            if all(not h for h in self.health_history[-3:]):
                return True, "consecutive_failures"

        return True, "health_check_failed"

    def restart_service(self, reason: str):
        """Restart the service"""
        logger.info(f"Restarting service: {reason}")
        self.restart_count += 1
        self.last_restart_time = time.time()
        self.health_history.clear()

        try:
            # Try graceful restart first
            subprocess.run(["pkill", "-f", PROCESS_NAME, "-SIGTERM"], timeout=10)

            # Wait for graceful shutdown
            time.sleep(5)

            # Force kill if still running
            subprocess.run(["pkill", "-f", PROCESS_NAME, "-SIGKILL"], timeout=5)

            # Start new process
            subprocess.Popen(
                ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"],
                cwd=APP_DIR,
                stdout=open("/var/log/aicity-stdout.log", "a"),
                stderr=open("/var/log/aicity-stderr.log", "a")
            )

            logger.info(f"Service restarted successfully (attempt {self.restart_count})")

        except subprocess.TimeoutExpired:
            logger.error("Graceful shutdown timeout, force killing")
            subprocess.run(["pkill", "-9", "-f", PROCESS_NAME])
        except Exception as e:
            logger.error(f"Restart failed: {e}")

    def run(self):
        """Main monitoring loop"""
        logger.info("Starting AI City Self-Healing Monitor")
        logger.info(f"Health check interval: {HEALTH_CHECK_INTERVAL}s")
        logger.info(f"Max restart attempts: {MAX_RESTART_ATTEMPTS}")

        consecutive_failures = 0

        while True:
            try:
                # Check dead process (for self-hosted)
                if not self.check_dead_process():
                    logger.warning("Dead process detected, restarting")
                    self.restart_service("dead_process")
                    continue

                # Check health
                is_healthy = self.check_health()

                if is_healthy:
                    consecutive_failures = 0
                    logger.debug("Health check OK")
                else:
                    consecutive_failures += 1
                    logger.warning(f"Unhealthy (consecutive failures: {consecutive_failures})")

                    if consecutive_failures >= DEAD_PROCESS_THRESHOLD:
                        should_restart, reason = self.should_restart()
                        if should_restart:
                            self.restart_service(reason)
                            consecutive_failures = 0

            except KeyboardInterrupt:
                logger.info("Shutting down monitor")
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}")

            time.sleep(HEALTH_CHECK_INTERVAL)


if __name__ == "__main__":
    monitor = SelfHealingMonitor()
    monitor.run()
