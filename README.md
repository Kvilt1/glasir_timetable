# Glasir Timetable Extractor

This application extracts timetable data from the Glasir website and saves it in JSON format for use in calendar applications.

## Features

- Extracts class information including subjects, teachers, rooms, times, and homework
- Supports multiple weeks extraction
- Standardized JSON format compatible with calendar applications
- Multiple output format options for better integration

## Installation

```bash
git clone https://github.com/yourusername/glasir_timetable.git
cd glasir_timetable
pip3 install -r requirements.txt
```

## Usage

### Basic Usage

```bash
python3 glasir_timetable/main.py --email your_email@example.com --password your_password
```

### Options

- `--email`: Your login email
- `--password`: Your login password
- `--credentials-file`: Path to JSON file with email and password (default: glasir_timetable/credentials.json)
- `--weekforward`: Number of weeks forward to extract (default: 0)
- `--weekbackward`: Number of weeks backward to extract (default: 0)
- `--all-weeks`: Extract all available weeks from all academic years
- `--output-dir`: Directory to save output files (default: glasir_timetable/weeks)
- `--test-js`: Test the JavaScript integration before extracting data
- `--headless`: Run in headless mode (default: true)
- `--log-level`: Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `--log-file`: Log to a file instead of console
- `--use-new-format`: Save data in the new event-centric format (default)
- `--use-old-format`: Save data in the old traditional format
- `--save-dual-format`: Save data in both formats

## Output Formats

### New Event-Centric Format (Default)

The new event-centric format organizes data around individual events (classes), making it easier to integrate with calendar applications. This format uses camelCase property names and standardized ISO 8601 date formats.

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
    "startDate": "2025.03.24",
    "endDate": "2025.03.30",
    "year": 2025
  }
}
```

### Traditional Format

The traditional format organizes data by week and day, maintaining backward compatibility with existing applications:

```json
{
  "Week 13: 2025.03.24 to 2025.03.30": {
    "Monday": [
      {
        "name": "evf",
        "level": "A",
        "Year": "2024-2025",
        "date": "24/3-2025",
        "Teacher": "Teacher Name",
        "Teacher short": "TN",
        "Location": "608",
        "Time slot": "2",
        "Time": "10:05-11:35",
        "Cancelled": false,
        "Homework": "Homework description"
      },
      ...
    ],
    "Tuesday": [...],
    ...
  },
  "student_info": {
    "student_name": "Student Name",
    "class": "Class"
  }
}
```

### Dual Format

The dual format includes both traditional and event-centric structures in the same file, allowing for a smooth transition between formats:

```json
{
  "traditional": {
    // Traditional format as above
  },
  "eventCentric": {
    // Event-centric format as above
  },
  "formatVersion": 2
}
```

## Converting Existing JSON Files

The converter script can transform existing traditional format JSON files to the new event-centric format:

```bash
python3 glasir_timetable/utils/converter.py --input path/to/file_or_directory --output-dir path/to/output
```

### Converter Options

- `--input`: Path to input file or directory
- `--output-dir`: Directory to save converted files
- `--format`: Format to convert to (new=event-centric only, dual=both formats)
- `--overwrite`: Overwrite original files
- `--log-level`: Logging level (DEBUG, INFO, WARNING, ERROR)

Example to convert all files in a directory:

```bash
python3 glasir_timetable/utils/converter.py --input glasir_timetable/weeks --output-dir glasir_timetable/weeks_new --format dual
```

## Integrating with Calendar Applications

The event-centric format makes it easier to import timetable data into calendar applications:

1. Each event in the `events` array corresponds to a calendar event
2. Use the `date`, `startTime`, and `endTime` fields to set the event timing
3. Use `title` for the event title, `location` for the location, and `description` for additional details
4. Cancelled classes (where `cancelled` is true) can be handled according to your application's requirements

## License

This project is licensed under the MIT License - see the LICENSE file for details. 