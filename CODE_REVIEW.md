# Code Review: AxiDraw Service

**Review Date:** January 2025  
**Reviewed By:** Automated Code Review  
**Repository:** axidraw-service  
**Overall Risk Level:** 🟡 MODERATE - Ready for limited production use with recommendations

---

## Executive Summary

The AxiDraw Service is a well-structured FastAPI application for controlling a pen plotter via REST API. The codebase demonstrates good understanding of modern Python async patterns and follows reasonable architectural separation. However, several security, reliability, and production-readiness issues need attention before widespread deployment.

### Quick Stats
- **Lines of Code:** ~800 (Python)
- **Test Coverage:** 0% ⚠️
- **Security Issues:** 3 Critical, 2 Medium
- **Technical Debt:** Medium

---

## 🔴 Critical Issues (Must Fix)

### 1. No Authentication/Authorization
**Location:** All API endpoints  
**Risk:** HIGH - Any network user can control the plotter

```python
# Current: No authentication
@router.post("", response_model=JobSubmitResponse)
async def submit_job(file: UploadFile = File(...)):
    ...
```

**Recommendation:** Implement API key authentication at minimum:

```python
# src/api/dependencies.py
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key

# In routes:
@router.post("", dependencies=[Depends(verify_api_key)])
async def submit_job(...):
    ...
```

Add to config:
```python
api_key: str = Field(default=None, description="API key for authentication")
```

---

### 2. Path Traversal Vulnerability in File Upload
**Location:** `src/api/routes/jobs.py:50-60`  
**Risk:** HIGH - Malicious filenames could write outside uploads directory

```python
# VULNERABLE: Uses user-provided filename directly
filename = file.filename  # Could be "../../../etc/passwd"
filepath = settings.uploads_dir / filename
```

**Recommendation:** Sanitize filenames:

```python
import re
from pathlib import Path

def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal attacks."""
    # Remove path separators and null bytes
    filename = filename.replace('/', '_').replace('\\', '_').replace('\0', '')
    # Keep only safe characters
    filename = re.sub(r'[^\w\-_\. ]', '_', filename)
    # Get just the filename part (no directory)
    filename = Path(filename).name
    # Ensure it's not empty
    if not filename or filename.startswith('.'):
        filename = f"upload_{uuid.uuid4().hex[:8]}.svg"
    return filename

# In submit_job:
filename = sanitize_filename(file.filename)
filepath = settings.uploads_dir / filename
# Verify resolved path is within uploads_dir
if not filepath.resolve().is_relative_to(settings.uploads_dir.resolve()):
    raise HTTPException(status_code=400, detail="Invalid filename")
```

---

### 3. Blocking Subprocess in Async Context
**Location:** `src/plotter/controller.py:85-100`  
**Risk:** HIGH - Blocks entire event loop during plotting

```python
# BLOCKING: process.communicate() blocks the event loop
process = subprocess.Popen(...)
stdout, stderr = process.communicate(timeout=parameters.get("timeout", 3600))
```

**Recommendation:** Use asyncio subprocess:

```python
import asyncio

async def plot_svg(self, svg_path: Path, job_id: str, parameters: Dict[str, Any], 
                   progress_callback=None) -> bool:
    # ... validation code ...
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=parameters.get("timeout", 3600)
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            logger.error(f"Job {job_id} timed out")
            self.state = PlotterState.ERROR
            return False
        
        # ... rest of handling ...
```

---

## 🟠 Medium Issues (Should Fix)

### 4. CORS Wildcard in Production
**Location:** `src/api/main.py:47-52`  
**Risk:** MEDIUM - Allows any origin to make requests

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # Default: ["*"]
    allow_credentials=True,  # Dangerous with wildcard origins
    ...
)
```

**Recommendation:** Configure explicit origins:

```python
# config.py
cors_origins: list[str] = Field(
    default=["http://localhost:3080"],  # Pi dashboard only
    description="Allowed CORS origins"
)

# main.py - validate credentials setting
if "*" in settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,  # Must be False with wildcard
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

---

### 5. SVG Content Not Validated
**Location:** `src/api/routes/jobs.py:37-45`  
**Risk:** MEDIUM - Malicious SVG could cause parsing issues or exploits

```python
# Only checks extension, not content
if not file.filename.lower().endswith('.svg'):
    raise HTTPException(status_code=400, detail="Only SVG files are supported")
```

**Recommendation:** Validate SVG structure:

```python
import xml.etree.ElementTree as ET

def validate_svg(content: bytes) -> bool:
    """Validate that content is a valid SVG file."""
    try:
        root = ET.fromstring(content)
        # Check root element is SVG
        if not root.tag.endswith('svg'):
            return False
        # Check for potentially dangerous elements
        dangerous_tags = ['script', 'foreignObject', 'iframe']
        for tag in dangerous_tags:
            if root.find(f'.//{{{*}}}{tag}') is not None:
                logger.warning(f"SVG contains potentially dangerous element: {tag}")
        return True
    except ET.ParseError:
        return False

# In submit_job:
if not validate_svg(content):
    raise HTTPException(status_code=400, detail="Invalid SVG file")
```

