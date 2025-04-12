# Glasir Timetable Exporter

A powerful tool for extracting, processing, and exporting timetable data from Glasir's internal timetable system.

---

## Overview

This application authenticates with Glasir's system, fetches timetable and homework data via internal APIs, and exports the data as structured JSON files. It supports parallel extraction, teacher mapping, and flexible week range selection.

The tool uses a hybrid approach. It **automatically operates in an API-only mode** using `httpx` when valid authentication data (cookies and student info) is found for the selected profile, significantly speeding up extraction. If valid data is missing or expired, it seamlessly falls back to using Playwright browser automation for login and initial data retrieval. It caches teacher mappings and student info to optimize subsequent runs. All data, cookies, and credentials are stored per account under dedicated directories, enabling seamless management of multiple user accounts.

---

## Features

- **Automatic Hybrid Extraction:** Uses fast `httpx` API calls when possible (valid cookies/student info found), seamlessly falling back to Playwright browser automation for login/data retrieval only when necessary.
- **Efficient Authentication:** Reuses saved cookies and student info to bypass repeated Playwright logins.
- **Parallel fetching** of timetable and homework for multiple weeks.
- **Teacher initials resolution** with caching.
- **Homework integration** merged into timetable events.
- **Export to JSON** for easy integration with other tools.
- **Configurable week ranges** (current, past, future, or all).
- **Robust error handling** and detailed logging.
- **CLI interface** with comprehensive options.
- **Per-account data and cookie management** for multiple users.
- **Caching of teacher maps and student info** to optimize repeated runs.

---

## Architecture

The system features a modular architecture separating concerns like authentication, API interaction, data parsing, and storage.

For a detailed explanation and diagrams, see the [Architecture Documentation](docs/architecture.md).

---

## Usage

Basic example to extract the current week, plus 2 weeks forward and 2 weeks backward:

```bash
python3 -m glasir_timetable --weekforward 2 --weekbackward 2
```

### Command-line Options

- `--username`: Glasir username (without @glasir.fo)
- `--password`: Glasir password
- `--credentials-file`: JSON file with credentials (default: `glasir_timetable/accounts/<username>/credentials.json`)
- `--weekforward`: Weeks forward to extract
- `--weekbackward`: Weeks backward to extract
- `--all-weeks`: Extract all available weeks
- `--output-dir`: Directory for exports (default: `output/`)
- `--headless`: Run browser headless (default: true)
- `--log-level`: Logging level (e.g., INFO, DEBUG)
- `--log-file`: Log to a specified file
- `--collect-error-details`: Collect detailed error info
- `--collect-tracebacks`: Collect tracebacks
- `--enable-screenshots`: Save screenshots on browser errors
- `--error-limit`: Max errors per category before stopping
- `--use-cookies`: Use saved cookies for login (default: true)
- `--cookie-path`: Path for cookies file (default: `glasir_timetable/accounts/<username>/cookies.json`)
- `--no-cookie-refresh`: Disable automatic cookie refresh
- `--teacherupdate`: Force update of the teacher cache
- `--skip-timetable`: Skip timetable extraction (e.g., only fetch homework)

---

## Output Format

Exports JSON files per week to the specified output directory. Example (`output/week_2023_10.json`):

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
      "dayOfWeek": 1, // Monday
      "subject": "Mathematics",
      "room": "A1.02",
      "teacher": "John Doe",
      "teacherInitials": "JDO",
      "description": "Homework: Complete exercises 1-10 on page 42"
    }
    // ... more events
  ]
}
```

---

## Installation

See [INSTALLATION.md](INSTALLATION.md) for detailed setup instructions.

---

## Testing

The project uses `pytest` for running tests. Mocks are utilized to isolate components during unit testing.

For details on the testing strategy and how to run tests, see the [Testing Documentation](docs/testing.md).

---

## Contributing

Contributions are welcome! Please fork the repository, create a feature branch, and submit a pull request.

---

## License

MIT License. See the LICENSE file for details.
