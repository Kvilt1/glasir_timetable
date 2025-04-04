# Plan: Refactor and Improve Glasir Timetable Project

**1. Overall Goal:**
*   Improve the maintainability, performance, and reliability of the Glasir Timetable project. This includes reducing code duplication, improving error handling, and migrating more logic to the API.

**2. Current State & Motivation (Observation):**
*   The current codebase has several areas of code duplication, particularly in API request handling and data extraction.
*   Performance bottlenecks exist due to reliance on Playwright for certain tasks and inefficient regex-based parsing.
*   Error handling is inconsistent, with a mix of `@handle_errors` and `try...except` blocks.
*   The project relies on extracting dynamic parameters from the page, which can be fragile and prone to errors.

**3. Proposed Solution / High-Level Approach:**
*   Refactor the codebase to reduce code duplication and improve modularity.
*   Migrate more logic to the API to improve performance and reduce reliance on Playwright.
*   Implement a consistent error handling strategy.
*   Improve the reliability of dynamic parameter extraction.
*   Consolidate configuration values into `constants.py`.

**4. Information Gathering / Pre-computation:**
*   **Files/Areas to Review:**
    *   `glasir_timetable/api_client.py`:
        *   **Lines:** All lines
        *   **Focus:** API request handling, teacher map extraction, homework extraction
        *   **Reason:** Identify code duplication and potential performance bottlenecks.
    *   `glasir_timetable/auth.py`:
        *   **Lines:** All lines
        *   **Focus:** Authentication logic
        *   **Reason:** Identify hardcoded URLs and potential improvements to error handling.
    *   `glasir_timetable/navigation.py`:
        *   **Lines:** All lines
        *   **Focus:** Week navigation, student ID extraction
        *   **Reason:** Identify areas for simplification and improved reliability.
    *   `glasir_timetable/services.py`:
        *   **Lines:** All lines
        *   **Focus:** Service interfaces and implementations
        *   **Reason:** Understand the overall architecture and identify areas for improvement.
    *   `glasir_timetable/extractors/timetable.py`:
        *   **Lines:** All lines
        *   **Focus:** Timetable data extraction logic
        *   **Reason:** Understand how timetable data is extracted from HTML.
    *   `glasir_timetable/constants.py`:
        *   **Lines:** All lines
        *   **Focus:** Configuration values and URLs
        *   **Reason:** Identify hardcoded values that should be constants.
*   **Key Concepts/Context to Understand:**
    *   Existing error handling patterns
    *   API rate limits for external service X
    *   Dynamic parameter extraction logic
    *   Data models used in the project

