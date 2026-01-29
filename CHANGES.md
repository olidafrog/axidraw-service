# AxiDraw Service - Security and Code Quality Fixes

**Date:** 2025-01-14  
**Summary:** Fixed critical and high-priority issues identified in code review.

---

## Changes Made

### 1. ✅ Fixed Missing Import in worker.py
- **File:** `src/queue/worker.py`
- **Change:** Added `from typing import Optional` import
- **Impact:** Fixes NameError when `Optional[asyncio.Task]` type hint is evaluated

### 2. ✅ Fixed Blocking Subprocess in controller.py
- **File:** `src/plotter/controller.py`
- **Change:** Replaced `subprocess.run()` with `asyncio.create_subprocess_exec()` in `check_connection()`
- **Impact:** Prevents blocking the event loop during AxiDraw connection checks
- **Details:** Added proper timeout handling with `asyncio.wait_for()` and process cleanup

### 3. ✅ Fixed Path Traversal Vulnerability in jobs.py
- **File:** `src/api/routes/jobs.py`
- **Change:** Moved path validation BEFORE file write operation
- **Impact:** Prevents malicious filenames from being written to disk before validation
- **Details:** Path resolution and `is_relative_to()` check now happens before `aiofiles.open()`

### 4. ✅ Added JSON Validation in worker.py
- **File:** `src/queue/worker.py`
- **Change:** Added try/catch around `json.loads(next_job.parameters)`
- **Impact:** Gracefully handles malformed JSON parameters, marks job as FAILED with error message
- **Details:** Also moved json import to top of file

### 5. ✅ Added Rate Limiting
- **Files:** `src/api/main.py`, `src/api/routes/jobs.py`, `src/config.py`, `requirements.txt`
- **Change:** Integrated slowapi for API rate limiting
- **Impact:** Protects against abuse and DoS attacks
- **Details:** 
  - Added slowapi==0.1.9 to requirements
  - Configurable via `RATE_LIMIT_ENABLED`, `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW` env vars
  - Default: 100 requests/minute on job submission endpoint

### 6. ✅ Added File Cleanup
- **File:** `src/queue/worker.py`
- **Change:** Added automatic cleanup of uploaded SVG files after job completion
- **Impact:** Prevents disk space exhaustion from accumulated uploads
- **Details:** Files are deleted after both successful and failed jobs; errors logged but don't fail job

### 7. ✅ Fixed API Key Comparison (Timing Attack Prevention)
- **File:** `src/api/dependencies.py`
- **Change:** Replaced `api_key != settings.api_key` with `secrets.compare_digest()`
- **Impact:** Prevents timing attacks that could leak API key via response time analysis

### 8. ✅ Added Database Indexes
- **File:** `src/queue/database.py`
- **Change:** Added indexes on `status` and `created_at` columns, plus composite index
- **Impact:** Significantly improves query performance for job listing and queue operations
- **Details:**
  - `ix_jobs_status` - index on status column
  - `ix_jobs_created_at` - index on created_at column  
  - `ix_jobs_status_created_at` - composite index for common query pattern

### 9. ✅ Fixed Datetime Handling (Timezone-Aware)
- **Files:** `src/queue/database.py`, `src/queue/manager.py`
- **Change:** Replaced deprecated `datetime.utcnow()` with timezone-aware `datetime.now(timezone.utc)`
- **Impact:** Fixes deprecation warnings and ensures consistent timezone handling
- **Details:** Created `utc_now()` helper function; updated all datetime column definitions to use `timezone=True`

### 10. ✅ Enhanced Input Validation
- **File:** `src/api/models.py`
- **Change:** Enhanced `JobParameters` Pydantic model with stricter validation
- **Impact:** Prevents invalid/malicious parameter values
- **Details:**
  - `layers`: Added regex pattern to allow only digits, commas, spaces; max 100 chars
  - `pen_up_delay`/`pen_down_delay`: Added max limit of 5000ms
  - `timeout`: Added new field with range 60-86400 seconds (1 min to 24 hours)

---

## Files Modified

| File | Changes |
|------|---------|
| `src/queue/worker.py` | Added Optional import, JSON validation, file cleanup |
| `src/plotter/controller.py` | Async subprocess for connection check |
| `src/api/routes/jobs.py` | Path validation order, rate limiting |
| `src/api/dependencies.py` | Constant-time API key comparison |
| `src/queue/database.py` | Timezone-aware datetime, database indexes |
| `src/queue/manager.py` | Updated datetime calls |
| `src/api/main.py` | Rate limiting middleware |
| `src/api/models.py` | Enhanced parameter validation |
| `src/config.py` | Rate limiting settings |
| `requirements.txt` | Added slowapi dependency |

---

## Issues Not Fixed

**None** - All 10 identified issues were successfully addressed.

---

## Next Steps for Testing

1. **Unit Tests:** Run existing tests to verify no regressions
   ```bash
   pytest tests/ -v
   ```

2. **Rate Limiting Test:**
   ```bash
   # Send rapid requests to verify rate limiting
   for i in {1..110}; do curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/api/jobs; done
   # Should see 429 responses after 100 requests
   ```

3. **Path Traversal Test:**
   ```bash
   # Attempt path traversal (should fail)
   curl -X POST -F "file=@test.svg;filename=../../../etc/passwd" http://localhost:8080/api/jobs
   ```

4. **API Key Timing Test:**
   ```bash
   # Verify constant-time comparison (response times should be similar)
   API_KEY=wrong1 time curl -H "X-API-Key: $API_KEY" http://localhost:8080/api/jobs
   API_KEY=wrong2longer time curl -H "X-API-Key: $API_KEY" http://localhost:8080/api/jobs
   ```

5. **Database Migration:**
   ```bash
   # For existing databases, indexes may need to be added manually or via Alembic migration
   # The new indexes will be created automatically for new databases
   ```

6. **Datetime Verification:**
   ```bash
   # Check that timestamps are timezone-aware in API responses
   curl http://localhost:8080/api/jobs | jq '.[] | .created_at'
   # Should show ISO format with timezone info
   ```

7. **File Cleanup Test:**
   ```bash
   # Submit job, wait for completion, verify upload file is deleted
   ls -la /data/uploads/  # Should be cleaned up after job completes
   ```

---

## Recommended Future Improvements

1. Add Alembic for database migrations
2. Add comprehensive integration tests
3. Consider adding request signing for additional security
4. Add Prometheus metrics for monitoring rate limit hits
5. Consider adding file type validation beyond extension checking (magic bytes)
