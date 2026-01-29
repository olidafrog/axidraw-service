# AxiDraw Service Deployment Guide

## Initial Setup on Raspberry Pi

### 1. Clone the Repository

```bash
cd /home/admin/projects
git clone https://github.com/olidafrog/axidraw-service.git
cd axidraw-service
```

### 2. Create Data Directory

```bash
sudo mkdir -p /opt/data/axidraw/uploads
sudo chown -R admin:admin /opt/data/axidraw
```

### 3. Identify USB Device

Connect the AxiDraw and identify the device:

```bash
# List USB devices
ls -l /dev/tty* | grep -E "(ACM|USB)"

# Common devices:
# - /dev/ttyACM0 (most common for AxiDraw)
# - /dev/ttyUSB0 (alternative)

# Check device permissions
ls -l /dev/ttyACM0
```

If the device is different from `/dev/ttyACM0`, update `docker-compose.yml` in `/opt/docker/`:

```yaml
devices:
  - /dev/ttyUSB0:/dev/ttyUSB0  # Change here
```

### 4. Add User to dialout Group

For USB access without privileged mode:

```bash
sudo usermod -a -G dialout admin
# Log out and back in, or:
newgrp dialout
```

### 5. Initial Build and Start

```bash
cd /opt/docker
docker-compose up -d --build axidraw-service
```

### 6. Verify Service

```bash
# Check container status
docker ps | grep axidraw

# Check logs
docker logs axidraw-service

# Test API
curl http://localhost:8080/api/health
```

Expected response:
```json
{
  "status": "healthy",
  "uptime": 10,
  "queue_size": 0,
  "plotter_connected": true,
  "version": "1.0.0",
  "timestamp": "2024-01-01T00:00:00"
}
```

## GitHub Repository Setup

### 1. Create GitHub Repository

```bash
# On your local machine
cd axidraw-service
git init
git add .
git commit -m "Initial commit: AxiDraw service"

# Create repo on GitHub: olidafrog/axidraw-service
git remote add origin https://github.com/olidafrog/axidraw-service.git
git branch -M master  # Note: This repo uses 'master' branch
git push -u origin master
```

### 2. Add Secrets

Add these secrets to the GitHub repository (Settings → Secrets and variables → Actions):

| Secret | Description | Notes |
|--------|-------------|-------|
| `TS_OAUTH_CLIENT_ID` | Tailscale OAuth client ID | Shared across services |
| `TS_OAUTH_SECRET` | Tailscale OAuth secret | Shared across services |
| `PI_SSH_KEY` | SSH private key for Pi access | Shared across services |

These should already exist from other services (kindle-sync-server, invoice-generator, etc.).

### 3. Test Auto-Deploy

```bash
# Make a change and push
echo "# Test" >> README.md
git add README.md
git commit -m "Test auto-deploy"
git push origin master
```

Watch GitHub Actions and check Pi:
```bash
ssh admin@100.103.87.83
docker logs axidraw-service
```

### 4. Manual Workflow Trigger

You can also trigger deployment manually via GitHub Actions:
1. Go to Actions tab in the repository
2. Select "Deploy to Pi" workflow
3. Click "Run workflow"
4. Optionally enable "Force rebuild" if needed

## Updating the Service

### Manual Update

```bash
ssh admin@100.103.87.83
/opt/scripts/update-projects.sh axidraw-service
```

### Automatic Update

Push to `master` branch - GitHub Actions will deploy automatically.

## CI/CD Pipeline Details

### Workflow Features

The deployment workflow (`.github/workflows/deploy.yml`) includes:

1. **Branch trigger**: Deploys on push to `master` branch
2. **Tailscale connection**: Establishes secure tunnel to Pi
3. **SSH deployment**: Runs update-projects.sh on the Pi
4. **Health verification**: Checks `/api/health` endpoint after deployment
5. **Rollback on failure**: Automatically reverts to previous commit if deployment fails
6. **Failure diagnostics**: Collects container logs on failure

### Deployment Flow

```
GitHub Push → Tailscale Connect → SSH to Pi → update-projects.sh → Health Check → ✓
                                                      ↓
                                            [If fails: Rollback]
```

### What update-projects.sh Does

1. Pulls latest code to `/home/admin/projects/axidraw-service`
2. Runs `docker compose up -d --build axidraw-service` from `/opt/docker/`
3. The docker-compose.yml in `/opt/docker/` defines the service configuration

### Deployment Locations

| Location | Purpose |
|----------|---------|
| `/home/admin/projects/axidraw-service` | Source code (git repo) |
| `/opt/docker/docker-compose.yml` | Service orchestration (from rpi-config) |
| `/opt/data/axidraw` | Persistent data (jobs.db, uploads) |
| `/opt/scripts/update-projects.sh` | Deployment script (from rpi-config) |

## Configuration

### Environment Variables

Edit `/opt/docker/docker-compose.yml`:

```yaml
environment:
  - DATA_DIR=/data
  - LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
  - AXIDRAW_DEVICE=/dev/ttyACM0
```

Then restart:
```bash
docker-compose up -d --build axidraw-service
```

### Resource Limits

Adjust memory if needed:

```yaml
deploy:
  resources:
    limits:
      memory: 256M  # Increase if needed
```

