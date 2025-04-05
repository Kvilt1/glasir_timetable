# Glasir Timetable Exporter

A powerful tool for extracting, processing, and exporting timetable data from Glasir's internal timetable system.

---

## Overview

This application authenticates with Glasir's system, fetches timetable and homework data via internal APIs, and exports the data as structured JSON files. It supports parallel extraction, teacher mapping, and flexible week range selection.

---

## Features

- **Async API-based extraction** using Playwright and httpx
- **Automatic authentication** with Playwright login and cookie reuse
- **Parallel fetching** of timetable and homework for multiple weeks
- **Teacher initials resolution** with caching
- **Homework integration** merged into timetable events
- **Export to JSON** for easy integration with other tools
- **Configurable week ranges** (current, past, future, or all)
- **Robust error handling** and detailed logging
- **CLI interface** with many options
- **Docker support** for easy deployment

---

## Architecture

The project is structured into several layers:

### Authentication Layer
- **Playwright login** (`auth.py`)
- **Cookie management** (`cookie_auth.py`)
- **Account management** (`account_manager.py`)

### API Client Layer
- **`api_client.py`**: Async httpx client for timetable, homework, teacher map, weeks
- Handles retries, DNS checks, and raw response saving

### Service Layer
- **Interfaces and implementations** in `services.py`
- **Factory** in `service_factory.py` wires services together
- Supports Playwright and API-based extraction

### Navigation & Extraction
- **`navigation.py`** orchestrates week processing
- **`extractors/`** parse timetable and homework HTML

### Data Models
- **Pydantic models** in `models.py`
- **Domain entities** in `domain.py`

### Storage
- **Exports** JSON files to `glasir_timetable/weeks/` or custom dir
- **Caches** teacher map, credentials, cookies in `glasir_timetable/accounts/`

### Configuration & Error Handling
- Constants in `constants.py`
- Error collection in `__init__.py`

---

## Architecture Diagram

```mermaid
flowchart TD

  subgraph Auth
    A1[Playwright Login]
    A2[Cookie Management]
    A3[Account Manager]
  end

  subgraph API
    B1[API Client (httpx)]
    B2[Homework Fetch]
    B3[Timetable Fetch]
    B4[Teacher Map Fetch]
  end

  subgraph Services
    S1[AuthenticationService]
    S2[ExtractionService]
    S3[NavigationService]
    S4[FormattingService]
    S5[StorageService]
  end

  subgraph Data
    D1[Models (Pydantic)]
    D2[Domain Entities]
    D3[JSON Exports]
  end

  A1 --> A2
  A2 --> A3
  A3 --> S1

  S1 --> B1
  B1 --> B2
  B1 --> B3
  B1 --> B4

  S2 --> B1
  S3 --> B1

  S4 --> D1
  S4 --> D2

  S5 --> D3
```

---

## Usage

Basic example:

```bash
python3 -m glasir_timetable.main --weekforward 2 --weekbackward 2
```

This extracts the current week, plus 2 weeks forward and 2 weeks backward.

### Command-line Options

- `--username`: Glasir username (without @glasir.fo)
- `--password`: Glasir password
- `--credentials-file`: JSON file with credentials (default: glasir_timetable/credentials.json)
- `--weekforward`: Weeks forward to extract
- `--weekbackward`: Weeks backward to extract
- `--all-weeks`: Extract all available weeks
- `--output-dir`: Directory for exports (default: glasir_timetable/weeks)
- `--headless`: Run browser headless (default: true)
- `--log-level`: Logging level
- `--log-file`: Log to file
- `--collect-error-details`: Collect detailed error info
- `--collect-tracebacks`: Collect tracebacks
- `--enable-screenshots`: Save screenshots on errors
- `--error-limit`: Max errors per category
- `--use-cookies`: Use saved cookies (default: true)
- `--cookie-path`: Path for cookies file
- `--no-cookie-refresh`: Disable cookie refresh
- `--teacherupdate`: Update teacher cache
- `--skip-timetable`: Skip timetable extraction

---

## Output Format

Exports JSON files like:

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
    }
  ]
}
```

---

## Installation

See [INSTALLATION.md](INSTALLATION.md) for detailed instructions.

---

## Contributing

Contributions welcome! Please fork, create a branch, and submit a pull request.

---

## License

MIT License. See LICENSE file.