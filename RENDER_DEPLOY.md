# Render Deployment Guide

## Quick Deploy (Free Tier)

### Prerequisites
- Render account (free at render.com - no credit card)
- GitHub account (optional - can upload files directly)

### Option 1: Deploy via GitHub (Recommended)

1. **Create Render Account**
   - Go to https://render.com and sign up with email or GitHub
   - No credit card required for free tier

2. **Create New Web Service**
   - Click "New" → "Web Service"
   - Connect your GitHub repository OR
   - For direct deploy without GitHub:
     - Zip the backend files
     - Use render.com's "Deploy from zip" option

3. **Configure Service**
   - Name: `aicity-api`
   - Environment: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

4. **Environment Variables**
   Add these in Render dashboard:
   ```
   DATABASE_URL=postgresql://user:pass@host:5432/aicity
   QDRANT_URL=http://qdrant:6333
   OLLAMA_BASE_URL=http://ollama:11434
   JWT_SECRET=your-secret-key
   FRONTEND_URL=https://your-frontend.vercel.app
   MATOMO_URL=https://analytics.aicity.dev
   MATOMO_SITE_ID=1
   ```

5. **Deploy**
   - Click "Create Web Service"
   - Wait for build and deploy
   - Check logs for errors

### Option 2: Deploy via CLI

```bash
# Install Render CLI
npm install -g @render/cloud-services

# Login
render login

# Deploy
cd aicity-backend-local
render create service --name aicity-api --type web --plan free
render env set DATABASE_URL="postgresql://..."
```

### Verify Deployment

```bash
curl https://aicity-api.onrender.com/health
```

Expected response:
```json
{"status":"ok","timestamp":"..."}
```

## Free Tier Limits
- 750 hours/month
- Sleeps after 15 min of inactivity (auto-wake)
- No custom domain (requires paid plan)

## Troubleshooting

### Build Fails
- Check requirements.txt includes all dependencies
- Verify Python version compatibility

### Database Connection Error
- Ensure DATABASE_URL is correct
- Database must be accessible from Render (use Supabase/Neon for free PostgreSQL)

### 503 Error After Deploy
- Cold start - wait 30 seconds
- Check logs in Render dashboard