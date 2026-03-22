# AI City - Incident Response Runbook

## SLA Commitment
- **Uptime Target:** 99.9% (8.76 hours downtime/year)
- **MTTR Target:** < 4 hours for P1 incidents
- **MTTR Target:** < 24 hours for P2 incidents

## Severity Levels

| Severity | Impact | Response Time | Resolution Time |
|----------|--------|---------------|-----------------|
| P1 Critical | Complete outage, all users affected | 15 minutes | 30 minutes |
| P2 High | Major feature unavailable | 1 hour | 4 hours |
| P3 Medium | Minor feature degraded | 4 hours | 24 hours |
| P4 Low | Cosmetic/non-blocking | 24 hours | 1 week |

## Incident Response Process

### Step 1: Detection & Alert
- Automated monitoring triggers alert
- On-call engineer acknowledges within SLA window
- Severity is assigned based on impact assessment

### Step 2: Initial Assessment
```bash
# Check current status
curl https://aicity-backend-deploy.vercel.app/health
curl https://aicity-backend-deploy.vercel.app/monitoring/stats

# Check recent deployments
vercel ls
```

### Step 3: Communication
- Create incident ticket in Paperclip
- Notify stakeholders via Slack/email
- Update status page if applicable

### Step 4: Mitigation
**For Backend Outage:**
```bash
# Check if Vercel deployment is healthy
curl -s https://aicity-backend-deploy.vercel.app/health

# Redeploy if needed
vercel --prod --force

# Rollback if deployment failed
vercel rollback
```

**For Database Issues:**
```bash
# Check database connectivity
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT 1"

# Check connection pool
curl https://aicity-backend-deploy.vercel.app/monitoring/stats
```

**For External Service Failure (Ollama/Qdrant):**
- System degrades gracefully
- RAG features disabled, other features continue
- No user action required unless prolonged

### Step 5: Resolution
- Confirm all systems operational
- Update incident ticket with resolution
- Notify stakeholders of resolution

### Step 6: Post-Incident Review
- Document timeline and root cause
- Identify improvement actions
- Update runbooks as needed

## Quick Commands Reference

```bash
# Health check
curl https://aicity-backend-deploy.vercel.app/health

# Full diagnostics
curl https://aicity-backend-deploy.vercel.app/monitoring/health/deep

# Stats
curl https://aicity-backend-deploy.vercel.app/monitoring/stats

# Logs (Vercel)
vercel logs aicity-backend-deploy

# Restart (Vercel)
vercel --prod --force

# Rollback
vercel rollback

# Database backup (manual)
python scripts/backup.py --type=db

# Restore from backup
gunzip -c /backups/db_backup_YYYYMMDD_HHMMSS.sql.gz | psql ...
```

## Escalation Contacts

| Role | Name | Contact |
|------|------|---------|
| On-call SRE | DevOps Agent | Paperclip |
| Backup On-call | TBD | TBD |
| CEO | Nova | Paperclip |

## Runbook Index

- [x] Health Check: `scripts/health_check.py`
- [x] Self-Healing: `scripts/self_heal.py`
- [x] Backup: `scripts/backup.py`
- [x] Uptime Monitor: `scripts/uptime_monitor.sh`
- [x] HA Architecture: `SRE_HA_ARCHITECTURE.md`
