# Internet Speed Monitoring Service

A Flask-based service that monitors internet speed and exposes metrics in Prometheus format.

## Features

- Periodic internet speed testing (download & upload)
- Prometheus-compatible metrics endpoint
- Thread-safe implementation
- Configurable test intervals
- Configurable socket timeout for HTTP requests
- Automatic retry on failure
- Graceful error handling

## Installation

### Using uv (recommended)

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# For zsh users, add to your ~/.zshrc:
# export PATH="$HOME/.cargo/bin:$PATH"
# Then reload: source ~/.zshrc

# Run directly (uv handles dependencies automatically)
uv run python src/speed_test.py

# Run with custom config file
uv run python src/speed_test.py --config /path/to/config.yaml

# Run tests
uv run pytest
```

### Using pip

```bash
pip install flask speedtest-cli pyyaml fritzconnection
python src/speed_test.py
```

### Installing as a package

```bash
pip install .
speedtest-monitor --config config.yaml
```

## Configuration

All settings are managed via `config.yaml`. See the file for available options:

```yaml
speedtest:
  retry_interval: 60      # Seconds between retries when no data
  normal_interval: 3600   # Seconds between normal speedtests (1 hour)
  socket_timeout: 30      # HTTP request timeout
  metrics_port: 5000      # Flask server port

prometheus:
  metrics_enabled: true   # Enable/disable metrics endpoint
  auto_start: false       # Auto-start Prometheus server

router_restart:
  enabled: false          # Enable automatic router restart on slow speeds
  # See config.yaml for full router restart options
```

## Usage

### Basic Usage (default settings)

```bash
python src/speed_test.py
```

This will:
- Start the Flask server on port 5000 (configurable in config.yaml)
- Run speedtests at intervals defined in config.yaml
- Retry every 60 seconds if no data is available yet

### Custom Configuration File

```bash
python src/speed_test.py --config /path/to/custom-config.yaml
```

### View Help

```bash
python src/speed_test.py --help
```

## Metrics Endpoint

The service exposes metrics at `http://localhost:5000/metrics` (or your custom port).

Example output:
```
# HELP internet_speed_download_mbps Measured download speed in Mbps
# TYPE internet_speed_download_mbps gauge
internet_speed_download_mbps 150.5
# HELP internet_speed_upload_mbps Measured upload speed in Mbps
# TYPE internet_speed_upload_mbps gauge
internet_speed_upload_mbps 25.3
```

Values are in Mbps (Megabits per second).

If no data is available yet, the endpoint returns:
```
# HELP internet_speed_download_mbps Measured download speed in Mbps
# TYPE internet_speed_download_mbps gauge
internet_speed_download_mbps nan
# HELP internet_speed_upload_mbps Measured upload speed in Mbps
# TYPE internet_speed_upload_mbps gauge
internet_speed_upload_mbps nan
```

## Testing

Run the test suite:

```bash
# Run all tests with uv
uv run pytest

# Run with verbose output
uv run pytest -v

# Run with coverage
uv run pytest --cov=src --cov-report=html

# Using unittest directly
python -m pytest tests/
```

### Test Coverage

The test suite covers:
- ✅ Speedtest sampling functionality
- ✅ Flask metrics endpoint
- ✅ Thread safety and locking
- ✅ Error handling (ConfigRetrievalError, generic exceptions)
- ✅ Retry vs normal interval logic
- ✅ Prometheus format validation
- ✅ Concurrent read/write scenarios

## Prometheus Integration

Add this to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'internet_speed'
    static_configs:
      - targets: ['localhost:5000']
    scrape_interval: 1m
```

## Architecture

### Components

1. **Flask Web Server**: Serves the `/metrics` endpoint
2. **Background Thread**: Runs periodic speedtests (daemon thread)
3. **Thread Lock**: Ensures thread-safe access to speed variables

### Thread Safety

- Global variables (`download_speed`, `upload_speed`) are protected by `metrics_lock`
- All reads and writes happen within lock context
- Lock is held for minimal time to avoid blocking

### Error Handling

- **Socket Timeouts**: Individual HTTP requests timeout after configurable period (default 30s)
- **ConfigRetrievalError**: Logged as warning, metrics cleared, retry after interval
- **Generic Exceptions**: Logged with full traceback, metrics cleared, retry after interval
- **No Data State**: Returns `nan` until first successful speedtest
- **Retry Logic**: Uses fast retry interval when no data, normal interval when data exists

## Configuration Options

All options are configured via `config.yaml`:

| Section | Option | Default | Description |
|---------|--------|---------|-------------|
| `speedtest` | `retry_interval` | 60 | Seconds to wait between retries when no data available |
| `speedtest` | `normal_interval` | 3600 | Seconds to wait between normal speedtests (1 hour) |
| `speedtest` | `socket_timeout` | 30 | Socket timeout for individual HTTP requests |
| `speedtest` | `metrics_port` | 5000 | Port for Flask web server |
| `prometheus` | `metrics_enabled` | true | Enable/disable the /metrics endpoint |
| `prometheus` | `auto_start` | false | Auto-start Prometheus server |
| `router_restart` | `enabled` | false | Enable automatic router restart feature |

## Development

### Project Structure

```
network_speed/
├── src/
│   ├── __init__.py           # Package marker
│   ├── speed_test.py         # Main application
│   ├── prometheus_manager.py # Prometheus lifecycle management
│   └── router_restart.py     # Router restart functionality
├── tests/
│   ├── test_speedtest.py     # Speed test tests
│   ├── test_prometheus_manager.py
│   ├── test_router_restart.py
│   └── test_wsgi_mode.py     # WSGI compatibility tests
├── prometheus/
│   └── prometheus.yml        # Prometheus config
├── config.yaml               # Main configuration file
├── pyproject.toml            # Project configuration
└── README.md                 # This file
```

### Contributing

1. Make your changes
2. Add tests for new functionality
3. Run the test suite to ensure everything passes
4. Submit a pull request

## License

MIT
