from flask import Flask, Response
import speedtest
import time
import threading
import logging
import math
import argparse

app = Flask(__name__)
download_speed = None
upload_speed = None
metrics_lock = threading.Lock()
_thread_started = False
_startup_lock = threading.Lock()

# Default sleep times (in seconds)
RETRY_INTERVAL = 60  # Fast retry when no data yet
NORMAL_INTERVAL = 1800  # Normal interval (30 minutes)
SOCKET_TIMEOUT = 30  # Socket timeout for individual HTTP requests (30 seconds)

logging.basicConfig(level=logging.INFO)


def start_speedtest_thread():
    """Start the background speedtest thread if not already started."""
    global _thread_started
    with _startup_lock:
        if not _thread_started:
            logging.info(f"Starting speedtest thread (retry: {RETRY_INTERVAL}s, normal: {NORMAL_INTERVAL}s)")
            threading.Thread(target=speedtest_thread, daemon=True).start()
            _thread_started = True


def get_sleep_interval():
    """Determine the sleep interval based on current metrics state.
    
    Returns RETRY_INTERVAL if we have no data yet, otherwise NORMAL_INTERVAL.
    Must be called with metrics_lock held.
    """
    return RETRY_INTERVAL if download_speed is None else NORMAL_INTERVAL


def take_speedtest_sample():
    """Run a speedtest and store the results under lock."""
    global download_speed, upload_speed
    s = speedtest.Speedtest(timeout=SOCKET_TIMEOUT)
    s.get_best_server()
    download = s.download() / 1024 / 1024
    upload = s.upload() / 1024 / 1024
    with metrics_lock:
        download_speed = download
        upload_speed = upload


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
    start_speedtest_thread()
    
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
    parser = argparse.ArgumentParser(description='Internet speed monitoring service')
    parser.add_argument('--retry-interval', type=int, default=60,
                        help='Retry interval in seconds when no data yet (default: 60)')
    parser.add_argument('--normal-interval', type=int, default=1800,
                        help='Normal interval in seconds between speed tests (default: 1800)')
    parser.add_argument('--socket-timeout', type=int, default=30,
                        help='Socket timeout in seconds for HTTP requests (default: 30)')
    parser.add_argument('--port', type=int, default=5000,
                        help='Port to run Flask server on (default: 5000)')
    args = parser.parse_args()
    
    global RETRY_INTERVAL, NORMAL_INTERVAL, SOCKET_TIMEOUT
    RETRY_INTERVAL = args.retry_interval
    NORMAL_INTERVAL = args.normal_interval
    SOCKET_TIMEOUT = args.socket_timeout
    
    start_speedtest_thread()
    app.run(host='0.0.0.0', port=args.port)


if __name__ == '__main__':
    main()
