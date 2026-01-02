#!/usr/bin/env python3
"""
Router Restart Script
Monitors internet speed and automatically restarts FRITZ!Box router when speed is slow.
"""

import json
import logging
import os
import re
import subprocess
import threading
import weakref
from datetime import datetime
from pathlib import Path

from fritzconnection import FritzConnection


# Registry of active RouterRestartManager instances for metrics aggregation
_instances_lock = threading.RLock()
_active_instances = weakref.WeakSet()


def _register_instance(instance):
    """Register a RouterRestartManager instance for metrics tracking.
    
    Prevents duplicate registration of the same instance.
    """
    with _instances_lock:
        _active_instances.add(instance)


def _unregister_instance(instance):
    """Unregister a RouterRestartManager instance."""
    with _instances_lock:
        _active_instances.discard(instance)


def get_router_restart_metrics():
    """Get aggregated router restart metrics from all active instances.
    
    Returns:
        dict with restart_total, restart_last_timestamp, restart_failures_total,
        and router_id (if single router) or None (if multiple/none).
        Returns None if no instances are registered.
    """
    with _instances_lock:
        instances = list(_active_instances)
        if not instances:
            return None
        
        # Collect metrics from each instance while holding their individual locks
        total = 0
        failures = 0
        timestamps = []
        
        for inst in instances:
            with inst._metrics_lock:
                total += inst._restart_total
                failures += inst._restart_failures_total
                if inst._restart_last_timestamp is not None:
                    timestamps.append(inst._restart_last_timestamp)
        
        last_timestamp = max(timestamps) if timestamps else None
        
        # Include router identifier if single instance
        router_id = instances[0].fritzbox_ip if len(instances) == 1 else None
        
        return {
            "restart_total": total,
            "restart_last_timestamp": last_timestamp,
            "restart_failures_total": failures,
            "router_id": router_id,
        }


