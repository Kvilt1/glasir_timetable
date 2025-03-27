# Glasir Timetable

A tool for extracting timetable data from Glasir's website.

## Project Structure

The project is organized in a modular structure:

```
glasir_timetable/
├── __init__.py           # Package initialization
├── auth.py               # Authentication functionality
├── constants.py          # Constants and mappings
├── main.py               # Main application logic
├── extractors/           # Data extraction modules
│   ├── __init__.py
│   ├── teacher_map.py    # Teacher information extraction
│   └── timetable.py      # Timetable data extraction
└── utils/                # Utility functions
    ├── __init__.py
    ├── formatting.py     # Date and data formatting
    └── validator.py      # Data validation
```

## Usage

### 1. Running from the main script

The simplest way to run the application is:

```bash
python3 glasir_timetable.py
```

### 2. Running the module directly

You can also run the package as a module:

```bash
python3 -m glasir_timetable
```

### 3. Running the main.py file

The `main.py` file can be run directly from the parent directory:

```bash
python3 -m glasir_timetable.main
```

## Requirements

- Python 3.7+
- Playwright (`pip3 install playwright`)
- Beautiful Soup 4 (`pip3 install beautifulsoup4`)
- You will need to install Playwright browsers: `python3 -m playwright install`

## Configuration

Create a file named `credentials.json` in the project root with the following format:

```json
{
  "email": "your_email@example.com",
  "password": "your_password"
}
```

## Output

The extracted timetable data will be saved to the `weeks/` directory in JSON format. The filenames will be based on the year and week number. 