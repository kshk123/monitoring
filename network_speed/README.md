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
uv run src/SpeedTest.py

# Run with options
uv run src/SpeedTest.py --retry-interval 120 --normal-interval 3600 --socket-timeout 60 --port 8080

# Run tests
uv run pytest
```

### Using pip

```bash
pip install flask speedtest-cli
python src/SpeedTest.py
```

## Usage

### Basic Usage (default settings)

```bash
python src/SpeedTest.py
```

This will:
- Start the Flask server on port 5000
- Run speedtests every 30 minutes (1800 seconds)
- Retry every 60 seconds if no data is available yet

### Custom Configuration

```bash
# Custom retry interval (2 minutes when no data)
python src/SpeedTest.py --retry-interval 120

# Custom normal interval (1 hour between tests)
python src/SpeedTest.py --normal-interval 3600

# Custom socket timeout (60 seconds for HTTP requests)
python src/SpeedTest.py --socket-timeout 60

# Custom port
python src/SpeedTest.py --port 8080

# All options
python src/SpeedTest.py --retry-interval 30 --normal-interval 900 --socket-timeout 45 --port 8080
```

### View Help

```bash
python src/SpeedTest.py --help
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

| Option | Default | Description |
|--------|---------|-------------|
| `--retry-interval` | 60 | Seconds to wait between retries when no data available |
| `--normal-interval` | 1800 | Seconds to wait between normal speedtests (30 min) |
| `--socket-timeout` | 30 | Socket timeout for individual HTTP requests (prevents hangs) |
| `--port` | 5000 | Port for Flask web server |

## Development

### Project Structure

```
network_speed/
├── src/
│   └── SpeedTest.py      # Main application
├── tests/
│   └── test_speedtest.py # Test suite
├── pyproject.toml        # Project configuration
└── README.md            # This file
```

### Contributing

1. Make your changes
2. Add tests for new functionality
3. Run the test suite to ensure everything passes
4. Submit a pull request

## License

MIT