---

## 🟡 Minor Issues (Nice to Fix)

### 6. Missing Type Hint for Optional in Worker
**Location:** `src/queue/worker.py:14`

```python
# Missing import and type hint
self.task: Optional[asyncio.Task] = None  # 'Optional' not imported
```

**Fix:**
```python
from typing import Optional
```

---

### 7. Error Response Not Using JSONResponse
**Location:** `src/api/main.py:73-84`

```python
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return {  # Should use JSONResponse
        "error": "Not found",
        ...
    }
```

**Fix:**
```python
from fastapi.responses import JSONResponse

@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"error": "Not found", "detail": str(exc.detail) if hasattr(exc, 'detail') else "Resource not found"}
    )
```

---

### 8. Hardcoded Sleep Intervals
**Location:** `src/queue/worker.py:46, 54`

```python
await asyncio.sleep(5)  # Should be configurable
```

**Recommendation:** Add to config:
```python
worker_poll_interval: int = Field(default=5, description="Worker poll interval in seconds")
```

---

### 9. Database Session Not Committed on Update
**Location:** `src/queue/manager.py:76-94`

The `update_job_status` method commits properly, but could benefit from explicit error handling:

```python
async def update_job_status(self, session: AsyncSession, job_id: str, 
                            status: JobStatus, ...) -> Optional[Job]:
    try:
        job = await self.get_job(session, job_id)
        if not job:
            return None
        # ... updates ...
        await session.commit()
        await session.refresh(job)
        return job
    except Exception as e:
        await session.rollback()
        logger.error(f"Failed to update job {job_id}: {e}")
        raise
```

---

### 10. Incomplete Cancel Implementation
**Location:** `src/plotter/controller.py:121-124`

```python
async def cancel(self) -> bool:
    """Cancel current plotting job"""
    # Would need to track subprocess and kill it
    logger.warning("Cancel not yet implemented")
    return False
```

**Recommendation:** Store process reference and implement cancellation:

```python
class AxiDrawController:
    def __init__(self):
        # ... existing ...
        self._current_process: Optional[asyncio.subprocess.Process] = None

    async def cancel(self) -> bool:
        """Cancel current plotting job"""
        if self._current_process and self._current_process.returncode is None:
            self._current_process.terminate()
            try:
                await asyncio.wait_for(self._current_process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._current_process.kill()
            self.state = PlotterState.IDLE
            self.current_job_id = None
            return True
        return False
```

---

## ✅ Positive Highlights

### Well-Implemented Patterns

1. **Clean Architecture Separation**
   - Clear separation between API, queue, and plotter layers
   - Models properly defined with Pydantic
   - Good use of dependency injection for sessions

2. **Async-First Design**
   - Proper use of `asynccontextmanager` for lifespan
   - Async database operations with SQLAlchemy 2.0
   - Background worker using `asyncio.Task`

3. **Robust Job Queue**
   - FIFO ordering with SQLite persistence
   - Queue position tracking
   - Proper status transitions

4. **Good Docker Configuration**
   - Non-root user for security
   - Health check configured
   - Proper volume mounts for data persistence
   - Device passthrough for USB access

5. **Comprehensive Documentation**
   - Excellent README with architecture diagram
   - Detailed deployment guide
   - Troubleshooting section

6. **Configuration Management**
   - Pydantic Settings for type-safe config
   - Environment variable support
   - Sensible defaults

---

## 🧪 Testing Gap Analysis

**Current State:** No tests exist ⚠️

### Recommended Test Structure:

```
tests/
├── conftest.py           # Fixtures
├── test_api/
│   ├── test_jobs.py      # Job submission, listing, deletion
│   ├── test_plotter.py   # Plotter status, pause/resume
│   └── test_health.py    # Health endpoint
├── test_queue/
│   ├── test_manager.py   # Queue operations
│   └── test_worker.py    # Worker processing
└── test_plotter/
    └── test_controller.py # Mock AxiCLI tests
```

### Priority Tests to Add:

```python
# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

@pytest.fixture
async def test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest.fixture
def client(test_db):
    # Override dependencies
    app.dependency_overrides[get_session] = lambda: test_db
    return TestClient(app)

# tests/test_api/test_jobs.py
def test_submit_job_validates_svg_extension(client):
    response = client.post(
        "/api/jobs",
        files={"file": ("test.txt", b"not an svg", "text/plain")}
    )
    assert response.status_code == 400
    assert "Only SVG files" in response.json()["detail"]

def test_submit_job_checks_file_size(client, settings):
    large_content = b"<svg></svg>" + b"x" * (settings.max_svg_size_mb * 1024 * 1024 + 1)
    response = client.post(
        "/api/jobs",
        files={"file": ("large.svg", large_content, "image/svg+xml")}
    )
    assert response.status_code == 413
```

