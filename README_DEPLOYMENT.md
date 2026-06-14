# Mejhr Platform — GCC/Saudi Deployment Guide

This guide covers deploying Mejhr on a Linux VPS in **Saudi Arabia or GCC**
(required to reach Saudi Exchange without Akamai geo-blocking).

---

## Database: Supabase PostgreSQL

Mejhr uses Supabase as its PostgreSQL host. There are two connection modes:

### Connection String Types

| Variable | Mode | Port | Used by |
|----------|------|------|---------|
| `DATABASE_URL` | Session Pooler or Transaction Pooler | 5432 / 6543 | FastAPI (asyncpg) |
| `DATABASE_URL_SYNC` | Session Pooler or Direct | 5432 | Alembic migrations (psycopg2) |

```dotenv
# Session Pooler — works for both app and Alembic (recommended for simplicity)
DATABASE_URL=postgresql+asyncpg://postgres.[REF]:[PASS]@aws-0-[REGION].pooler.supabase.com:5432/postgres?ssl=require
DATABASE_URL_SYNC=postgresql://postgres.[REF]:[PASS]@aws-0-[REGION].pooler.supabase.com:5432/postgres?sslmode=require
```

### Important Notes

- **Never use the Transaction Pooler (port 6543) for Alembic migrations.** PgBouncer's
  transaction mode does not support the persistent sessions that DDL migrations require.
  Use the Session Pooler (port 5432) or the Direct Connection for `DATABASE_URL_SYNC`.

- **IPv4-only networks:** Supabase's direct connection (`db.[REF].supabase.co:5432`)
  requires IPv6 or the Supabase IPv4 Add-On. If your server is IPv4-only, use the
  **Session Pooler** URL for both `DATABASE_URL` and `DATABASE_URL_SYNC` — it resolves
  over IPv4.

- **asyncpg + Transaction Pooler:** If you use the Transaction Pooler (port 6543)
  for `DATABASE_URL`, prepared statements must be disabled. `database.py` detects
  `pooler.supabase.com` in the URL and sets `prepared_statement_cache_size=0`
  automatically. No manual change needed.

- **No fake or sample data.** `ENABLE_SAMPLE_DATA` is `false` by default and
  is enforced: the backend will refuse to start if `APP_ENV=production` and
  `ENABLE_SAMPLE_DATA=true`. All data in the database must come from official
  Saudi Exchange imports.

### Running Migrations

```bash
# Inside Docker (recommended)
docker compose exec backend alembic upgrade head

# Verify state
docker compose exec backend alembic current
docker compose exec backend alembic history
```

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Linux VPS | Ubuntu 22.04 LTS or Debian 12 recommended |
| Location | Saudi Arabia, UAE, Bahrain, or any GCC region |
| RAM | 2 GB minimum, 4 GB recommended |
| Disk | 20 GB minimum (more if storing XBRL files) |
| Domain | A domain pointed to the server's IP (for SSL) |
| Docker | v24+ with Docker Compose v2+ |
| Port 80/443 | Open in firewall/security group |

---

## 1. Server Setup

```bash
# Update packages
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Verify
docker --version
docker compose version
```

---

## 2. Clone the Repository

```bash
git clone https://github.com/your-org/mejhr-platform.git
cd mejhr-platform
```

---

## 3. Configure Environment Variables

```bash
cp .env.production.example .env
nano .env   # fill in every <CHANGE> value
```

Critical values to set:

```dotenv
DOMAIN=mejhr.example.sa           # your real domain
POSTGRES_PASSWORD=<strong random>
DATABASE_URL=postgresql+asyncpg://mejhr_user:<password>@db:5432/mejhr_db
DATABASE_URL_SYNC=postgresql://mejhr_user:<password>@db:5432/mejhr_db
SECRET_KEY=<64-char random hex>
APP_ENV=production
ENABLE_SAMPLE_DATA=false           # must be false — enforced at startup
```

Generate secrets:
```bash
python3 -c "import secrets; print(secrets.token_hex(64))"
```

---

## 4. Configure Nginx

```bash
# Edit the domain name in the nginx config
nano deploy/nginx.conf
# Replace all occurrences of "mejhr.example.sa" with your real domain
```

---

## 5. Obtain TLS Certificate

