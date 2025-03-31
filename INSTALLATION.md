# Installation Guide

This guide covers multiple installation methods for the Glasir Timetable Extractor.

## Prerequisites

- Python 3.8 or higher
- pip, Poetry, or PDM (depending on your preferred installation method)

## Method 1: Using pip (Standard)

```bash
# Clone the repository
git clone https://github.com/yourusername/glasir_timetable.git
cd glasir_timetable

# Install dependencies
pip3 install -r requirements.txt

# Install Playwright browsers
python3 -m playwright install

# Run the application
python3 main.py --username your_username --password your_password
```

## Method 2: Using Poetry (Recommended)

Poetry provides better dependency resolution and virtual environment management.

```bash
# Install Poetry if you don't have it
curl -sSL https://install.python-poetry.org | python3 -

# Clone the repository
git clone https://github.com/yourusername/glasir_timetable.git
cd glasir_timetable

# Install dependencies
poetry install

# Install Playwright browsers
poetry run python -m playwright install

# Run the application
poetry run python glasir_timetable/main.py --username your_username --password your_password

# Alternative: Use the defined script
poetry run glasir --username your_username --password your_password
```

## Method 3: Using PDM

PDM is a modern Python package and dependency manager.

```bash
# Install PDM if you don't have it
curl -sSL https://pdm.fming.dev/install-pdm.py | python3 -

# Clone the repository
git clone https://github.com/yourusername/glasir_timetable.git
cd glasir_timetable

# Install dependencies
pdm install

# Install Playwright browsers
pdm run python -m playwright install

# Run the application
pdm run python glasir_timetable/main.py --username your_username --password your_password

# Alternative: Use the defined script
pdm run glasir --username your_username --password your_password
```

## Optional: Using Credentials File

Instead of providing credentials via command line, you can create a `credentials.json` file:

```json
{
  "username": "your_username",
  "password": "your_password"
}
```

Place this file in the `glasir_timetable` directory or specify a custom path with `--credentials-file`.

## Troubleshooting

### Playwright Installation Issues

If you encounter Playwright installation issues:

```bash
# For specific browser installation:
python3 -m playwright install chromium

# For dependencies installation:
python3 -m playwright install-deps
```

### SSL Certificate Errors

If you encounter SSL certificate errors during installation or execution:

```bash
# Add trusted certificates environment variable
export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
export NODE_TLS_REJECT_UNAUTHORIZED=0

# Then install dependencies again
```

### Dependency Conflicts

With Poetry or PDM, dependency conflicts are minimized, but if they occur:

```bash
# With Poetry:
poetry update --lock

# With PDM:
pdm update
``` 