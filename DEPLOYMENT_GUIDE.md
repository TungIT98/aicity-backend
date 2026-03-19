# AI City Deployment Guide - aicity.com

## Overview
This guide covers deploying AI City backend to production on aicity.com (IP: 3.33.130.190)

## Prerequisites
- Domain: aicity.com (already registered)
- GitHub repo: `TungIT98/aicity-backend` (must be created manually - see below)
- Railway or Render account for hosting

## ⚠️ IMPORTANT: Create GitHub Repo First

The backend code is ready in a local git repo. Create the GitHub repo:

1. Go to: https://github.com/new
2. Repository name: `aicity-backend`
3. Description: "AI City Backend API - FastAPI server for AI City services"
4. Make it Public
5. Do NOT initialize with README
6. Copy the repo URL (e.g., `https://github.com/TungIT98/aicity-backend.git`)
7. Add remote to local repo:
   ```bash
   cd backend
   git remote add origin https://github.com/TungIT98/aicity-backend.git
   git push -u origin master
   ```

## Deployment Options

### Option 1: Railway (Recommended for Python/FastAPI)

**Pros:**
- Native Python support
- Managed PostgreSQL (optional)
- Automatic SSL
- Easy scaling

**Steps:**
1. Push code to GitHub
2. Connect Railway to GitHub repo
3. Set environment variables from `.env.production`
4. Deploy

**Environment Variables to Set:**
```
DB_HOST=10.0.0.50  # Internal IP of nova_postgres
DB_PORT=5432
DB_NAME=aicity
DB_USER=aicity
DB_PASSWORD=aicity_secure_2024

QDRANT_URL=http://10.0.0.51:6333

ENV=production
DEBUG=false
```

### Option 2: Render

**Pros:**
- Free tier available
- Python native
- Automatic SSL

**Steps:**
1. Connect GitHub to Render
2. Create Python service
3. Set start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables

### Option 3: Self-Hosted on VPS (DigitalOcean/Railway/Render)

For full control, deploy to a VPS:

1. **Create VPS** (DigitalOcean $5/mo droplet)
2. **Install Docker:**
   ```bash
   curl -fsSL https://get.docker.com | sh
   sudo systemctl start docker
   sudo systemctl enable docker
   ```

3. **Deploy with Docker Compose:**
   ```yaml
   # docker-compose.production.yml
   version: '3.8'

   services:
     backend:
       build: .
       ports:
         - "8000:8000"
       environment:
         - DB_HOST=nova_postgres
         - DB_PORT=5432
         - QDRANT_URL=http://nova_qdrant:6333
       depends_on:
         - caddy

     caddy:
       image: caddy:2
       ports:
         - "80:80"
         - "443:443"
       volumes:
         - ./Caddyfile:/etc/Caddyfile
         - caddy_data:/data
   ```

4. **Caddyfile for automatic SSL:**
   ```
   aicity.com {
       reverse_proxy backend:8000
       tls your-email@aicity.com
   }
   ```

## DNS Configuration

**Required DNS Records:**
```
A @ 3.33.130.190
CNAME www aicity.com
```

**For Railway:**
- Add custom domain in Railway dashboard
- Railway will provide DNS target

**For Render:**
- Add domain in Render settings
- Use their DNS target

## Database Connection

### Option A: Continue using self-hosted PostgreSQL

Current setup: `nova_postgres` at 10.0.0.50:5432

For external access:
1. Edit PostgreSQL config: `postgresql.conf`
   ```
   listen_addresses = '*'
   ```
2. Add to `pg_hba.conf`:
   ```
   host all all 0.0.0.0/0 md5
   ```
3. Update `.env.production` with external IP

### Option B: Managed PostgreSQL (Recommended)

**Supabase:**
1. Create project at supabase.com
2. Get connection string
3. Update environment variables

**Neon:**
1. Create project at neon.tech
2. Get connection string
3. Update environment variables

## Security Checklist

- [ ] Change default passwords in `.env.production`
- [ ] Set `DEBUG=false` in production
- [ ] Restrict CORS to `aicity.com`
- [ ] Enable HTTPS/SSL
- [ ] Set up firewall rules
- [ ] Configure rate limiting

## Health Check

After deployment, verify:
```bash
curl https://aicity.com/health
```

Expected response:
```json
{
  "status": "running",
  "service": "AI City API",
  "ollama": "ok",
  "qdrant": "ok",
  "postgres": "ok"
}
```

## Rollback Plan

1. Keep previous Docker image tag
2. Use Railway/Render rollback feature
3. Keep database backups current

## Monitoring

- **Health endpoint:** `GET /health`
- **Metrics:** Integrate with Matomo
- **Logs:** Check platform dashboard

## Estimated Monthly Cost

| Component | Option | Cost |
|-----------|--------|------|
| Hosting | Railway Pro | $20/mo |
| Database | Self-hosted | $0 (existing) |
| Domain | aicity.com | $12/year |
| SSL | Free (platform) | $0 |
| **Total** | | **~$20/mo** |