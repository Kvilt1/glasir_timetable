# Glasir Timetable Exporter

A tool for extracting and exporting timetable data from Glasir's internal timetable system.

## Overview

This application accesses the Glasir timetable system, authenticates using your credentials, and exports the timetable data to JSON format. The exported data can then be used in various applications, such as calendar integrations or custom timetable viewers.

## Features

- **API-based Extraction**: Uses Glasir's internal API to extract timetable data efficiently
- **Automatic Authentication**: Handles login process with your credentials
- **Week Range Selection**: Export current week, specific ranges, or all available weeks
- **Homework Integration**: Extracts homework assignments and merges them with timetable entries
- **Teacher Name Resolution**: Maps teacher initials to full names
- **Cookie-based Authentication**: Reuses authentication tokens to minimize login requests
- **Export to JSON**: Exports data in a structured JSON format for easy integration with other applications

## Usage

Basic usage:

```bash
python3 -m glasir_timetable.main --weekforward 2 --weekbackward 2
```

This will extract the current week, plus 2 weeks forward and 2 weeks backward.

### Command-line Options

- `--username`: Your Glasir username (without @glasir.fo)
- `--password`: Your Glasir password
- `--credentials-file`: JSON file with username and password (default: glasir_timetable/credentials.json)
- `--weekforward`: Number of weeks forward to extract (default: 0)
- `--weekbackward`: Number of weeks backward to extract (default: 0)
- `--all-weeks`: Extract all available weeks from all academic years
- `--output-dir`: Directory to save output files (default: glasir_timetable/weeks)
- `--headless`: Run in non-headless mode (default: headless=True)
- `--log-level`: Set the logging level (choices: DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `--log-file`: Log to a file instead of console
- `--collect-error-details`: Collect detailed error information
- `--collect-tracebacks`: Collect tracebacks for errors
- `--enable-screenshots`: Enable screenshots on errors
- `--error-limit`: Maximum number of errors to store per category
- `--use-cookies`: Use cookie-based authentication when possible (default: True)
- `--cookie-path`: Path to save/load cookies (default: cookies.json)
- `--no-cookie-refresh`: Do not refresh cookies even if they are expired
- `--teacherupdate`: Update the teacher mapping cache at the start of the script
- `--skip-timetable`: Skip timetable extraction, useful when only updating teachers

## Output Format

The exported JSON files follow this structure:

```json
{
  "weekInfo": {
    "weekNumber": 10,
    "year": 2023,
    "startDate": "2023-03-06",
    "endDate": "2023-03-12"
  },
  "events": [
    {
      "lessonId": "1234567",
      "startTime": "08:15",
      "endTime": "10:00",
      "dayOfWeek": 1,
      "subject": "Mathematics",
      "room": "A1.02",
      "teacher": "John Doe",
      "teacherInitials": "JDO",
      "description": "Homework: Complete exercises 1-10 on page 42"
    },
    // More events...
  ]
}
```

## Installation

See the [INSTALLATION.md](INSTALLATION.md) file for detailed installation instructions.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 