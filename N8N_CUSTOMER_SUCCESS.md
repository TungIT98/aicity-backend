# AI City Customer Success Workflow Setup Guide

## Overview

This guide covers the Customer Success automated workflow using n8n for AI City. The workflow handles:
- Automated onboarding sequences
- Scheduled check-ins (weekly, monthly)
- Health score monitoring
- Churn risk alerts
- Re-engagement campaigns

## Prerequisites

- PostgreSQL database running (nova_postgres:aicity)
- n8n automation platform
- Gmail account for automated emails
- Database user with INSERT/UPDATE permissions

## Database Setup

### 1. Create Database Tables

Run the SQL schema in your PostgreSQL database:

```bash
psql -h nova_postgres -U nova -d aicity -f customer_success.sql
```

This creates:
- `customer_health_scores` - Health score tracking
- `customer_onboarding_milestones` - Onboarding progress
- `customer_checkins` - Check-in logs
- `customer_success_metrics` - Success metrics
- `churn_risk_alerts` - Churn risk tracking

### 2. Verify Tables Created

```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name LIKE 'customer%';
```

## n8n Workflow Setup

### 1. Import Workflow

1. Open n8n at http://localhost:5678
2. Go to Workflows → Import from File
3. Select `n8n-customer-success-workflow.json`
4. Click Import

### 2. Configure Credentials

#### PostgreSQL Credential
1. Go to Settings → Credentials
2. Add new PostgreSQL credential
3. Configure:
   - Host: nova_postgres
   - Database: aicity
   - User: nova
   - Password: nova2026
   - Port: 5432

#### Gmail Credential
1. Add new Gmail credential
2. Follow OAuth setup (requires Google Cloud project)
3. Scopes needed: `gmail.send`

### 3. Activate Workflow

1. Open the imported workflow
2. Click "Active" toggle to enable
3. Workflow runs hourly (Hourly Check trigger)

## Webhook Endpoints

### Manual Trigger
```
POST http://localhost:5678/webhook/customer-success
```

Example usage:
```bash
curl -X POST http://localhost:5678/webhook/customer-success \
  -H "Content-Type: application/json" \
  -d '{"customer_id": 123, "action": "trigger_checkin"}'
```

## Features Explained

### Onboarding Sequence (Days 1-7)
- Day 1: Welcome email + account setup guide
- Day 2-3: Profile configuration reminder
- Day 4-5: First feature usage encouragement
- Day 6-7: Team invitation + onboarding completion

### Health Score Calculation
The `calculate_customer_health_score()` function computes scores based on:
- NPS score (0-30 points)
- Engagement level (0-20 points)
- Activity recency (0-30 points)
- Feature usage (0-20 points)

### Churn Risk Levels
- **Critical** (<20): Immediate intervention required
- **High** (20-40): Proactive outreach within 24 hours
- **Medium** (40-60): Weekly check-in
- **Low** (60+): Standard engagement

## Monitoring

### View Active Alerts
```sql
SELECT c.name, c.email, ca.risk_level, ca.created_at
FROM churn_risk_alerts ca
JOIN customers c ON c.id = ca.customer_id
WHERE ca.status = 'active'
ORDER BY ca.created_at DESC;
```

### Check-in History
```sql
SELECT c.name, cc.checkin_type, cc.status, cc.completed_at
FROM customer_checkins cc
JOIN customers c ON c.id = cc.customer_id
WHERE cc.completed_at > NOW() - INTERVAL '30 days'
ORDER BY cc.completed_at DESC;
```

## Troubleshooting

### Workflow Not Triggering
1. Check if workflow is Active (toggle in n8n)
2. Verify PostgreSQL credential is valid
3. Check n8n logs for errors

### Emails Not Sending
1. Verify Gmail OAuth is properly configured
2. Check spam folder
3. Review n8n execution history

### Health Scores Not Calculating
1. Run health score function manually:
```sql
SELECT calculate_customer_health_score(1);
```
2. Check customers have activity logs
3. Verify NPS surveys exist

## Customization

### Add Custom Milestones
```sql
INSERT INTO customer_onboarding_milestones
  (customer_id, milestone_name, milestone_order, status)
VALUES
  (1, 'Custom Step', 6, 'pending');
```

### Modify Check-in Frequency
Edit the "Hourly Check" trigger in n8n:
- Daily: Change to "Once per day"
- Weekly: Add a "Weekday" filter node

## API Endpoints (Optional)

If you need REST API access:

```javascript
// Express.js routes for customer success
app.get('/api/customers/:id/health', async (req, res) => {
  const score = await pool.query(
    'SELECT calculate_customer_health_score($1) as score',
    [req.params.id]
  );
  res.json(score.rows[0]);
});

app.get('/api/customers/:id/checkins', async (req, res) => {
  const checkins = await pool.query(
    'SELECT * FROM customer_checkins WHERE customer_id = $1 ORDER BY scheduled_at DESC',
    [req.params.id]
  );
  res.json(checkins.rows);
});
```

## Support

For issues or questions:
- Check n8n execution logs
- Review PostgreSQL error logs
- Contact the Backend team
