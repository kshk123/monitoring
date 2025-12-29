"""Prometheus server management for the speed monitoring service."""

import subprocess
import atexit
import logging
import sys
from pathlib import Path


class PrometheusManager:
    """Manages the lifecycle of a Prometheus server instance."""
    
    def __init__(self, config: dict, project_root: Path = None):
        """Initialize the Prometheus manager.
        
        Args:
            config: The prometheus section of the config file.
            project_root: Root directory of the project (for resolving relative paths).
        """
        self.project_root = project_root or Path(__file__).parent.parent
        self._process = None
        
        # Parse config values
        self.binary = config.get("binary_path") or "prometheus"
        self.config_file = self.project_root / config.get("config_file", "prometheus/prometheus.yml")
        self.data_dir = self.project_root / config.get("data_dir", "prometheus/data")
    
    def start(self):
        """Start Prometheus server."""
        # Check if Prometheus is already running
        if self._is_already_running():
            logging.info("Prometheus is already running, skipping auto-start")
            return
        
        if not self.config_file.exists():
            logging.error(f"Prometheus config file not found: {self.config_file}")
            return
        
        # Create data directory if it doesn't exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        cmd = [
            self.binary,
            f"--config.file={self.config_file}",
            f"--storage.tsdb.path={self.data_dir}"
        ]
        
        try:
            logging.info(f"Starting Prometheus: {' '.join(cmd)}")
            # Use DEVNULL to avoid pipe buffer blocking on long-running process
            # Prometheus logs to its own files; we don't need to capture output
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=self.project_root
            )
            logging.info(f"Prometheus started with PID {self._process.pid}")
            
            # Register cleanup on exit
            atexit.register(self._stop_on_exit)
            
        except Exception as e:
            logging.error(f"Failed to start Prometheus: {e}")
    
    def stop(self):
        """Stop Prometheus server if it was started by this manager."""
        self._stop(silent=False)
    
    def _stop_on_exit(self):
        """Stop Prometheus at interpreter exit without logging."""
        self._stop(silent=True)
    
    def _stop(self, silent: bool):
        """Internal stop helper with optional logging suppression."""
        if self._process is None:
            return
        
        finalizing = getattr(sys, "is_finalizing", lambda: False)()
        should_log = not silent and not finalizing
        try:
            if should_log:
                logging.info("Stopping Prometheus...")
            self._process.terminate()
            self._process.wait(timeout=5)
            if should_log:
                logging.info("Prometheus stopped")
        except Exception as e:
            if should_log:
                logging.error(f"Error stopping Prometheus: {e}")
            try:
                self._process.kill()
            except:
                pass
        finally:
            self._process = None
    
    def _is_already_running(self) -> bool:
        """Check if Prometheus is already running on the system."""
        try:
            result = subprocess.run(
                ["pgrep", "-f", "prometheus.*--config.file"],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception as e:
            logging.debug(f"Could not check if Prometheus is running: {e}")
            return False