**5. Detailed Steps / Sub-Tasks:**

    *   **Step 0: Analyze All Files**
        *   **Goal:** To analyze every file and every line in the project.
        *   **Files to Modify:**
            *   None
        *   **Detailed Changes/Actions:**
            *   Use `list_files` to get a recursive list of all files in the project.
            *   For each file, use `read_file` to read its contents.
            *   Analyze the code in each file, looking for potential areas for improvement, optimization, and cleanup.
        *   **Expected Outcome/Impact:** A comprehensive understanding of the entire codebase.

    *   **Step 1: Create a Base API Request Function**
        *   **Goal:** Reduce code duplication in `api_client.py` by creating a base function for handling API requests.
        *   **Files to Modify:**
            *   `glasir_timetable/api_client.py`
        *   **Detailed Changes/Actions:**
            *   Create a new function (e.g., `_api_request`) that takes the API URL, parameters, headers, and cookies as input.
            *   Move the code for setting up the `httpx.AsyncClient`, handling exceptions, and saving raw responses to this function.
            *   Update the `fetch_homework_for_lesson`, `fetch_teacher_mapping`, `fetch_weeks_data`, and `fetch_timetable_for_week` functions to use the `_api_request` function.
        *   **Expected Outcome/Impact:** Reduced code duplication and improved maintainability.

    *   **Step 2: Refactor Teacher Map Extraction**
        *   **Goal:** Improve the robustness and efficiency of teacher map extraction.
        *   **Files to Modify:**
            *   `glasir_timetable/api_client.py`
            *   `glasir_timetable/extractors/teacher_map.py`
        *   **Detailed Changes/Actions:**
            *   Consolidate the regex patterns used in `extract_teachers_from_html` into a single, more comprehensive pattern.
            *   Consider using a more efficient HTML parsing library (e.g., `lxml`) for teacher map extraction.
            *   Move the teacher map extraction logic to `glasir_timetable/extractors/teacher_map.py` and create a dedicated function for API-based extraction.
        *   **Expected Outcome/Impact:** Improved teacher map extraction accuracy and performance.

    *   **Step 3: Improve Dynamic Parameter Extraction**
        *   **Goal:** Improve the reliability and maintainability of dynamic parameter extraction.
        *   **Files to Modify:**
            *   `glasir_timetable/utils/param_utils.py`
            *   `glasir_timetable/session.py`
        *   **Detailed Changes/Actions:**
            *   Consolidate all dynamic parameter extraction logic into the `parse_dynamic_params` function in `utils.param_utils.py`.
            *   Remove the deprecated `get_dynamic_session_params` function in `session.py`.
            *   Update the `AuthSessionManager` to use the `parse_dynamic_params` function for fetching parameters.
        *   **Expected Outcome/Impact:** More reliable and maintainable dynamic parameter extraction.

    *   **Step 4: Implement Consistent Error Handling**
        *   **Goal:** Implement a consistent error handling strategy throughout the codebase.
        *   **Files to Modify:**
            *   All files
        *   **Detailed Changes/Actions:**
            *   Use the `@handle_errors` decorator consistently for all API requests and data extraction functions.
            *   Remove redundant `try...except` blocks and rely on the decorator for error logging and handling.
            *   Ensure that all exceptions are properly logged with traceback information.
        *   **Expected Outcome/Impact:** More consistent and reliable error handling.

    *   **Step 5: Migrate Hardcoded URLs to Constants**
        *   **Goal:** Improve maintainability by moving hardcoded URLs to constants.
        *   **Files to Modify:**
            *   `glasir_timetable/auth.py`
            *   `glasir_timetable/navigation.py`
            *   `glasir_timetable/constants.py`
        *   **Detailed Changes/Actions:**
            *   Define constants for all hardcoded URLs in `constants.py`.
            *   Update the code to use these constants instead of hardcoded URLs.
        *   **Expected Outcome/Impact:** Improved maintainability and easier configuration.

    *   **Step 6: Refactor Student ID Extraction**
        *   **Goal:** Consolidate student ID extraction logic into a single function.
        *   **Files to Modify:**
            *   `glasir_timetable/student_utils.py`
            *   `glasir_timetable/navigation.py`
            *   `glasir_timetable/services.py`
        *   **Detailed Changes/Actions:**
            *   Move the student ID extraction logic from `PlaywrightNavigationService` and `ApiExtractionService` to the `get_student_id` function in `student_utils.py`.
            *   Update the code to use the `get_student_id` function for extracting the student ID.
        *   **Expected Outcome/Impact:** Reduced code duplication and improved maintainability.

    *   **Step 7: Analyze and Improve Raw Response Handling**
        *   **Goal:** Improve the raw response handling.
        *   **Files to Modify:**
            *   `glasir_timetable/__init__.py`
            *   `glasir_timetable/api_client.py`
        *   **Detailed Changes/Actions:**
            *   Update the filename construction for raw responses to include more relevant information (e.g., the URL being requested, request parameters).
            *   Make the raw response saving directory configurable via command-line arguments.
        *   **Expected Outcome/Impact:** More informative raw response filenames and improved configuration options.

**6. Potential Risks & Considerations:**
*   Changes to API request handling could break existing functionality. Thorough testing is required.
*   Refactoring the authentication logic could introduce security vulnerabilities. Careful review is needed.
*   Changes to data extraction logic could result in incorrect or incomplete data.
*   The Glasir website structure could change, requiring updates to the extraction logic.

**7. Testing Strategy:**
*   Add new unit tests for the base API request function.
*   Update existing unit tests to ensure that the refactored code works correctly.
*   Add integration tests to verify the end-to-end functionality of the application.
*   Manually test the application to ensure that all features are working as expected.

**8. Summary / Key Actions:**
*   Analyze all files in the project.
*   Create a base API request function to reduce code duplication.
*   Refactor teacher map extraction for improved robustness and efficiency.
*   Improve dynamic parameter extraction for better reliability.
*   Implement a consistent error handling strategy.
*   Migrate hardcoded URLs to constants.
*   Consolidate student ID extraction logic.
*   Improve raw response handling.