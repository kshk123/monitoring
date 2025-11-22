from flask import Flask, Response
from prometheus_client import Gauge, generate_latest
import time
import psutil
from threading import Thread

app = Flask(__name__)

# Gauge Metrics
CPU_GAUGE = Gauge('system_cpu_usage', 'System CPU usage')
MEM_GAUGE = Gauge('system_memory_usage', 'System memory usage')
DISK_GAUGE = Gauge('system_disk_usage', 'System disk usage')

# Network usage metrics
NET_BYTES_SENT_GAUGE = Gauge('system_net_bytes_sent', 'System network bytes sent')
NET_BYTES_RECV_GAUGE = Gauge('system_net_bytes_recv', 'System network bytes received')

def monitor_system_metrics():
    while True:
        cpu_percent = psutil.cpu_percent()
        mem_percent = psutil.virtual_memory().percent
        disk_percent = psutil.disk_usage('/').percent

        net_io_counters = psutil.net_io_counters()
        bytes_sent = net_io_counters.bytes_sent
        bytes_recv = net_io_counters.bytes_recv

        # Update Prometheus Gauges
        CPU_GAUGE.set(cpu_percent)
        MEM_GAUGE.set(mem_percent)
        DISK_GAUGE.set(disk_percent)

        # Update network usage gauges
        NET_BYTES_SENT_GAUGE.set(bytes_sent)
        NET_BYTES_RECV_GAUGE.set(bytes_recv)

        # Sleep for 15 minutes
        time.sleep(15 * 60)

@app.route('/')
def main_route():
    return "Metrics being served at /metrics endpoint"

@app.route('/metrics')
def metrics():
    return Response(generate_latest(), mimetype=str('text/plain'))

if __name__ == "__main__":
    # Start the metrics monitoring in a separate thread
    thread = Thread(target=monitor_system_metrics)
    thread.start()

    # Start the Flask app (default port is 5010)
    app.run(port=5010)
