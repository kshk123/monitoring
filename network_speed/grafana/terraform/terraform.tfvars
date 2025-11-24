# Grafana Cloud Configuration
grafana_url  = "https://your-instance.grafana.net"  # Replace with your Grafana Cloud URL
# grafana_auth is set via environment variable: export TF_VAR_grafana_auth="your-api-key"

# Prometheus Data Source
# IMPORTANT: Replace with your actual Prometheus datasource UID from Grafana Cloud
# Find it at: Grafana Cloud → Connections → Data sources → Prometheus → Settings (in the URL or page)
# Example UID format: "PBFA97CFB590B2093" (NOT "prometheus")
prometheus_datasource_uid = "REPLACE_WITH_YOUR_PROMETHEUS_UID"

# Alert Thresholds
download_threshold    = 63   # Mbps - Pi WiFi shows ~42% of actual (150 Mbps actual = 63 Mbps on Pi)
consecutive_failures  = 5    # Number of consecutive failures before alerting (5 × 30min = 2.5 hours)

# Email Configuration
alert_email = "your-email@example.com"  # Replace with your email address

# Alert Timing (in seconds)
lookback_window      = 3600   # How far back to look for current speed (1 hour)
evaluation_interval  = 1800   # How often to evaluate alerts (30 minutes, matches scrape interval)
# Note: failure_count_window is calculated automatically as consecutive_failures × evaluation_interval

# Notification Settings
group_wait_time      = "30s"  # Wait time before sending first notification
group_interval_time  = "5m"   # Wait time between grouped notifications
repeat_interval_time = "4h"   # How often to resend if alert is still firing
