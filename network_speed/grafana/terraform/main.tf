# Terraform configuration for Grafana Cloud Alerts
# This creates alert rules in Grafana Cloud using Infrastructure as Code
#
# Prerequisites:
# 1. Install Terraform: https://www.terraform.io/downloads
# 2. Get Grafana Cloud API key with Admin permissions
# 3. Set environment variables:
#    export GRAFANA_URL="https://your-instance.grafana.net"
#    export GRAFANA_AUTH="your-api-key"
#
# Usage:
# terraform init
# terraform plan
# terraform apply

terraform {
  required_providers {
    grafana = {
      source  = "grafana/grafana"
      version = "~> 2.0"
    }
  }
}

# Configure the Grafana provider
provider "grafana" {
  url  = var.grafana_url
  auth = var.grafana_auth
}

# Variables
variable "grafana_url" {
  description = "Grafana Cloud instance URL"
  type        = string
  default     = "https://your-instance.grafana.net"
}

variable "grafana_auth" {
  description = "Grafana API key"
  type        = string
  sensitive   = true
}

variable "prometheus_datasource_uid" {
  description = "Prometheus data source UID in Grafana (find this in Grafana Cloud: Connections → Data sources → Prometheus → Settings)"
  type        = string
  default     = "REPLACE_WITH_YOUR_PROMETHEUS_UID"
  
  validation {
    condition     = var.prometheus_datasource_uid != "REPLACE_WITH_YOUR_PROMETHEUS_UID"
    error_message = "You must replace 'REPLACE_WITH_YOUR_PROMETHEUS_UID' with your actual Prometheus datasource UID from Grafana Cloud. Find it at: Connections → Data sources → Prometheus → Settings"
  }
}

variable "download_threshold" {
  description = "Download speed threshold in Mbps"
  type        = number
  default     = 63
}

variable "consecutive_failures" {
  description = "Number of consecutive failures before alerting"
  type        = number
  default     = 5
}

variable "alert_email" {
  description = "Email address for alerts"
  type        = string
  default     = "your-email@example.com"
}

variable "lookback_window" {
  description = "Time range to look back for current speed measurement (in seconds)"
  type        = number
  default     = 3600  # 1 hour
}

# Calculated: failure_count_window = consecutive_failures * evaluation_interval
# This ensures we look back far enough to count all consecutive failures
locals {
  failure_count_window = var.consecutive_failures * var.evaluation_interval
}

variable "evaluation_interval" {
  description = "How often to evaluate alert rules (in seconds)"
  type        = number
  default     = 1800  # 30 minutes
}

variable "group_wait_time" {
  description = "Wait time before sending first notification"
  type        = string
  default     = "30s"
}

variable "group_interval_time" {
  description = "Wait time between grouped notifications"
  type        = string
  default     = "5m"
}

variable "repeat_interval_time" {
  description = "How often to resend alert if still firing"
  type        = string
  default     = "4h"
}

# Create alert folder
resource "grafana_folder" "network_monitoring" {
  title = "Network Monitoring"
}

# Contact point for email alerts
resource "grafana_contact_point" "email" {
  name = "email_alerts"

  email {
    addresses = [var.alert_email]
  }
}

# Notification policy
resource "grafana_notification_policy" "internet_speed" {
  contact_point = grafana_contact_point.email.name
  group_by      = ["alertname", "service"]

  group_wait      = var.group_wait_time
  group_interval  = var.group_interval_time
  repeat_interval = var.repeat_interval_time
}

# Alert rule for slow download speed
resource "grafana_rule_group" "internet_speed_alerts" {
  name             = "internet_speed_alerts"
  folder_uid       = grafana_folder.network_monitoring.uid
  interval_seconds = var.evaluation_interval

  rule {
    name      = "Slow Download Speed"
    condition = "B"

    # Query A: Get download speed
    data {
      ref_id = "A"

      relative_time_range {
        from = var.lookback_window
        to   = 0
      }

      datasource_uid = var.prometheus_datasource_uid

      model = jsonencode({
        expr         = "internet_speed_download_mbps{job=\"internet_speed\"}"
        intervalMs   = 1000
        maxDataPoints = 43200
        refId        = "A"
      })
    }

    # Query B: Threshold check 
    data {
      ref_id = "B"

      relative_time_range {
        from = var.lookback_window
        to   = 0
      }

      datasource_uid = "__expr__"

      model = jsonencode({
        expression = "A"
        reducer    = "last"
        refId      = "B"
        type       = "reduce"
        conditions = [
          {
            evaluator = {
              params = [var.download_threshold]
              type   = "lt"
            }
            operator = {
              type = "and"
            }
            query = {
              params = []
            }
            reducer = {
              params = []
              type   = "last"
            }
            type = "query"
          }
        ]
      })
    }

    no_data_state  = "NoData"
    exec_err_state = "Error"

    for = "${local.failure_count_window}s"

    annotations = {
      description = "Download speed has been below ${var.download_threshold} Mbps for ${var.consecutive_failures} consecutive measurements. Current speed: {{ $values.A.Value }} Mbps"
      summary     = "Internet download speed is critically slow"
    }

    labels = {
      severity = "warning"
      service  = "internet_speed"
    }
  }
}

# Outputs
output "alert_folder_uid" {
  value = grafana_folder.network_monitoring.uid
}

output "contact_point_name" {
  value = grafana_contact_point.email.name
}