```bash
# Install certbot
sudo apt install -y certbot

# Obtain certificate (standalone mode — nginx not running yet)
sudo certbot certonly --standalone -d mejhr.example.sa

# Certificates will be at:
#   /etc/letsencrypt/live/mejhr.example.sa/fullchain.pem
#   /etc/letsencrypt/live/mejhr.example.sa/privkey.pem
```

---

## 6. Create Storage Directory

```bash
sudo mkdir -p /storage/logs
sudo chown -R $USER:$USER /storage
```

---

## 7. Build and Start Services

```bash
# Build images
docker compose -f deploy/docker-compose.prod.yml build

# Start in detached mode
docker compose -f deploy/docker-compose.prod.yml up -d

# Check all services are running
docker compose -f deploy/docker-compose.prod.yml ps
```

Expected output — all services should show `healthy` or `running`:
```
NAME              STATUS
mejhr_db          healthy
mejhr_redis       healthy
mejhr_backend     healthy
mejhr_worker      running
mejhr_beat        running
mejhr_frontend    running
mejhr_nginx       running
```

---

## 8. Run Database Migrations

```bash
docker compose -f deploy/docker-compose.prod.yml exec backend \
    alembic upgrade head
```

---

## 9. Validate Environment

```bash
# Full environment validation (DB, Redis, storage, Saudi Exchange)
docker compose -f deploy/docker-compose.prod.yml exec backend \
    python -m app.pipeline.exchange.validate_environment
```

Expected output on a healthy GCC server:
```
[OK ] database
[OK ] redis
[OK ] storage
[OK ] saudi_exchange_reachable       ← should be True on GCC server
[OK ] saudi_exchange_akamai_block    ← blocked=False on GCC server
[WRN] companies_endpoint             ← still unverified (see step 10)
[OK ] sample_data_disabled
```

---

## 10. Verify the Companies Endpoint

The companies endpoint path needs to be confirmed from an unblocked environment.

```bash
# Step 1: Run the endpoint probe (from GCC server only)
docker compose -f deploy/docker-compose.prod.yml exec backend \
    python -m app.pipeline.exchange.endpoint_probe
```

If the default path returns HTML (not JSON), you need to find the correct path:

1. Open `https://www.saudiexchange.sa` in a browser.
2. Go to **Markets → All Shares** or **Listed Companies**.
3. Open **DevTools → Network → XHR/Fetch**.
4. Find the JSON request that loads the company list.
5. Copy the path (e.g. `/api/market/companies`).
6. Update `.env`:
   ```dotenv
   SAUDI_EXCHANGE_COMPANIES_PATH=/api/market/companies
   ```
7. Restart the backend:
   ```bash
   docker compose -f deploy/docker-compose.prod.yml restart backend worker
   ```
8. Re-run the probe to confirm:
   ```bash
   docker compose -f deploy/docker-compose.prod.yml exec backend \
       python -m app.pipeline.exchange.endpoint_probe
   ```

---

## 11. Import Companies

Once the endpoint is confirmed and reachable:

```bash
# Manual trigger
docker compose -f deploy/docker-compose.prod.yml exec backend \
    python -m app.pipeline.exchange.companies
```

Or via the API:
```bash
curl -X POST https://mejhr.example.sa/api/v1/jobs/trigger \
    -H "Authorization: Bearer <admin-token>" \
    -H "Content-Type: application/json" \
    -d '{"job_type": "fetch_companies"}'
```

The Celery beat scheduler will also run this automatically at **06:00 Riyadh time** daily.

---

## 12. Health Checks

```bash
# Basic app health
curl -s https://mejhr.example.sa/api/v1/health/ | python3 -m json.tool

# Saudi Exchange connectivity
curl -s "https://mejhr.example.sa/api/v1/system/saudi-exchange-health" \
    | python3 -m json.tool

# Saudi Exchange + companies path probe
curl -s "https://mejhr.example.sa/api/v1/system/saudi-exchange-health?probe_companies=true" \
    | python3 -m json.tool
```

---

## 13. Logs

```bash
# Backend logs
docker compose -f deploy/docker-compose.prod.yml logs -f backend

# Worker logs
docker compose -f deploy/docker-compose.prod.yml logs -f worker
# or
tail -f /storage/logs/celery-worker.log

# Beat logs
tail -f /storage/logs/celery-beat.log

# Nginx logs
docker compose -f deploy/docker-compose.prod.yml exec nginx \
    tail -f /var/log/nginx/mejhr_access.log
```

---

