from flask import Flask, Response
import speedtest
import time
import threading
import logging
import math
import argparse
from pathlib import Path
import yaml

# Use try/except for imports to support both direct execution and package installation
try:
    from .prometheus_manager import PrometheusManager
    from .router_restart import RouterRestartManager
except ImportError:
    # Direct execution (python src/speed_test.py)
    from prometheus_manager import PrometheusManager
    from router_restart import RouterRestartManager

app = Flask(__name__)
download_speed = None
upload_speed = None
metrics_lock = threading.Lock()
_thread_started = False
_startup_lock = threading.Lock()
_prometheus_manager = None
_router_restart_manager = None
_config = None

# Runtime configuration (set by main() or lazy-loaded from config)
# Defaults are provided for WSGI mode where main() is not called
_DEFAULT_RETRY_INTERVAL = 60
_DEFAULT_NORMAL_INTERVAL = 3600
_DEFAULT_SOCKET_TIMEOUT = 30

retry_interval = None
normal_interval = None
socket_timeout = None

# Configure basic logging at module level
# Note: This only sets up console logging. RouterRestartManager can add file handlers.
# Using force=True would reset all handlers, so we avoid that here.
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO)

# Project root directory (parent of src/)
_PROJECT_ROOT = Path(__file__).parent.parent


def _resolve_config_path(config_path: str) -> Path:
    """Resolve config path relative to project root if not absolute.
    
    Args:
        config_path: Path to config file (absolute or relative)
        
    Returns:
        Resolved absolute Path
    """
    path = Path(config_path)
    if path.is_absolute():
        return path
    
    # Try relative to project root first (for installed packages)
    project_relative = _PROJECT_ROOT / path
    if project_relative.exists():
        return project_relative
    
    # Try relative to CWD (for development)
    cwd_relative = Path.cwd() / path
    if cwd_relative.exists():
        return cwd_relative
    
    # Default to project root path (will raise FileNotFoundError if missing)
    return project_relative


def load_config(config_path="config.yaml"):
    """Load configuration from YAML file.
    
    Args:
        config_path: Path to the config file (absolute or relative to project root).
        
    Raises:
        FileNotFoundError: If config file is not found.
        
    Returns:
        dict: Configuration dictionary (empty dict if file is empty).
    """
    path = _resolve_config_path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path.absolute()}")
    
    logging.info(f"Loading config from {path}")
    with open(path, "r") as f:
        config = yaml.safe_load(f)
    
    # yaml.safe_load returns None for empty files
    if config is None:
        logging.warning(f"Config file {path} is empty, using defaults")
        return {}
    
    if not isinstance(config, dict):
        logging.warning(f"Config file {path} is not a valid YAML dict, using defaults")
        return {}
    
    return config


def _ensure_config_loaded():
    """Ensure configuration is loaded, using defaults for WSGI mode.
    
    When running via WSGI (e.g., gunicorn), main() is never called,
    so we need to load config lazily on first request.
    """
    global _config, retry_interval, normal_interval, socket_timeout
    
    if retry_interval is not None:
        return  # Already configured
    
    # Load config if not already loaded
    if _config is None:
        try:
            _config = load_config()
        except FileNotFoundError:
            logging.warning("Config file not found, using defaults")
            _config = {}
    
    speedtest_config = _config.get("speedtest", {})
    retry_interval = speedtest_config.get("retry_interval", _DEFAULT_RETRY_INTERVAL)
    normal_interval = speedtest_config.get("normal_interval", _DEFAULT_NORMAL_INTERVAL)
    socket_timeout = speedtest_config.get("socket_timeout", _DEFAULT_SOCKET_TIMEOUT)
    
    logging.info(f"Config loaded: retry={retry_interval}s, normal={normal_interval}s, timeout={socket_timeout}s")


def start_speedtest_thread():
    """Start the background speedtest thread if not already started."""
    global _thread_started
    
    # Ensure config is loaded before starting thread
    _ensure_config_loaded()
    
    with _startup_lock:
        if not _thread_started:
            logging.info(f"Starting speedtest thread (retry: {retry_interval}s, normal: {normal_interval}s)")
            threading.Thread(target=speedtest_thread, daemon=True).start()
            _thread_started = True


