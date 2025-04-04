
```markdown
# Glasir Timetable Exporter - Project Context

## 1. Project Goal

The primary goal of this project is to automatically extract student timetable data, including class schedules, teacher information, and homework assignments, from the internal Glasir timetable system (`tg.glasir.fo`) and save it into structured JSON files for external use (e.g., calendar integration, analysis).

## 2. Core Functionality

*   **Authentication:** Logs into the Glasir system using Microsoft authentication via Playwright for the initial session, then primarily relies on saved cookies for subsequent API interactions. Handles cookie refresh.
*   **Timetable Extraction:** Fetches timetable data for specified weeks (current, range, or all available). It prioritizes direct API calls (`udvalg.asp`) over browser navigation.
*   **Teacher Mapping:** Extracts a mapping of teacher initials (e.g., "BIJ") to their full names (e.g., "Brynjálvur I. Johansen") using an API endpoint (`teachers.asp`) with caching (`teacher_cache.json`).
*   **Homework Extraction:** Identifies lessons with associated homework notes and fetches the homework content using a specific API endpoint (`note.asp`), merging it into the corresponding lesson data.
*   **Data Parsing:** Uses BeautifulSoup (with lxml) to parse HTML responses obtained from API calls or Playwright page content.
*   **Data Storage:** Saves the processed timetable data for each week into individual JSON files in a designated output directory (`glasir_timetable/weeks/`).
*   **Student Info Handling:** Extracts and caches student ID, name, and class (`student-id.json`).

## 3. Technology Stack

*   **Language:** Python 3.8+
*   **Asynchronous Operations:** `asyncio`
*   **Web Interaction (Login/Fallback):** `playwright` (Chromium)
*   **HTTP Requests (API):** `httpx` (asynchronous)
*   **HTML/XML Parsing:** `beautifulsoup4`, `lxml`
*   **Data Modeling/Validation:** `pydantic`
*   **Command-line Interface:** `argparse`
*   **Progress Indication:** `tqdm`
*   **Retry Logic:** `backoff`

## 4. Architecture & Design

*   **Service-Oriented:** Organized into distinct services (Authentication, Navigation, Extraction, Formatting, Storage) managed by a `ServiceFactory`.
*   **API-First Approach:** Prioritizes direct asynchronous API calls (`httpx`) for data fetching after initial authentication, minimizing reliance on slower Playwright interactions. Playwright is primarily used for the complex initial Microsoft login and as a fallback.
*   **Extractors:** Dedicated modules (`glasir_timetable/extractors/`) handle parsing logic for specific data types (timetable, teachers, homework).
*   **Utilities:** Helper functions for date handling, file operations, error handling, parameter extraction, etc. are located in `glasir_timetable/utils/`.
*   **Models:** Pydantic models (`glasir_timetable/models.py`, `glasir_timetable/domain.py`) define the structure of the data being processed and exported.
*   **Caching:** Uses JSON files (`cookies.json`, `teacher_cache.json`, `student-id.json`) to cache authentication tokens, teacher data, and student identifiers to speed up subsequent runs and reduce load.
*   **Session Management:** `AuthSessionManager` handles dynamic parameters (`lname`, `timer`) required for API calls, extracting them from page content.

## 5. Authentication Flow

1.  **Check Cookies:** Load cookies from `cookies.json` (or specified path).
2.  **Validate Cookies:** Check if loaded cookies are present and not expired.
3.  **Refresh (if needed):** If cookies are invalid/missing and refresh is enabled, use Playwright to perform a full Microsoft login (`login_to_glasir`), save the new cookies.
4.  **API Usage:** Use the valid cookies with `httpx` for subsequent API requests.

## 6. Data Extraction & Processing Flow

1.  **Authenticate:** Ensure valid authentication (cookies or fresh login).
2.  **Initialize Parameters:** Extract dynamic parameters (`lname`, `timer`, `student_id`) required for API calls.
3.  **Get Teacher Map:** Load/fetch the teacher mapping.
4.  **(Optional) Determine Week Range:** If `--all-weeks`, query the API to find the min/max available week offsets.
5.  **Fetch Timetable HTML:** For each required week offset, fetch the corresponding timetable HTML using the `udvalg.asp` API endpoint (potentially in parallel).
6.  **Parse Timetable:** For each fetched HTML:
    *   Parse using `BeautifulSoup` (`extract_timetable_data`).
    *   Identify basic lesson details (subject, time, room, teacher initials).
    *   Extract `lessonId` for lessons with homework indicators.
    *   Extract `weekInfo` (dates, week number, year).
7.  **Fetch Homework:** For lessons with identified `lessonId`s, fetch homework content using the `note.asp` API endpoint (in parallel batches per week).
8.  **Parse Homework:** Parse the homework HTML response (`parse_homework_html_response`) and clean the text.
9.  **Merge Data:** Combine timetable events with corresponding teacher full names and homework descriptions.
10. **Format & Save:** Format the final data structure (using Pydantic models internally) and save it as a JSON file with a standardized filename (e.g., `YYYY Vika WW - YYYY.MM.DD-YYYY.MM.DD.json`).

## 7. Configuration & Usage

*   **Credentials:** Managed via `--username`/`--password` arguments or `credentials.json`. Users are prompted if neither is provided.
*   **Week Selection:** Controlled by `--weekforward`, `--weekbackward`, `--all-weeks` arguments.
*   **Output:** Configured via `--output-dir`.
*   **Authentication Behavior:** Controlled by `--use-cookies`, `--cookie-path`, `--no-cookie-refresh`.
*   **Logging/Debugging:** Controlled by `--log-level`, `--log-file`, `--collect-error-details`, etc.

## 8. Output Data Structure (JSON)

The primary output is one JSON file per week, containing:

*   `studentInfo`: Name and class.
*   `weekInfo`: Week number, year, start/end dates (ISO format YYYY-MM-DD).
*   `events`: A list of lesson/event objects, each including:
    *   Subject (`title`), level, academic year (`year`).
    *   Date (ISO), day name.
    *   Teacher full name (`teacher`), initials (`teacherShort`).
    *   Location (`location`).
    *   Time slot info (`timeSlot`, `startTime`, `endTime`, `timeRange`).
    *   Cancellation status (`cancelled`).
    *   Lesson ID (`lessonId`) if available.
    *   Homework description (`description`) if fetched.
*   `formatVersion`: Indicates the schema version (currently 2).

## 9. Key Modules/Components

*   `main.py`: Entry point, argument parsing, orchestration.
*   `service_factory.py`: Creates and manages service instances.
*   `services.py`: Defines service interfaces and implementations (Auth, Navigation, Extraction, etc.).
*   `api_client.py`: Handles direct interaction with Glasir API endpoints using `httpx`.
*   `session.py`: Manages dynamic session parameters (`lname`, `timer`).
*   `extractors/`: Modules for parsing specific data (timetable, teachers, homework).
*   `utils/`: Helper functions (date, file, error handling).
*   `models.py`/`domain.py`: Pydantic data models.
*   `auth.py`/`cookie_auth.py`: Authentication logic.
*   `navigation.py`: (Legacy, now mostly superseded by API calls) Week navigation logic.
*   `student_utils.py`: Student ID handling.
*   `constants.py`: URLs, mappings, fixed values.

## 10. External Dependencies

*   Relies heavily on the structure and availability of the `tg.glasir.fo` website and its internal APIs. Changes to the website structure or API endpoints will likely break the extractor.
*   Requires a valid Glasir student account for authentication.
```