## 14. Backups

### PostgreSQL

```bash
# Create a dump
docker compose -f deploy/docker-compose.prod.yml exec db \
    pg_dump -U mejhr_user mejhr_db > /backups/mejhr_$(date +%Y%m%d_%H%M%S).sql.gz

# Restore from dump
docker compose -f deploy/docker-compose.prod.yml exec -T db \
    psql -U mejhr_user mejhr_db < /backups/mejhr_YYYYMMDD_HHMMSS.sql.gz
```

Add a cron job for automated daily backups:
```bash
crontab -e
# Add:
# 0 3 * * * docker compose -f /home/user/mejhr-platform/deploy/docker-compose.prod.yml exec -T db pg_dump -U mejhr_user mejhr_db | gzip > /backups/mejhr_$(date +\%Y\%m\%d).sql.gz
```

### Storage (XBRL files)

```bash
# Backup storage volume
tar -czf /backups/storage_$(date +%Y%m%d).tar.gz /storage
```

---

## 15. TLS Certificate Renewal

Let's Encrypt certificates expire every 90 days. Set up auto-renewal:

```bash
# Test renewal
sudo certbot renew --dry-run

# Add to crontab (runs twice daily, renews when <30 days remaining)
crontab -e
# Add:
# 0 0,12 * * * sudo certbot renew --quiet && docker compose -f /path/to/deploy/docker-compose.prod.yml restart nginx
```

---

## 16. Updating the Application

```bash
git pull origin main
docker compose -f deploy/docker-compose.prod.yml build
docker compose -f deploy/docker-compose.prod.yml up -d
docker compose -f deploy/docker-compose.prod.yml exec backend alembic upgrade head
```

---

## Production Checklist

Before going live, verify every item:

- [ ] `APP_ENV=production` in `.env`
- [ ] `ENABLE_SAMPLE_DATA=false` in `.env`
- [ ] `DEBUG=false` in `.env`
- [ ] Strong `POSTGRES_PASSWORD` (not default)
- [ ] Strong `SECRET_KEY` (64-char random hex)
- [ ] `DOMAIN` set to real domain
- [ ] TLS certificate obtained and nginx config updated
- [ ] `docker compose ps` shows all services healthy
- [ ] `alembic upgrade head` completed with no errors
- [ ] `validate_environment` shows no critical failures
- [ ] Saudi Exchange reachable (`reachable: true` in health endpoint)
- [ ] Akamai not blocking (`blocked_by_akamai: false`)
- [ ] `endpoint_probe` found the correct companies JSON path
- [ ] `SAUDI_EXCHANGE_COMPANIES_PATH` updated to verified path
- [ ] First manual companies import ran successfully
- [ ] `GET /api/v1/companies/` returns company records (not empty list)
- [ ] Nginx access log shows expected traffic
- [ ] Daily backup cron job configured
- [ ] TLS renewal cron job configured
- [ ] Celery beat scheduled tasks running (check worker logs)

---

## Exact Commands to Run on the GCC Server (in order)

```bash
# 1. Clone
git clone https://github.com/your-org/mejhr-platform.git
cd mejhr-platform

# 2. Configure
cp .env.production.example .env && nano .env

# 3. TLS
sudo certbot certonly --standalone -d your-domain.sa

# 4. Build and start
docker compose -f deploy/docker-compose.prod.yml build
docker compose -f deploy/docker-compose.prod.yml up -d

# 5. Migrations
docker compose -f deploy/docker-compose.prod.yml exec backend alembic upgrade head

# 6. Validate
docker compose -f deploy/docker-compose.prod.yml exec backend \
    python -m app.pipeline.exchange.validate_environment

# 7. Connectivity test
docker compose -f deploy/docker-compose.prod.yml exec backend \
    python -m app.pipeline.exchange.connectivity

# 8. Endpoint probe
docker compose -f deploy/docker-compose.prod.yml exec backend \
    python -m app.pipeline.exchange.endpoint_probe

# 9. Update SAUDI_EXCHANGE_COMPANIES_PATH if probe found a JSON path
nano .env
docker compose -f deploy/docker-compose.prod.yml restart backend worker

# 10. Import companies
docker compose -f deploy/docker-compose.prod.yml exec backend \
    python -m app.pipeline.exchange.companies

# 11. Verify via API
curl -s https://your-domain.sa/api/v1/companies/ | python3 -m json.tool
```
