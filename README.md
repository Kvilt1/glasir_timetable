# Glasir Timetable Site Mapper

A comprehensive site mapping tool for the Glasir timetable website. This script authenticates with the site using cookies and captures:

- All HTML pages and their content
- CSS stylesheets
- JavaScript files 
- Network requests and responses
- Site structure and navigation
- Timetable data across all available weeks
- Homework content for all classes
- Teacher information

## Prerequisites

- Python 3.7+
- Playwright
- httpx
- The Glasir timetable package (for cookie authentication)

## Installation

1. Make sure you have Python 3.7+ installed
2. Install the required packages:
   ```
   pip3 install playwright httpx
   playwright install
   ```
3. Ensure you have valid cookies in the cookies.json file (use the cookie_auth.py module to refresh them if needed)

## Usage

Run the script with the following command:

```bash
python3 site_mapper.py
```

### Command-line options:

- `-o`, `--output-dir`: Directory where mapping output will be saved (default: "site_map_output")
- `-c`, `--cookie-path`: Path to the cookies.json file (default: "./glasir_timetable/cookies.json")
- `-d`, `--depth`: Maximum crawl depth for site exploration (default: 2)
- `-w`, `--weeks`: Number of weeks to navigate forward and backward (default: 5)

Example with all options:

```bash
python3 site_mapper.py --output-dir my_mapped_site --cookie-path /path/to/cookies.json --depth 3 --weeks 10
```

## Output Structure

The script organizes captured data into the following directory structure:

- `site_map_output/` (or specified output directory)
  - `html/`: Captured HTML pages
  - `css/`: Captured CSS files
  - `js/`: Captured JavaScript files
  - `images/`: Screenshots and image resources
  - `requests/`: Other captured resources
  - `timetable/`: Extracted timetable data
  - `homework/`: Extracted homework content
  - `requests_log.json`: Log of all network requests
  - `resources.json`: Details of all captured resources
  - `page_content.json`: Index of all captured pages
  - `urls.json`: All discovered URLs
  - `timetable_data.json`: Structured timetable data
  - `homework_data.json`: Structured homework data
  - `teacher_map.json`: Teacher information

## Features

The site mapper performs the following tasks:

1. **Authentication**: Uses cookie-based authentication to access the site
2. **Resource Collection**: Captures all network requests, HTML, CSS, JavaScript, and images
3. **Site Crawling**: Recursively follows links within the site's domain
4. **Week Navigation**: Iterates through available weeks in the timetable
5. **Homework Collection**: Captures homework details for all lessons
6. **Teacher Map**: Extracts information from the teacher page
7. **Storage**: Organizes collected data in a structured directory system

## Working with the Data

After running the site mapper, you can analyze the collected data in various ways:

- Review the HTML content to understand the page structure
- Analyze JavaScript files to understand the site's behavior
- Examine network requests to identify API patterns
- Study the timetable data structure for integration purposes
- Explore the site navigation structure
- Understand homework and teacher data relationships 