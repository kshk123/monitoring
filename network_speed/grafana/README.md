# Grafana Cloud Alerts Setup

This directory contains Terraform configuration for setting up alerts in Grafana Cloud for internet speed monitoring.

## Alert Logic

The alert will trigger when:
- **Download speed** < 63 Mbps for 5 consecutive measurements (2.5 hours)

*Note: The 63 Mbps threshold is calibrated for Raspberry Pi WiFi limitations (42% of actual internet speed). If your Pi shows ~80 Mbps, your actual internet speed is ~190 Mbps.*

Notifications are sent via email.

## Setup

### 1. Install Terraform

```bash
# macOS
brew install terraform

# Linux
wget https://releases.hashicorp.com/terraform/1.6.0/terraform_1.6.0_linux_amd64.zip
unzip terraform_1.6.0_linux_amd64.zip
sudo mv terraform /usr/local/bin/
```

### 2. Get Grafana Cloud Credentials

**Grafana URL:**
- Your Grafana Cloud instance URL (e.g., `https://your-instance.grafana.net`)

**API Key:**
1. Go to Grafana Cloud
2. Navigate to: Administration → Service accounts → Create service account
3. Name: "Terraform Provisioning"
4. Role: Admin
5. Add token → Copy the key

**Prometheus Data Source UID:**
1. Go to Grafana Cloud
2. Navigate to: Connections → Data sources → Prometheus
3. Copy the UID from the URL or settings page

### 3. Configure Variables

Edit `grafana/terraform/terraform.tfvars` with your actual values:

```hcl
# Grafana Configuration
grafana_url = "https://your-instance.grafana.net"

# Prometheus Data Source UID (from Grafana Cloud)
prometheus_datasource_uid = "your-prometheus-uid"

# Alert Thresholds
download_threshold    = 63  # Mbps (calibrated for Pi WiFi)
consecutive_failures  = 5   # Number of failures before alerting

# Notification Settings
alert_email = "your-email@example.com"

# Timing Configuration (in seconds)
lookback_window        = 3600  # 1 hour
failure_count_window   = 9000  # 2.5 hours (for 5×30min checks)
evaluation_interval    = 1800  # 30 minutes (match Prometheus scrape)
group_wait_time        = 30    # 30 seconds
group_interval_time    = 300   # 5 minutes
repeat_interval_time   = 14400 # 4 hours
```

**Important:** The Grafana API key is **not** in `terraform.tfvars` for security. Set it as an environment variable instead (see step 4).

### 4. Set Environment Variables

Set the Grafana API key (never commit this to git):

```bash
export TF_VAR_grafana_auth="your-api-key"
```

### 5. Apply Configuration

```bash
cd grafana/terraform
terraform init
terraform plan
terraform apply
```

### 6. Verify

Go to Grafana Cloud → Alerting → Alert rules

You should see:
- ✅ Slow Download Speed


## Customizing Thresholds

Edit the values in `terraform.tfvars`:

- **`download_threshold`:** Minimum acceptable download speed (Mbps)
  - Default: 63 Mbps (calibrated for Pi WiFi = ~150 Mbps actual internet)
  - If using Ethernet: Set to your actual minimum speed (e.g., 150)
- **`consecutive_failures`:** Number of consecutive failures before alerting
  - `1` = Alert immediately on first failure
  - `5` = Alert after 2.5 hours of slow speed (recommended, default)
  - `10` = Alert after 5 hours of slow speed
- **`alert_email`:** Email address for notifications
- **`evaluation_interval`:** How often to check (in seconds)
  - Default: 1800 (30 minutes, matches Prometheus scrape interval)

After changing values, run:
```bash
terraform plan
terraform apply
```

## Managing Alerts

**View current state:**
```bash
terraform show
```

**Update alerts:**
1. Edit `main.tf`
2. Run `terraform plan` to preview changes
3. Run `terraform apply` to apply changes

**Delete alerts:**
```bash
terraform destroy
```

## Testing Alerts

To test if alerts are working:

1. Temporarily set a very high threshold in `terraform.tfvars`:
   ```hcl
   download_threshold = 1000  # Temporarily high
   ```
2. Apply: `terraform apply`
3. Wait for the next speedtest measurement (30 minutes)
4. You should receive an alert email after 2.5 hours (5 consecutive failures)
5. Reset threshold to 63 and apply again


## Troubleshooting

**Alerts not triggering:**
- Check if metrics are flowing: Grafana → Explore → Query `internet_speed_download_mbps`
- Verify alert evaluation: Grafana → Alerting → Alert rules → View details
- Check contact point: Grafana → Alerting → Contact points → Test

**Emails not received:**
- Check spam folder
- Verify email address in `terraform.tfvars`
- Test contact point manually in Grafana UI

**Terraform errors:**
- Verify API key has Admin permissions
- Check Prometheus datasource UID is correct
- Run `terraform init` if provider errors occur

## Files

- `terraform/main.tf` - Terraform infrastructure configuration with variable declarations
- `terraform/terraform.tfvars` - Configuration values (committed with placeholders, edit with your actual values)
- `README.md` - This file
