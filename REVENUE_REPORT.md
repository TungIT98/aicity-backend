# AI City Weekly Revenue Report

## Overview

Automated weekly revenue report system that generates every Friday with:
1. Total revenue this week
2. New customers acquired
3. Active users count
4. MRR (Monthly Recurring Revenue)
5. Top performing feature

## Setup

### 1. API Endpoints

The system provides these REST endpoints:

- `GET /reports/revenue/weekly` - Generate and get current week's report
- `GET /reports/revenue/latest` - Get latest saved report
- `GET /reports/revenue/history` - Get report history (last 12 weeks)

### 2. Scheduled Job (Linux/macOS)

Add to crontab to run every Friday at 9 AM:

```bash
crontab -e
# Add this line:
0 9 * * 5 /path/to/backend/weekly_revenue_report.sh
```

### 3. Scheduled Job (Windows)

Use Task Scheduler to run the Python script:

```powershell
# Create a scheduled task
schtasks /create /tn "Weekly Revenue Report" /tr "python backend\revenue_report.py" /sc weekly /d FRI /st 09:00
```

## Report Data

The weekly revenue report includes:

```json
{
  "report_id": "rev_20260320",
  "period_start": "2026-03-16",
  "period_end": "2026-03-22",
  "generated_at": "2026-03-20T09:00:00",
  "total_revenue_vnd": 15000000,
  "new_customers": 15,
  "active_users": 45,
  "mrr_vnd": 25000000,
  "top_feature": "AI Chat/Completion",
  "revenue_by_plan": {
    "starter": 4500000,
    "professional": 6000000,
    "enterprise": 4500000
  }
}
```

## Manual Report Generation

To generate a report manually:

```bash
cd backend
python3 revenue_report.py
```

Or via API:

```bash
curl http://localhost:8000/reports/revenue/weekly
```

## Database Schema

Reports are stored in the `reports` table:

- `report_type`: 'weekly_revenue'
- `title`: Report title
- `content`: Full JSON report data
- `period_start`, `period_end`: Report date range
- `generated_at`: Report generation timestamp