---

## 📦 Dependencies Review

### requirements.txt Analysis

| Package | Version | Status | Notes |
|---------|---------|--------|-------|
| fastapi | 0.104.1 | ⚠️ Update | 0.115+ available |
| uvicorn | 0.24.0 | ⚠️ Update | 0.34+ available |
| pydantic | 2.5.0 | ⚠️ Update | 2.10+ available |
| sqlalchemy | 2.0.23 | ✅ OK | Recent |
| aiofiles | 23.2.1 | ✅ OK | Recent |
| aiosqlite | 0.19.0 | ⚠️ Update | 0.21+ available |
| AxiDraw_API | zip URL | ⚠️ Risky | No version pinning |

### Recommendations:

1. **Pin AxiDraw dependency properly:**
```txt
# Option 1: Pin specific version (if available on PyPI)
pyaxidraw==3.9.0

# Option 2: Use git tag
git+https://github.com/evil-mad/axidraw.git@v3.9.0#egg=pyaxidraw
```

2. **Add security scanning:**
```yaml
# .github/workflows/security.yml
- name: Run safety check
  run: pip install safety && safety check -r requirements.txt
```

3. **Add missing dev dependencies:**
```txt
# requirements-dev.txt
pytest==8.0.0
pytest-asyncio==0.23.0
httpx==0.27.0  # For async test client
black==24.1.0
ruff==0.1.14
mypy==1.8.0
```

---

## 🐳 Docker & Deployment Review

### Dockerfile Issues

1. **No multi-stage build** - Image larger than necessary
2. **Missing .env support** - Consider python-dotenv

### Recommended Dockerfile Improvements:

```dockerfile
# Multi-stage build for smaller image
FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.11-slim

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libusb-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy wheels and install
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

COPY src/ ./src/

# Create directories and user
RUN mkdir -p /data/uploads \
    && groupadd -r axidraw \
    && useradd -r -g axidraw axidraw \
    && chown -R axidraw:axidraw /app /data

ENV PYTHONUNBUFFERED=1
EXPOSE 8080
USER axidraw

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health')" || exit 1

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### docker-compose.yml Improvements:

```yaml
version: '3.8'

services:
  axidraw-service:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: axidraw-service
    ports:
      - "127.0.0.1:8080:8080"  # Bind to localhost only
    volumes:
      - ./data:/data
      - /etc/localtime:/etc/localtime:ro  # Sync timezone
    devices:
      - /dev/ttyACM0:/dev/ttyACM0
    environment:
      - DATA_DIR=/data
      - LOG_LEVEL=INFO
      - API_KEY=${API_KEY}  # Add authentication
    restart: unless-stopped
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    deploy:
      resources:
        limits:
          memory: 256M
```

---

## 📊 Action Items Summary

### Immediate (Before Production)
| Priority | Issue | Effort |
|----------|-------|--------|
| 🔴 P0 | Add API authentication | 2-4 hours |
| 🔴 P0 | Fix path traversal vulnerability | 1 hour |
| 🔴 P0 | Fix blocking subprocess | 2-3 hours |

### Short-term (Next Sprint)
| Priority | Issue | Effort |
|----------|-------|--------|
| 🟠 P1 | Add basic test suite | 4-8 hours |
| 🟠 P1 | Fix CORS configuration | 30 min |
| 🟠 P1 | Add SVG validation | 2 hours |
| 🟠 P1 | Update dependencies | 1 hour |

### Medium-term (Backlog)
| Priority | Issue | Effort |
|----------|-------|--------|
| 🟡 P2 | Implement cancel functionality | 2-4 hours |
| 🟡 P2 | Add progress streaming (WebSocket) | 4-8 hours |
| 🟡 P2 | Multi-stage Docker build | 1 hour |
| 🟡 P2 | Add rate limiting | 2 hours |

---

## Conclusion

The AxiDraw Service demonstrates solid engineering fundamentals with clean architecture, modern Python patterns, and good documentation. However, **it should NOT be exposed to untrusted networks** in its current state due to the authentication and path traversal vulnerabilities.

For a Raspberry Pi deployment on a trusted home network with Tailscale, the risk is manageable, but implementing API key authentication is strongly recommended before adding dashboard integration.

**Recommended next steps:**
1. Fix the three critical security issues
2. Add a minimal test suite
3. Update dependencies
4. Consider adding rate limiting for production use

---

*Review generated with assistance from automated code analysis tools.*
