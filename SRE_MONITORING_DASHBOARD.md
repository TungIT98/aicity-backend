# AI City - Monitoring & Observability Dashboard

## Overview
This document describes the monitoring and observability setup for AI City platform.

## Key Metrics to Track

### 1. Availability Metrics
| Metric | Target | Alert Threshold |
|--------|--------|----------------|
| Uptime | 99.9% | < 99.5% |
| Error Rate | < 0.1% | > 1% |
| Health Check Success | 100% | < 95% |

### 2. Performance Metrics
| Metric | Target | Alert Threshold |
|--------|--------|----------------|
| P50 Latency | < 200ms | > 500ms |
| P95 Latency | < 500ms | > 1000ms |
| P99 Latency | < 1000ms | > 2000ms |
| Requests/minute | - | > 10000 |

### 3. Resource Metrics
| Metric | Target | Alert Threshold |
|--------|--------|----------------|
| CPU Usage | < 70% | > 85% |
| Memory Usage | < 80% | > 90% |
| Database Connections | < 80% pool | > 90% pool |

### 4. Business Metrics
| Metric | Target |
|--------|--------|
| Demo Bookings | - |
| Lead Conversions | - |
| API Usage | - |

## Monitoring Endpoints

### Backend API Metrics
```
GET /health                    - Basic health check
GET /monitoring/health/deep    - Deep diagnostics
GET /monitoring/stats          - Request statistics
GET /monitoring/stats/{ep}     - Per-endpoint stats
GET /monitoring/errors         - Recent errors
GET /analytics/dashboard       - Business metrics
```

### Prometheus Export (Future)
```
GET /metrics                   - Prometheus-format metrics
```

## Alert Rules

### Critical (P1) - Page immediately
- Health check fails for > 1 minute
- Error rate > 5%
- All instances down

### Warning (P2) - Page on-call
- Error rate > 1%
- Latency P95 > 1000ms
- Health check degraded

### Info (P3) - Slack notification
- Error rate > 0.1%
- Latency P95 > 500ms
- Non-critical service down

## Dashboard Panels

### 1. Overview Dashboard
- Uptime percentage (last 7/30 days)
- Error rate trend
- Request volume
- Active users

### 2. Performance Dashboard
- Latency percentiles (P50, P95, P99)
- Request rate
- Response size
- Slowest endpoints

### 3. Infrastructure Dashboard
- Backend health
- Database health
- External services status
- Deployment history

### 4. Business Dashboard
- Demo bookings
- Lead conversion rate
- Revenue metrics
- Funnel progression

## Grafana Dashboard Config

```json
{
  "dashboard": {
    "title": "AI City - Production Overview",
    "tags": ["aicity", "production"],
    "timezone": "Asia/Ho_Chi_Minh",
    "panels": [
      {
        "title": "Backend Health",
        "type": "stat",
        "targets": [
          {
            "expr": "up{job='aicity-backend'}",
            "refId": "A"
          }
        ]
      },
      {
        "title": "Request Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(http_requests_total[5m])",
            "refId": "A"
          }
        ]
      },
      {
        "title": "Error Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(http_requests_total{status=~'5..'}[5m]) / rate(http_requests_total[5m]) * 100",
            "refId": "A"
          }
        ]
      },
      {
        "title": "Latency P95",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) * 1000",
            "refId": "A"
          }
        ]
      }
    ]
  }
}
```

## AlertManager Config

```yaml
# alertmanager.yml
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'slack'
  routes:
  - match:
      severity: critical
    receiver: 'pagerduty'
  - match:
      severity: warning
    receiver: 'slack'

receivers:
- name: 'slack'
  slack_configs:
  - channel: '#alerts-aicity'
    api_url: '${SLACK_WEBHOOK_URL}'
- name: 'pagerduty'
  pagerduty_configs:
  - service_key: '${PAGERDUTY_KEY}'
```
