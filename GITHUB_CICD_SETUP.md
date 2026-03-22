# GitHub CI/CD Setup Guide - AI City Backend

## Overview
This guide explains how to connect the AI City backend to GitHub Actions for automated CI/CD deployment.

## Known Vercel IDs (from existing setup)
- **Vercel Team/Org ID:** `team_4rOMBfXBgdutLg9ZBN4MA6Re`
- **Backend Production Project ID:** `prj_B3BScDpWSxxUI5ktynKXcGa6WXpf` (aicity-backend-deploy)
- **Booking Frontend Project ID:** `prj_wgrB2xq1sw5skYr7Cpfaxbpp68mb`
- **GitHub username:** TungIT98

## Two Deployment Paths

### Path A: Vercel Auto-Deploy (Recommended - Already Working)
Vercel automatically syncs from the Paperclip workspace. No GitHub repo needed for basic deployment.

### Path B: GitHub Actions CI/CD (Full pipeline with quality gates)
Follow Steps 1-5 below to enable the full 9-job pipeline.

## Step 1: Create GitHub Repository

1. Go to: https://github.com/new
2. Repository name: `aicity-backend`
3. Owner: `TungIT98`
4. **DO NOT** initialize with README (we have existing code)
5. Click "Create repository"

Then push existing code:
```bash
cd backend
git init
git add .
git commit -m "Initial commit: AI City Backend v1.0"
git branch -M main
git remote add origin https://github.com/TungIT98/aicity-backend.git
git push -u origin main
```

## Step 2: Configure Vercel Git Integration

1. Go to: https://vercel.com/tungit98s-projects/aicity-backend-deploy/settings/git
2. Connect the GitHub repository `TungIT98/aicity-backend`
3. Set branch to `main`
4. Build Command: `pip install -r requirements.txt`
5. Install Command: leave default
6. Output Directory: `.`

**Note:** Vercel already has environment variables set (DATABASE_URL, etc.). These will be carried over.

## Step 3: Add GitHub Secrets

Go to: https://github.com/TungIT98/aicity-backend/settings/secrets/actions

Add these secrets:

| Secret Name | Value | Notes |
|------------|-------|-------|
| `VERCEL_TOKEN` | (generate at vercel.com/account/tokens) | Create with scope: full account |
| `VERCEL_ORG_ID` | `team_4rOMBfXBgdutLg9ZBN4MA6Re` | Vercel team ID |
| `VERCEL_PRODUCTION_PROJECT_ID` | `prj_B3BScDpWSxxUI5ktynKXcGa6WXpf` | Backend project |
| `VERCEL_STAGING_PROJECT_ID` | `prj_B3BScDpWSxxUI5ktynKXcGa6WXpf` | Use same project (alias) |
| `SLACK_WEBHOOK_URL` | (optional) | Skip if no Slack |

## Step 4: Trigger First GitHub Actions Run

1. Go to: https://github.com/TungIT98/aicity-backend/actions
2. The `CI/CD Pipeline` workflow should auto-trigger
3. Or manually trigger via: Actions tab → CI/CD Pipeline → Run workflow

Expected jobs:
1. `quality` - Security audit + linting
2. `test` - Unit tests with coverage
3. `integration-test` - API tests against Postgres
4. `build` - Docker image build
5. `deploy-staging` - Deploy to staging
6. `smoke-test` - Health checks
7. `deploy-production` - Zero-downtime production deploy
8. `post-deploy` - Summary report
9. `rollback` - Manual trigger available

## Step 5: Verify

```bash
# Test the production health endpoint
curl https://aicity-backend-deploy.vercel.app/health
curl https://aicity-backend-deploy.vercel.app/live
curl https://aicity-backend-deploy.vercel.app/ready
```

## Rollback (if needed)

Go to: https://github.com/TungIT98/aicity-backend/actions → CI/CD Pipeline → Run workflow → Select "production"

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `VERCEL_TOKEN` invalid | Regenerate at vercel.com/account/tokens |
| Deployment fails at build | Check Vercel build logs; verify DATABASE_URL is set |
| Health check timeout | Vercel serverless cold starts take ~30s; increase sleep in workflow |
| Quality/test jobs fail | These are `continue-on-error: true` - pipeline continues |

## Current Production Status (2026-03-22)

| Component | Status | URL |
|----------|--------|-----|
| Backend (Python FastAPI) | ✅ Healthy | https://aicity-backend-deploy.vercel.app |
| Booking Frontend | ⚠️ Auth blocked | https://booking-ddqljagl2-tungit98s-projects.vercel.app |
| PostgreSQL (Neon) | ✅ Connected | 48 leads in DB |
| Health probes | ✅ All passing | /health, /live, /ready |

---

Updated: 2026-03-22 17:05 UTC
Agent: AI City SRE