class RouterRestartManager:
    def __init__(self, config: dict):
        """Initialize the router restart manager with configuration.
        
        Args:
            config: The loaded configuration dictionary.
        """
        router_config = config["router_restart"]
        
        # Fritzbox settings
        self.fritzbox_ip = router_config["fritzbox"]["ip"]
        self.fritzbox_username = router_config["fritzbox"]["username"]
        self.onepassword_ref = router_config["fritzbox"]["onepassword_ref"]
        
        # Policy settings
        self.speed_threshold = router_config["policy"]["speed_threshold_mbps"]
        self.required_failures = router_config["policy"]["consecutive_failures"]
        self.time_window_start = datetime.strptime(
            router_config["policy"]["time_window_start"], "%H:%M"
        ).time()
        self.time_window_end = datetime.strptime(
            router_config["policy"]["time_window_end"], "%H:%M"
        ).time()
        
        # State file
        self.state_file = Path(router_config["state"]["state_file"]).expanduser()
        
        # Logging settings - nested under router_restart in config
        log_config = router_config.get("logging", {})
        self.logging_enabled = log_config.get("enabled", True)
        # Default to a user-writable location instead of /var/log
        default_log = Path.home() / ".local" / "log" / "router_restart.log"
        configured_log = log_config.get("log_file", str(default_log))
        # Expand ~ in path for user home directory without relying on Path (test mocking)
        self.log_file = os.path.expanduser(configured_log)
        
        # Validate 1Password reference format early to avoid unsafe inputs
        self._validate_onepassword_ref()
        
        # Instance-level metrics (thread-safe via _instances_lock in aggregation)
        self._restart_total = 0
        self._restart_last_timestamp = None
        self._restart_failures_total = 0
        self._metrics_lock = threading.Lock()
        
        self._setup_logging()
        self.state = self._load_state()
        
        # Track if this instance is registered (for close() idempotency)
        self._closed = False
        
        # Register this instance for metrics aggregation
        _register_instance(self)
    
    def close(self):
        """Unregister this instance from metrics aggregation.
        
        Should be called when the manager is no longer needed to prevent
        stale metrics and memory leaks. Safe to call multiple times.
        """
        if not self._closed:
            _unregister_instance(self)
            self._closed = True
    
    def __del__(self):
        """Ensure instance is unregistered when garbage collected."""
        self.close()
    
    def _setup_logging(self):
        """Setup logging based on configuration.
        
        Note: If logging.basicConfig() was already called (e.g., by speed_test.py),
        we add handlers directly to the root logger instead of using basicConfig.
        We check for existing handlers to avoid duplicating log lines on repeated init.
        """
        root_logger = logging.getLogger()
        
        if self.logging_enabled:
            # Ensure log directory exists
            log_path = Path(self.log_file)
            try:
                # Check if we already have a handler for this file
                target_path = os.path.abspath(self.log_file)
                existing_handlers = [
                    h for h in root_logger.handlers
                    if isinstance(h, logging.FileHandler) 
                    and os.path.abspath(getattr(h, "baseFilename", "")) == target_path
                ]
                
                if existing_handlers:
                    logging.debug(f"File handler for {self.log_file} already exists, skipping")
                else:
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    file_handler = logging.FileHandler(self.log_file)
                    file_handler.setFormatter(
                        logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
                    )
                    # Add file handler to root logger (works even if basicConfig was called)
                    root_logger.addHandler(file_handler)
                    logging.info(f"Router restart logging to file: {self.log_file}")
            except (OSError, PermissionError) as e:
                # Fall back to console-only logging if file logging fails
                logging.warning(f"Cannot create log file {self.log_file}: {e}. Using console only.")
            
            root_logger.setLevel(logging.INFO)
        else:
            root_logger.setLevel(logging.WARNING)
    
    def _get_default_state(self):
        """Return the default state dictionary."""
        return {
            "consecutive_failures": 0,
            "last_restart_time": None
        }
    
    def _load_state(self):
        """Load state from JSON file with fallback for corrupt data."""
        try:
            exists = self.state_file.exists()
        except AttributeError:
            exists = False
        
        if not isinstance(exists, bool) or not exists:
            return self._get_default_state()
        
        try:
            with open(self.state_file, "r") as f:
                state = json.load(f)
            
            # Validate required keys exist
            if not isinstance(state, dict):
                raise ValueError("State must be a dictionary")
            if "consecutive_failures" not in state:
                state["consecutive_failures"] = 0
            if "last_restart_time" not in state:
                state["last_restart_time"] = None
            
            return state
            
        except (json.JSONDecodeError, ValueError, IOError) as e:
            logging.warning(f"Failed to load state file ({e}), using defaults")
            return self._get_default_state()
    
    def _save_state(self):
        """Save state to JSON file."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2)
    
    def _get_fritzbox_password(self):
        """Retrieve FRITZ!Box password from 1Password."""
        try:
            result = subprocess.run(
                ["op", "read", self.onepassword_ref],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logging.error("Failed to retrieve password from 1Password (returncode=%s).", e.returncode)
            raise

    def _validate_onepassword_ref(self):
        """Validate the 1Password reference format to prevent unsafe inputs."""
        pattern = r"^op://[A-Za-z0-9 ._-]+/[A-Za-z0-9 ._-]+/[A-Za-z0-9 ._-]+$"
        if not re.fullmatch(pattern, self.onepassword_ref or ""):
            raise ValueError("Invalid 1Password reference format")
    
    def _is_within_time_window(self):
        """Check if current time is within the allowed restart window."""
        now = datetime.now().time()
        
        if self.time_window_start <= self.time_window_end:
            # Normal case: e.g., 02:00 to 04:00
            return self.time_window_start <= now <= self.time_window_end
        else:
            # Crosses midnight: e.g., 23:00 to 02:00
            return now >= self.time_window_start or now <= self.time_window_end
    
    def _restart_fritzbox(self):
        """Restart the FRITZ!Box router."""
        try:
            password = self._get_fritzbox_password()
            
            logging.info(f"Connecting to FRITZ!Box at {self.fritzbox_ip}...")
            fc = FritzConnection(
                address=self.fritzbox_ip,
                user=self.fritzbox_username if self.fritzbox_username else None,
                password=password
            )
            
            logging.info("Sending reboot command to FRITZ!Box...")
            fc.call_action("DeviceConfig1", "Reboot")
            
            logging.info("FRITZ!Box reboot initiated successfully")
            
            # Record successful restart in instance metrics
            with self._metrics_lock:
                self._restart_total += 1
                self._restart_last_timestamp = datetime.now().timestamp()
            
            return True
            
        except Exception as e:
            logging.error("Failed to restart FRITZ!Box (%s).", type(e).__name__)
            
            # Record failed restart attempt in instance metrics
            with self._metrics_lock:
                self._restart_failures_total += 1
            
            return False
    
    def check_and_restart(self, current_speed_mbps):
        """
        Check if router should be restarted based on current speed.
        
        Args:
            current_speed_mbps: Current download speed in Mbps
            
        Returns:
            bool: True if restart was triggered, False otherwise
        """
        # Check if speed is below threshold
        if current_speed_mbps < self.speed_threshold:
            self.state["consecutive_failures"] += 1
            logging.info(
                f"Speed {current_speed_mbps:.2f} Mbps is below threshold {self.speed_threshold} Mbps. "
                f"Consecutive failures: {self.state['consecutive_failures']}/{self.required_failures}"
            )
        else:
            # Speed is good, reset counter
            if self.state["consecutive_failures"] > 0:
                logging.info(
                    f"Speed {current_speed_mbps:.2f} Mbps is above threshold. "
                    f"Resetting failure counter."
                )
            self.state["consecutive_failures"] = 0
            self._save_state()
            return False
        
        # Check if we've reached the required number of consecutive failures
        if self.state["consecutive_failures"] >= self.required_failures:
            # Check if we're within the allowed time window
            if not self._is_within_time_window():
                logging.info(
                    "Restart conditions met, but outside allowed time window. "
                    f"Waiting for time window: {self.time_window_start} - {self.time_window_end}"
                )
                self._save_state()
                return False
            
            # All conditions met, trigger restart
            logging.warning(
                f"Triggering router restart after {self.state['consecutive_failures']} "
                f"consecutive failures (speed < {self.speed_threshold} Mbps)"
            )
            
            if self._restart_fritzbox():
                # Reset state after successful restart
                self.state["consecutive_failures"] = 0
                self.state["last_restart_time"] = datetime.now().isoformat()
                self._save_state()
                return True
            else:
                logging.error("Failed to restart router, will retry on next check")
                self._save_state()
                return False
        
        # Not enough failures yet
        self._save_state()
        return False
