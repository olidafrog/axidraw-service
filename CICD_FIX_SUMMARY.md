# CI/CD Pipeline Fix Summary

## Overview

Fixed the GitHub Actions deployment workflow for axidraw-service to correctly deploy to the Raspberry Pi.

## Issues Fixed

### 1. ✅ Branch Mismatch (Critical)
**Problem:** Workflow triggered on `main` branch, but repository uses `master` branch.
**Fix:** Changed trigger from `branches: [main]` to `branches: [master]`

### 2. ✅ Missing Deployment Verification
**Problem:** No verification that deployment succeeded.
**Fix:** Added:
- Health check against `/api/health` endpoint
- Container status verification
- Deployment summary in GitHub Actions UI

### 3. ✅ No Error Handling
**Problem:** Deployment failures had no diagnostics or recovery.
**Fix:** Added:
- Tailscale connection verification
- SSH connection test
- Automatic rollback on failure
- Container log collection on failure

### 4. ✅ No Manual Trigger Option
**Problem:** Could only deploy via push to master.
**Fix:** Added `workflow_dispatch` with optional force rebuild input.

## Files Changed

| File | Changes |
|------|---------|
| `.github/workflows/deploy.yml` | Complete rewrite with improvements |
| `DEPLOYMENT.md` | Updated CI/CD documentation section |

## What the New Workflow Does

```
1. Checkout code
2. Validate Dockerfile exists
3. Connect to Tailscale (with verification)
4. Setup SSH agent
5. Test SSH connection
6. Capture current commit (for rollback)
7. Run deployment script
8. Wait for service startup
9. Health check (up to 2 minutes)
10. Verify container status
11. Generate deployment summary

On failure:
- Attempt rollback to previous commit
- Collect container logs
- Add diagnostics to workflow summary
```

## What's Already Correct

1. ✅ **axidraw-service in update-projects.sh** - Already registered in rpi-config
2. ✅ **axidraw-service in docker-compose.yml** - Already configured in /opt/docker/
3. ✅ **Health endpoint** - `/api/health` already exists in the service
4. ✅ **Dockerfile** - Already has HEALTHCHECK directive

## Required GitHub Secrets

These secrets must be configured in the repository (Settings → Secrets → Actions):

| Secret | Description | Status |
|--------|-------------|--------|
| `TS_OAUTH_CLIENT_ID` | Tailscale OAuth client ID | Should exist (shared) |
| `TS_OAUTH_SECRET` | Tailscale OAuth secret | Should exist (shared) |
| `PI_SSH_KEY` | SSH private key for admin@pi | Should exist (shared) |

## Manual Steps Required

### Before First Deployment

1. **Verify secrets exist** in GitHub repo settings
   - Go to: https://github.com/olidafrog/axidraw-service/settings/secrets/actions
   - Confirm all three secrets are present

2. **Verify Pi is accessible** via Tailscale
   ```bash
   tailscale status | grep 100.103.87.83
   ```

3. **Verify project directory exists** on Pi
   ```bash
   ssh admin@100.103.87.83 "ls -la /home/admin/projects/axidraw-service"
   ```

### To Apply These Changes

```bash
cd /tmp/axidraw-service
git add .github/workflows/deploy.yml DEPLOYMENT.md CICD_FIX_SUMMARY.md
git commit -m "fix: CI/CD pipeline - trigger on master, add verification and rollback"
git push origin master
```

This push will trigger the workflow automatically.

## Testing the Workflow

### Option 1: Push to master (automatic)
The commit above will trigger deployment.

### Option 2: Manual trigger
1. Go to Actions tab
2. Select "Deploy to Pi"
3. Click "Run workflow"
4. Select master branch
5. Click "Run workflow"

## Expected Workflow Duration

- Tailscale connection: ~10-30 seconds
- SSH setup: ~5 seconds
- Deployment: ~30-60 seconds
- Health check: ~10-60 seconds
- **Total: ~1-3 minutes**

## Rollback Behavior

If deployment fails:
1. Workflow captures current commit before deployment
2. On failure, reverts to that commit
3. Rebuilds container with previous code
4. Logs are collected for diagnostics

## Monitoring After Deployment

```bash
# Check container status
ssh admin@100.103.87.83 "docker ps | grep axidraw"

# Check logs
ssh admin@100.103.87.83 "docker logs --tail 50 axidraw-service"

# Health check
ssh admin@100.103.87.83 "curl -s http://localhost:8080/api/health | jq"
```
