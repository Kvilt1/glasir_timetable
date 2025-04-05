# Installation Instructions

---

## Prerequisites

- Python 3.7 or higher
- Playwright (for login and HTML parsing)
- A valid Glasir account

---

## Step 1: Install Dependencies

```bash
pip3 install -r requirements.txt
python3 -m playwright install chromium
```

---

## Step 2: Clone and Setup

```bash
git clone https://github.com/yourusername/glasir_timetable.git
cd glasir_timetable

# Optional: create credentials file
echo '{"username": "your_username", "password": "your_password"}' > glasir_timetable/credentials.json
```

If no credentials file is created, you will be prompted on first run.

---

## Step 3: Run the Application

```bash
# Extract current week only
python3 -m glasir_timetable.main

# Extract current week plus 2 weeks forward and 2 weeks backward
python3 -m glasir_timetable.main --weekforward 2 --weekbackward 2

# Extract all available weeks
python3 -m glasir_timetable.main --all-weeks
```

---

## Authentication Details

- First login uses Playwright to authenticate and save cookies.
- Subsequent requests use saved cookies (`cookies.json` by default).
- Cookies refresh automatically when expired.

---

## Advanced Configuration

### Cookie Authentication

Enabled by default. Disable refresh with:

```bash
python3 -m glasir_timetable.main --no-cookie-refresh
```

### Custom Output Directory

```bash
python3 -m glasir_timetable.main --output-dir ~/my_timetable_data
```

### Update Teacher Map

```bash
python3 -m glasir_timetable.main --teacherupdate --skip-timetable
```

### Debugging and Logging

```bash
# Enable detailed logging
python3 -m glasir_timetable.main --log-level DEBUG --collect-error-details --collect-tracebacks

# Save logs to file
python3 -m glasir_timetable.main --log-file timetable_extraction.log

# Enable screenshots on errors
python3 -m glasir_timetable.main --enable-screenshots
```

---

## Docker Usage (Optional)

```bash
docker build -t glasir_timetable .
docker run -v $(pwd)/data:/app/data glasir_timetable --output-dir /app/data
```

---

## Troubleshooting

### Authentication Issues

- Check credentials
- Delete `cookies.json` to force fresh login
- Verify internet connection

### Extraction Issues

- Retry later if Glasir is down
- Check logs for errors
- Verify account access

### Playwright Browser Issues

```bash
python3 -m playwright install --force
```

---

## Developer Setup (Brief)

- Use a **virtual environment**:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 -m playwright install chromium
```

- **Run tests** (if available):

```bash
pytest
```

- Follow code style and submit pull requests for contributions.

---

## Next Steps

See [README.md](README.md) for features, architecture, and usage details.