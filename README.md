# Glasir Timetable Extractor

A tool for extracting timetable data from Glasir's timetable system.

## Project Structure

The project has been reorganized for clarity:

- **main.py**: Main entry point for the application
- **__main__.py**: Entry point for running as a module
- **credentials.json**: Login credentials (not committed to version control)

### Main Package
- **glasir_timetable/**: Core package containing application logic
  - **auth.py**: Authentication and login functionality
  - **constants.py**: Constants and configuration
  - **extractors/**: Modules for extracting timetable data
  - **utils/**: Utility functions and helpers
  - **js_navigation/**: JavaScript-based timetable navigation

### Support Directories
- **docs/**: Documentation files
- **tests/**: Test files and BDD feature specifications
- **tools/**: Utility scripts and tools
- **logs/**: Error logs and screenshots
- **weeks/**: Output directory for extracted timetable data
- **scraped_site/**: Scraped website resources
- **login_process/**: Login process analysis data
- **findings/**: Analysis findings

## Usage

```bash
python3 main.py --email YOUR_EMAIL --password YOUR_PASSWORD
```

Or using command-line options:

```bash
python3 main.py --credentials-file credentials.json --weekforward 3 --weekbackward 2
```

For more options:

```bash
python3 main.py --help
```

## Scripts

### 1. Site Scraper (`tools/site_scraper.py`)

This script logs into the Glasir Timetable website using the credentials from `docs/login_flow.md` and scrapes all resources (HTML, CSS, JavaScript) from the site.

Usage:
```bash
python3 tools/site_scraper.py
```

The script will:
- Log into the timetable site
- Download all JavaScript, CSS, and HTML files
- Capture screenshots and snapshots of various states
- Extract JavaScript objects and functions
- Interact with various elements to collect more data

All scraped data is saved to the `scraped_site` directory.

### 2. JavaScript Analysis (`tools/analyze_js.py`)

This script analyzes the JavaScript files collected by the scraper to identify potential issues, particularly with the speech bubble functionality.

Usage:
```bash
python3 tools/analyze_js.py
```

The script will:
- Search for the MyUpdate function
- Find DOM element usages (note buttons, speech bubbles)
- Analyze event handlers
- Check for AJAX calls

Results are saved to the `scraped_site/analysis` directory as both JSON data and a markdown report.

### 3. JavaScript Fixes (`tools/fix_js_issues.py`)

This script generates fixes for identified JavaScript issues, particularly focusing on the speech bubble functionality.

Usage:
```bash
python3 tools/fix_js_issues.py
```

The script will:
- Generate fixed versions of problematic JavaScript files
- Create CSS fixes for styling issues
- Provide comprehensive documentation on the fixes

All fixes are saved to the `scraped_site/fixes` directory.

## How to Use

1. **Setup**:
   - Ensure you have Python 3 and Playwright installed
   - Install requirements: `pip3 install playwright`
   - Install browsers: `playwright install chromium`

2. **Extract Timetable Data**:
   ```bash
   python3 main.py --credentials-file credentials.json
   ```

3. **Extract Multiple Weeks**:
   ```bash
   python3 main.py --credentials-file credentials.json --weekforward 3 --weekbackward 2
   ```

4. **Use JavaScript-based Navigation** (faster but experimental):
   ```bash
   python3 main.py --credentials-file credentials.json --use-js
   ```

## Notes

- The scripts handle errors gracefully but may still encounter issues due to changes in the website structure
- All original files are backed up before modifications
- The directory structure has been reorganized to separate core functionality from utility scripts 