## Monitoring

### Check Service Status

```bash
# Docker status
docker ps | grep axidraw

# Logs (last 100 lines)
docker logs --tail 100 axidraw-service

# Follow logs
docker logs -f axidraw-service

# Container stats
docker stats axidraw-service
```

### API Health Check

```bash
curl http://localhost:8080/api/health
```

### Pi Dashboard

The service should appear in the pi-dashboard at http://pi-ip:3080

## Troubleshooting

### Issue: AxiDraw Not Detected

**Symptoms:**
- `plotter_connected: false` in health check
- "AxiDraw not detected" in logs

**Solutions:**

1. **Check USB connection:**
   ```bash
   lsusb | grep -i "EiBotBoard\|AxiDraw"
   ls -l /dev/ttyACM*
   ```

2. **Verify device permissions:**
   ```bash
   ls -l /dev/ttyACM0
   # Should show: crw-rw---- 1 root dialout
   ```

3. **Check dialout group:**
   ```bash
   groups admin
   # Should include: admin dialout docker
   ```

4. **Restart container:**
   ```bash
   docker-compose restart axidraw-service
   ```

5. **Test AxiCLI directly:**
   ```bash
   docker exec -it axidraw-service python -m axicli --version
   ```

### Issue: Container Won't Start

**Check logs:**
```bash
docker logs axidraw-service
```

**Common causes:**
- USB device not found → Update device path in docker-compose.yml
- Port conflict (8080) → Change port mapping
- Permission issues → Check file permissions on /opt/data/axidraw

**Rebuild from scratch:**
```bash
docker-compose down
docker-compose up -d --build axidraw-service
```

### Issue: Jobs Stuck in Queue

**Check worker status:**
```bash
docker logs axidraw-service | grep -i worker
```

**Check plotter state:**
```bash
curl http://localhost:8080/api/plotter/status
```

**Restart service:**
```bash
docker-compose restart axidraw-service
```

### Issue: 503 Service Unavailable

**Check if container is running:**
```bash
docker ps | grep axidraw
```

**Check network:**
```bash
docker network inspect docker_default
# Verify axidraw-service is in the network
```

**Test from host:**
```bash
curl http://localhost:8080/api/health
```

## Backup and Restore

### Backup Job Database

```bash
# Backup
sudo cp /opt/data/axidraw/jobs.db /opt/data/axidraw/jobs.db.backup

# Restore
sudo cp /opt/data/axidraw/jobs.db.backup /opt/data/axidraw/jobs.db
docker-compose restart axidraw-service
```

### Clear All Jobs

```bash
# Stop service
docker-compose stop axidraw-service

# Remove database
sudo rm /opt/data/axidraw/jobs.db

# Remove uploaded files
sudo rm -rf /opt/data/axidraw/uploads/*
sudo mkdir -p /opt/data/axidraw/uploads

# Start service (will recreate database)
docker-compose up -d axidraw-service
```

## Performance Tuning

### Adjust Queue Size

Edit `src/config.py` and rebuild:
```python
max_queue_size: int = 200  # Default: 100
```

### Adjust Job Timeout

```python
job_timeout_seconds: int = 7200  # Default: 3600 (1 hour)
```

### Reduce Memory Usage

```yaml
deploy:
  resources:
    limits:
      memory: 128M  # Reduce if service is stable
```

## Security Considerations

### Network Isolation

Service is exposed on port 8080. To restrict access:

```yaml
ports:
  - "127.0.0.1:8080:8080"  # Localhost only
```

Then proxy through nginx if external access needed.

### File Upload Size Limits

Adjust in `src/config.py`:
```python
max_svg_size_mb: int = 5  # Default: 10MB
```

### API Authentication (Future)

Currently no authentication. To add:
1. Implement API key middleware in FastAPI
2. Add API key to dashboard requests
3. Store API key in environment variable

## Maintenance

### Log Rotation

Docker handles log rotation by default. To adjust:

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

### Database Maintenance

SQLite database is self-maintaining. For large deployments:

```bash
# Vacuum database (optimize)
docker exec -it axidraw-service sqlite3 /data/jobs.db "VACUUM;"

# Check database size
docker exec -it axidraw-service ls -lh /data/jobs.db
```

### Update Docker Base Image

Periodically rebuild to get security updates:

```bash
docker-compose pull  # Pull latest Python base image
docker-compose up -d --build axidraw-service
```

## Advanced: Multi-AxiDraw Setup

To support multiple plotters (future):

1. **Create separate instances:**
   ```yaml
   axidraw-service-1:
     # ... existing config ...
     devices:
       - /dev/ttyACM0:/dev/ttyACM0
     ports:
       - "8080:8080"
   
   axidraw-service-2:
     # ... existing config ...
     devices:
       - /dev/ttyACM1:/dev/ttyACM1
     ports:
       - "8081:8080"
   ```

2. **Load balancer** in dashboard to distribute jobs.

## Support

For issues:
1. Check logs: `docker logs axidraw-service`
2. Check health: `curl http://localhost:8080/api/health`
3. Review GitHub Issues: https://github.com/olidafrog/axidraw-service/issues
4. Consult AxiDraw docs: https://axidraw.com/doc/
