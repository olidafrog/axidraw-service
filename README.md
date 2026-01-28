# AxiDraw Service

REST API service for controlling an AxiDraw pen plotter. Built with FastAPI and Docker, designed to run headlessly on a Raspberry Pi.

## Features

- 📝 **Job Queue System**: Submit SVG files for plotting via REST API
- 🎨 **SVG Support**: Full support for SVG plotting with layer control
- 📊 **Status Monitoring**: Real-time job progress and plotter status
- 🐳 **Docker Ready**: Containerized with USB device passthrough
- 🔄 **Auto-Deploy**: GitHub Actions CI/CD for seamless updates
- 📈 **Dashboard Integration**: Monitored by pi-dashboard

## Quick Start

### Prerequisites

- AxiDraw pen plotter connected via USB
- Docker and Docker Compose installed
- AxiDraw connected at `/dev/ttyACM0` (or update `docker-compose.yml`)

### Local Development

1. **Clone the repository**:
   ```bash
   git clone https://github.com/olidafrog/axidraw-service.git
   cd axidraw-service
   ```

2. **Build and run**:
   ```bash
   docker-compose up --build
   ```

3. **Access the API**:
   - API docs: http://localhost:8080/docs
   - Health check: http://localhost:8080/api/health

### Production Deployment

The service auto-deploys to the Raspberry Pi when pushing to `main` branch:

```bash
git push origin main
```

GitHub Actions will:
1. Connect to Pi via Tailscale
2. Pull latest code
3. Rebuild and restart the Docker container

## API Documentation

### Submit a Job

```bash
curl -X POST http://localhost:8080/api/jobs \
  -F "file=@drawing.svg" \
  -F "speed=25" \
  -F "layers=1,2"
```

### Get Job Status

```bash
curl http://localhost:8080/api/jobs/{job_id}
```

### List All Jobs

```bash
curl http://localhost:8080/api/jobs
```

### Get Plotter Status

```bash
curl http://localhost:8080/api/plotter/status
```

### Health Check

```bash
curl http://localhost:8080/api/health
```

## Configuration

Environment variables (set in `docker-compose.yml`):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_DIR` | `/data` | Directory for job database and uploads |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `AXIDRAW_DEVICE` | `/dev/ttyACM0` | USB device path for AxiDraw |
| `API_KEY` | (none) | API key for authentication. If set, all requests must include `X-API-Key` header |

### Authentication

For security, you can enable API key authentication by setting the `API_KEY` environment variable:

```yaml
# docker-compose.yml
environment:
  - API_KEY=your-secret-key-here
```

When enabled, all API requests must include the `X-API-Key` header:

```bash
curl -X POST http://localhost:8080/api/jobs \
  -H "X-API-Key: your-secret-key-here" \
  -F "file=@drawing.svg"
```

**Recommended**: Always set an API key when exposing the service to a network, even on Tailscale.

## Job Parameters

When submitting a job, you can specify:

- **layers**: Comma-separated layer IDs to plot (e.g., "1,2,3")
- **speed**: Plotting speed (1-100, default: 25)
- **pen_up_delay**: Pen up delay in milliseconds (default: 150)
- **pen_down_delay**: Pen down delay in milliseconds (default: 150)
- **preview**: Preview mode - validate without plotting (default: false)

## Architecture

```
┌─────────────────┐
│   Pi Dashboard  │ (Monitor service status)
└────────┬────────┘
         │ HTTP
┌────────▼─────────────────────────────┐
│   AxiDraw Service (Docker)           │
│   ┌──────────────────────────────┐   │
│   │  FastAPI REST API            │   │
│   └──────────┬───────────────────┘   │
│   ┌──────────▼───────────────────┐   │
│   │  Job Queue (SQLite)          │   │
│   └──────────┬───────────────────┘   │
│   ┌──────────▼───────────────────┐   │
│   │  Background Worker           │   │
│   └──────────┬───────────────────┘   │
│   ┌──────────▼───────────────────┐   │
│   │  AxiCLI Controller           │   │
│   └──────────┬───────────────────┘   │
└──────────────┼───────────────────────┘
               │ USB
        ┌──────▼──────┐
        │   AxiDraw   │
        └─────────────┘
```

## Directory Structure

```
axidraw-service/
├── src/
│   ├── api/              # FastAPI application
│   │   ├── main.py       # Main app
│   │   ├── models.py     # Pydantic models
│   │   └── routes/       # API endpoints
│   ├── queue/            # Job queue management
│   │   ├── manager.py    # Queue manager
│   │   ├── worker.py     # Background worker
│   │   └── database.py   # SQLite models
│   ├── plotter/          # AxiDraw controller
│   │   └── controller.py # AxiCLI wrapper
│   └── config.py         # Configuration
├── data/                 # Job database and uploads (gitignored)
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Troubleshooting

### AxiDraw Not Detected

1. **Check USB connection**:
   ```bash
   ls -l /dev/ttyACM* /dev/ttyUSB*
   ```

2. **Update device path** in `docker-compose.yml`:
   ```yaml
   devices:
     - /dev/ttyUSB0:/dev/ttyUSB0  # or ttyACM0
   ```

3. **Check permissions**:
   ```bash
   sudo usermod -a -G dialout admin
   ```

### Job Stuck in Queue

Check worker logs:
```bash
docker logs axidraw-service
```

### Container Won't Start

Check logs and rebuild:
```bash
docker logs axidraw-service
docker-compose down
docker-compose up --build
```

## Development

### Running Tests

```bash
# TODO: Add tests
python -m pytest
```

### Manual AxiCLI Testing

Test AxiCLI directly inside the container:
```bash
docker exec -it axidraw-service python -m axicli --version
docker exec -it axidraw-service python -m axicli /data/uploads/test.svg
```

## Future Enhancements

- [ ] Real-time progress streaming via WebSockets
- [ ] SVG preview/thumbnail generation
- [ ] Pause/resume support for running jobs
- [ ] Multi-plotter support
- [ ] Job scheduling
- [ ] Authentication and multi-user support

## License

MIT License - see LICENSE file for details

## Links

- [AxiDraw Documentation](https://axidraw.com/doc/)
- [AxiCLI Documentation](https://axidraw.com/doc/cli_api/)
- [Pi Dashboard](https://github.com/olidafrog/pi-dashboard)
- [Infrastructure Config](https://github.com/olidafrog/rpi-config)
