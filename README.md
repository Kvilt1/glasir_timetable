# Glasir Timetable Extractor

This application extracts timetable data from the Glasir website and saves it in JSON format for use in calendar applications.

## Features

- Extracts class information including subjects, teachers, rooms, times, and homework
- Parallel homework extraction for improved performance
- Supports multiple weeks extraction
- Standardized JSON format compatible with calendar applications
- Interactive credential prompting when no saved credentials are found
- Automatic domain handling for Glasir usernames

## Installation

### Quick Start

```bash
git clone https://github.com/yourusername/glasir_timetable.git
cd glasir_timetable
pip3 install -r requirements.txt
python3 -m playwright install
```

### Advanced Installation Options

This project supports multiple dependency management options:

1. **Standard Method (pip)**: Uses `requirements.txt`
2. **Poetry (Recommended)**: Better dependency resolution via `pyproject.toml`
3. **PDM**: Modern Python package manager via `pdm.toml`

For detailed installation instructions, troubleshooting guide, and advanced options, see [INSTALLATION.md](INSTALLATION.md).

### Dependencies

- **Required**: playwright, beautifulsoup4, tqdm, requests, lxml, pydantic
- **Optional**: python-dotenv
- **Development**: pytest, pytest-asyncio, black, isort, mypy (Poetry/PDM only)

## Usage

### Basic Usage

```bash
python3 glasir_timetable/main.py
```

On first run, you'll be prompted to enter your Glasir username and password. These credentials will be saved for future use.

### Command-line Arguments

```bash
python3 glasir_timetable/main.py --username your_username --password your_password
```

### Options

- `--username`: Your login username (without @glasir.fo)
- `--password`: Your login password
- `--credentials-file`: Path to JSON file with username and password (default: glasir_timetable/credentials.json)
- `--weekforward`: Number of weeks forward to extract (default: 0)
- `--weekbackward`: Number of weeks backward to extract (default: 0)
- `--all-weeks`: Extract all available weeks from all academic years
- `--output-dir`: Directory to save output files (default: glasir_timetable/weeks)
- `--test-js`: Test the JavaScript integration before extracting data
- `--headless`: Run in headless mode (default: true)
- `--log-level`: Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `--log-file`: Log to a file instead of console
- `--batch-size`: Number of homework items to process in parallel (default: 5)
- `--unlimited-batch-size`: Process all homework items in a single batch for maximum performance

## Authentication

The application supports three methods of authentication:

1. **Interactive Prompt**: If no credentials are found, you'll be prompted to enter your username and password.
2. **Command-line Arguments**: Provide credentials via `--username` and `--password` flags.
3. **Credentials File**: A JSON file containing your username and password.

Your username is automatically appended with "@glasir.fo" domain during login. You only need to provide the username portion.

## Advanced Features

### Parallel Homework Extraction

The application uses an optimized parallel approach to extract homework data:

- Processes multiple homework items simultaneously for faster extraction
- Configurable batch size (via `--batch-size` parameter) to balance performance and server load
- Optimized for performance with JavaScript-based extraction

## Output Format

The application outputs data in a standardized event-centric format that organizes data around individual events (classes), making it easier to integrate with calendar applications. This format uses camelCase property names and standardized ISO 8601 date formats.

```json
{
  "studentInfo": {
    "studentName": "Student Name",
    "class": "Class"
  },
  "events": [
    {
      "title": "evf",
      "date": "2025-03-24",
      "day": "Monday",
      "startTime": "10:05",
      "endTime": "11:35",
      "teacher": "Teacher Name",
      "teacherShort": "TN",
      "location": "608",
      "timeSlot": "2",
      "cancelled": false,
      "description": "Homework description",
      "year": "2024-2025",
      "level": "A"
    },
    ...
  ],
  "weekInfo": {
    "weekNum": 13,
    "startDate": "2025-03-24",
    "endDate": "2025-03-30",
    "year": 2025
  },
  "formatVersion": 2
}
```

## Integrating with Calendar Applications

The event-centric format makes it easier to import timetable data into calendar applications:

1. Each event in the `events` array corresponds to a calendar event
2. Use the `date`, `startTime`, and `endTime` fields to set the event timing
3. Use `title` for the event title, `location` for the location, and `description` for additional details
4. Cancelled classes (where `cancelled` is true) can be handled according to your application's requirements

## License

This project is licensed under the MIT License - see the LICENSE file for details. 