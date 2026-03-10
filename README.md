# VIN Decoder

Bulk VIN decoding web app for CSV/XLS/XLSX uploads, optimized for lightweight deployment on a Raspberry Pi or a small local server.

## Features

- Bulk VIN decoding from uploaded spreadsheets
- Downloadable sample template
- Job IDs and persistent job tracking
- Free SQLite-backed job state and VIN cache
- Background processing with status polling
- Automatic cleanup of old uploads/results
- Configurable rate limiting
- Raspberry Pi + `systemd` + Gunicorn friendly

## Requirements

- Python 3.8+
- Flask
- Requests
- Pandas
- OpenPyXL
- Flask-Limiter
- Python-Dotenv
- Gunicorn (Linux/Raspberry Pi deployment)

## Installation

Create or update the virtual environment and install dependencies:

```bash
python install_required_packages.py
```

Run locally:

```bash
python vin_decoder.py
```

Open:

```text
http://127.0.0.1:5000/
```

## Configuration

Copy `.env.example` to `.env` and adjust values as needed.

Important variables:

- `VIN_DECODER_ENV` — `development`, `production`, or `testing`
- `VIN_DECODER_BASE_DIR` — project root override
- `VIN_DECODER_DB_PATH` — SQLite database location
- `VIN_DECODER_REQUEST_TIMEOUT_SECONDS` — upstream VIN API timeout
- `VIN_DECODER_RATE_LIMIT_STORAGE_URI` — defaults to `memory://`
- `VIN_DECODER_CACHE_TTL_HOURS` — VIN cache retention
- `VIN_DECODER_CLEANUP_TTL_HOURS` — old uploads/output retention
- `VIN_DECODER_JOB_POLL_INTERVAL_MS` — status page refresh interval

## Free mode defaults

This project is intentionally set up with free-friendly defaults:

- **SQLite** for persistent job tracking and VIN caching
- **memory://** Flask-Limiter backend
- **1 Gunicorn worker** in the sample service file for consistency on Raspberry Pi

If you later want stronger multi-worker rate limiting, switch to Redis by changing:

```env
VIN_DECODER_RATE_LIMIT_STORAGE_URI=redis://localhost:6379/0
```

## Running tests

```bash
python -m unittest discover -s tests
```

## Raspberry Pi deployment

Use the included `vin_decoder.service.example` as a starting point.

Install it as:

```bash
sudo cp vin_decoder.service.example /etc/systemd/system/vin_decoder.service
sudo systemctl daemon-reload
sudo systemctl enable vin_decoder
sudo systemctl restart vin_decoder
```

Check status:

```bash
sudo systemctl status vin_decoder
journalctl -u vin_decoder -f
```

## SQLite notes

The app uses SQLite with WAL mode enabled. That works well for a small free deployment, but it is still a single-writer database.

For this project size, it is a practical choice. If you later scale up significantly, move the job store to PostgreSQL.

## Troubleshooting

### App starts but uploads fail
Check:

- file type is CSV/XLS/XLSX
- one column contains valid 17-character VINs
- the upload directory is writable

### Gunicorn service won’t start
Check:

- `.venv` exists
- Gunicorn is installed in that environment
- the service `ExecStart` path matches the actual virtualenv path

### Rate limiter warning
If using `memory://`, keep Gunicorn on one worker for the free/simple setup.

### Logs
Use:

```bash
journalctl -u vin_decoder -f
```

## Project structure

- `vin_decoder.py` — Flask app and job processing
- `config.py` — environment-specific config
- `templates/` — HTML templates
- `static/` — CSS, icons, sample upload template
- `tests/` — unit tests
- `vin_decoder.service.example` — sample Raspberry Pi `systemd` unit