def get_sleep_interval():
    """Determine the sleep interval based on current metrics state.
    
    Returns retry_interval if we have no data yet, otherwise normal_interval.
    Must be called with metrics_lock held.
    """
    return retry_interval if download_speed is None else normal_interval


def check_router_restart(speed_mbps):
    """Check if router should be restarted based on speed."""
    if _router_restart_manager is None:
        return
    
    try:
        _router_restart_manager.check_and_restart(speed_mbps)
    except Exception as e:
        logging.error(f"Error checking router restart: {e}")


def take_speedtest_sample():
    """Run a speedtest and store the results under lock."""
    global download_speed, upload_speed
    s = speedtest.Speedtest(timeout=socket_timeout)
    s.get_best_server()
    download = s.download() / 1024 / 1024
    upload = s.upload() / 1024 / 1024
    with metrics_lock:
        download_speed = download
        upload_speed = upload
    
    # Check if router should be restarted based on download speed
    check_router_restart(download)


def speedtest_thread():
    global download_speed, upload_speed
    while True:
        try:
            take_speedtest_sample()
            with metrics_lock:
                sleep_time = get_sleep_interval()
            time.sleep(sleep_time)
        except speedtest.ConfigRetrievalError:
            logging.warning("Failed to retrieve speedtest configuration. Skipping this round.")
            with metrics_lock:
                download_speed = None
                upload_speed = None
                sleep_time = get_sleep_interval()
            time.sleep(sleep_time)
        except Exception:
            logging.exception("Speedtest failed; will retry after sleep.")
            with metrics_lock:
                download_speed = None
                upload_speed = None
                sleep_time = get_sleep_interval()
            time.sleep(sleep_time)

@app.route('/metrics')
def metrics():
    global _config
    
    # Ensure config is loaded with fallback to defaults
    _ensure_config_loaded()
    
    start_speedtest_thread()
    
    # Check if metrics are enabled
    if not _config.get("prometheus", {}).get("metrics_enabled", True):
        return Response("# Metrics disabled\n", mimetype='text/plain')
    
    with metrics_lock:
        download = download_speed
        upload = upload_speed

    download_val = download if download is not None else math.nan
    upload_val = upload if upload is not None else math.nan

    lines = [
        "# HELP internet_speed_download_mbps Measured download speed in Mbps",
        "# TYPE internet_speed_download_mbps gauge",
        f"internet_speed_download_mbps {download_val}",
        "# HELP internet_speed_upload_mbps Measured upload speed in Mbps",
        "# TYPE internet_speed_upload_mbps gauge",
        f"internet_speed_upload_mbps {upload_val}",
    ]
    return Response('\n'.join(lines), mimetype='text/plain')

def main():
    """Main entry point for the application"""
    global _config, _prometheus_manager, _router_restart_manager, retry_interval, normal_interval, socket_timeout
    
    parser = argparse.ArgumentParser(description='Internet speed monitoring service')
    parser.add_argument('--config', type=str, default='config.yaml',
                        help='Path to configuration file (default: config.yaml)')
    args = parser.parse_args()
    
    # Load configuration
    _config = load_config(args.config)
    speedtest_config = _config.get("speedtest", {})
    
    # Load settings from config with defaults (consistent with WSGI mode)
    retry_interval = speedtest_config.get("retry_interval", _DEFAULT_RETRY_INTERVAL)
    normal_interval = speedtest_config.get("normal_interval", _DEFAULT_NORMAL_INTERVAL)
    socket_timeout = speedtest_config.get("socket_timeout", _DEFAULT_SOCKET_TIMEOUT)
    port = speedtest_config.get("metrics_port", 5000)
    
    # Start Prometheus if configured
    if _config.get("prometheus", {}).get("auto_start", False):
        _prometheus_manager = PrometheusManager(_config.get("prometheus", {}))
        _prometheus_manager.start()
    
    # Initialize router restart manager if enabled
    if _config.get("router_restart", {}).get("enabled", False):
        _router_restart_manager = RouterRestartManager(_config)
    
    # Start speedtest thread
    start_speedtest_thread()
    
    # Start Flask server
    try:
        app.run(host='0.0.0.0', port=port)
    finally:
        if _prometheus_manager:
            _prometheus_manager.stop()


if __name__ == '__main__':
    main()
