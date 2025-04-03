# Installation Instructions

## Prerequisites

- Python 3.7 or higher
- Playwright (for the initial login process and HTML parsing)
- A valid Glasir account

## Step 1: Install Python Dependencies

```bash
# Install required Python packages
pip3 install -r requirements.txt

# Install Playwright browsers
python3 -m playwright install chromium
```

## Step 2: Clone and Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/glasir_timetable.git
cd glasir_timetable

# Create a credentials file (optional)
# If not created, you'll be prompted for credentials on first run
echo '{"username": "your_username", "password": "your_password"}' > glasir_timetable/credentials.json
```

## Step 3: Run the Application

```bash
# Basic usage - extract current week only
python3 -m glasir_timetable.main

# Extract current week plus 2 weeks forward and 2 weeks backward
python3 -m glasir_timetable.main --weekforward 2 --weekbackward 2

# Extract all available weeks
python3 -m glasir_timetable.main --all-weeks
```

## Authentication Details

The application uses a two-stage authentication process:

1. First login: Playwright is used to authenticate with the Glasir website and obtain cookies.
2. Subsequent requests: The application uses the cookies obtained in the first step to make API requests.

The cookies are saved to a file (`cookies.json` by default) and reused for subsequent runs. They will be refreshed automatically when expired.

## Advanced Configuration

### Cookie Authentication

Cookie-based authentication is enabled by default to minimize login requests. You can disable it with the `--no-cookie-refresh` flag.

```bash
# Disable cookie refreshing
python3 -m glasir_timetable.main --no-cookie-refresh
```

### Custom Output Directory

By default, the application saves timetable data to `glasir_timetable/weeks`. You can specify a custom output directory:

```bash
python3 -m glasir_timetable.main --output-dir ~/my_timetable_data
```

### Update Teacher Map

The application maintains a cache of teacher initials to full names. To update this cache:

```bash
python3 -m glasir_timetable.main --teacherupdate --skip-timetable
```

### Error Handling and Debugging

For troubleshooting, you can enable more detailed logging:

```bash
# Enable detailed logging
python3 -m glasir_timetable.main --log-level DEBUG --collect-error-details --collect-tracebacks

# Save logs to a file
python3 -m glasir_timetable.main --log-file timetable_extraction.log

# Enable screenshots on errors
python3 -m glasir_timetable.main --enable-screenshots
```

## Docker Installation (Optional)

You can also run the application using Docker:

```bash
# Build the Docker image
docker build -t glasir_timetable .

# Run with Docker
docker run -v $(pwd)/data:/app/data glasir_timetable --output-dir /app/data
```

## Troubleshooting

### Authentication Issues

- Check that your credentials are correct
- Try deleting the cookies.json file to force a fresh login
- Make sure you have a working internet connection

### Extraction Issues

- If the API extraction fails, try again later as the Glasir website may be experiencing issues
- Check the log files for detailed error messages
- Verify that your account has access to the timetable system

### Browser Installation Issues

If you encounter issues with Playwright browser installation:

```bash
# Force reinstall browsers
python3 -m playwright install --force
```

## Next Steps

After installation, see the README.md file for more details on usage and features. 