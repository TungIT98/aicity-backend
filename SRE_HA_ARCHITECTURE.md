# AI City - High Availability & Self-Healing Architecture

## Overview
This document describes the HA architecture for AI City platform, targeting 99.9% uptime SLA.

## Architecture Diagram

```
                    ┌─────────────────────────────────────────┐
                    │              Load Balancer               │
                    │     (Vercel Edge / CloudFlare)          │
                    └─────────────┬───────────────────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
        ┌─────▼─────┐      ┌─────▼─────┐      ┌─────▼─────┐
        │  Instance  │      │  Instance │      │  Instance │
        │     1     │      │     2     │      │     3     │
        │  (Primary)│      │ (Standby) │      │ (Standby) │
        └───────────┘      └───────────┘      └───────────┘
              │                   │                   │
              └───────────────────┼───────────────────┘
                                  │
                    ┌─────────────▼───────────────┐
                    │        Database Cluster      │
                    │    (PostgreSQL Primary +     │
                    │     Read Replicas)           │
                    └─────────────────────────────┘
```

## Health Check Endpoints

### Primary Health Check (`/health`)
- Returns status of all dependencies
- Response time target: < 100ms
- Used by load balancers and orchestrators

### Deep Health Check (`/monitoring/health`)
- Full system diagnostics
- Database connectivity test
- External service reachability
- Response time target: < 2s

### Readiness Probe (`/ready`)
- Returns 200 if instance is ready to serve traffic
- Used by Kubernetes/Vercel for traffic routing

### Liveness Probe (`/live`)
- Returns 200 if instance is alive
- Used for process monitoring

## Auto-Scaling Configuration

### Vercel (Current)
- Automatic scaling based on request volume
- Cold start optimization enabled
- Edge caching for static assets

### Future: Kubernetes (GCP/AWS)
```yaml
# HPA configuration
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
spec:
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

## Graceful Degradation

When dependencies fail, the system degrades gracefully:

| Dependency | Failure Impact | Fallback Behavior |
|------------|---------------|-------------------|
| Ollama | RAG search unavailable | Return cached results + error message |
| Qdrant | RAG search unavailable | Return cached results + error message |
| PostgreSQL | All features fail | Return "Service temporarily unavailable" |
| Matomo | Analytics unavailable | Continue without analytics tracking |

## Zero-Downtime Deployment

1. **Blue/Green Deployment**: Vercel handles automatic blue/green
2. **Canary Release**: Deploy to 5% of traffic first
3. **Health Check Gate**: Deploy only after health checks pass
4. **Automatic Rollback**: Revert if error rate increases > 5%

## Incident Response

### Severity Levels
- **P1 (Critical)**: Complete outage, > 5% error rate
- **P2 (High)**: Major feature degraded, > 1% error rate
- **P3 (Medium)**: Minor feature degraded, > 0.1% error rate
- **P4 (Low)**: Cosmetic issues, no user impact

### MTTR Targets
- P1: < 30 minutes
- P2: < 4 hours
- P3: < 24 hours
- P4: < 1 week
