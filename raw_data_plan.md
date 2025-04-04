# Plan: Refactor Week Info Extraction & Range Determination

**1. Overall Goal:**
*   Refactor the `glasir_timetable` project to utilize week information (year, week number, start/end dates) directly extracted from the raw HTML responses provided by the Glasir API (`udvalg.asp` endpoint), replacing the current calculation-based fallbacks.
*   Implement a more robust method for determining the full range of available weeks (min/max offsets), potentially spanning multiple academic years.

**2. Current State & Motivation (Observation):**
*   The current week info extraction in `extractors/timetable.py::parse_timetable_html` often fails to parse the date range directly from the HTML, falling back to calculations based on partial date info and the system year (evidenced by `INFO - Using calculated week info` logs). This can lead to inaccuracies if the HTML structure changes or if the partial date info is ambiguous.
*   The current week range determination in `api_client.py::extract_week_range` relies on parsing the HTML of the *current* week only, which might not reflect the full range of weeks available in the week selector, especially across different academic years.

**3. Proposed Solution / High-Level Approach:**
*   Modify the HTML parsing logic (`parse_timetable_html`) to specifically target and extract the week number and full date range from the known structure of the `udvalg.asp` response HTML. Prioritize using this extracted data.
*   Refactor the week range determination logic (`extract_week_range`) to use the `fetch_weeks_data` and `parse_weeks_html_response` functions, which are designed to fetch and parse the week selector data directly. Optionally, investigate using the `v_override` parameter to query multiple academic years for a truly comprehensive range.

    ```mermaid
    graph TD
        subgraph Task: Use Extracted Week Info & Improve Range
            A[Start] --> B{Analyze Code & HTML};
            B --> C{Plan Refactoring};
            C --> D[Refactor `parse_timetable_html`];
            D --> D1[Extract Week Num from Link];
            D --> D2[Extract Date Range from Text Node];
            D --> D3[Prioritize Extracted Data in `week_info`];
            D --> D4[Add Logging (Extracted/Calculated)];
            C --> E[Refactor Week Range Logic];
            E --> E1[Modify `extract_week_range`];
            E1 --> E2[Call `fetch_weeks_data`];
            E1 --> E3[Call `parse_weeks_html_response`];
            E1 --> E4[Determine Min/Max Offset];
            E --> E5[Investigate `v_override` (Optional)];
            C --> F[Update Callers];
            F --> F1[Check `navigation.py`];
            F --> F2[Check `main.py`];
            C --> G[Plan Testing];
            G --> G1[Unit Tests (Optional)];
            G --> G2[Integration Tests];
            G2 --> G3[Test Single Week (Check Logs)];
            G2 --> G4[Test `--allweeks` (Check Range)];
            G2 --> G5[Verify JSON Output];
            G5 --> H[End];
        end

        style D fill:#f9f,stroke:#333,stroke-width:2px
        style E fill:#f9f,stroke:#333,stroke-width:2px
        style F fill:#ccf,stroke:#333,stroke-width:1px
        style G fill:#cfc,stroke:#333,stroke-width:1px
    ```

**4. Information Gathering / Pre-computation:**
*   **Files/Areas to Review:**
    *   `glasir_timetable/extractors/timetable.py`:
        *   **Lines:** `235-588` (approx. `parse_timetable_html` function)
        *   **Focus:** Current date range and week number extraction logic, `week_info` population.
        *   **Reason:** Understand where the calculation fallback occurs and how to replace it with direct extraction.
    *   `glasir_timetable/api_client.py`:
        *   **Lines:** `864-1082` (`fetch_weeks_data`, `parse_weeks_html_response`), `1271-1331` (`extract_week_range`)
        *   **Focus:** Functions related to fetching/parsing the week selector and determining the week range.
        *   **Reason:** Understand how to modify `extract_week_range` to use the correct fetching/parsing functions. Assess feasibility of using `v_override`.
    *   `glasir_timetable/raw_responses/`:
        *   **Focus:** Example files like `raw_timetable_week0_...html`, `raw_timetable_week1_...html`.
        *   **Reason:** Confirm the exact HTML structure containing the week number (`UgeKnapValgt`) and the date range text node.
    *   `glasir_timetable/navigation.py`:
        *   **Lines:** `107-207` (`process_weeks`), `239-270` (`extract_min_max_week_offsets`)
        *   **Focus:** How `week_info` and the week range are used.
        *   **Reason:** Ensure integration points are correctly updated.
    *   `glasir_timetable/main.py`:
        *   **Focus:** Argument parsing (`--allweeks`), main processing loop.
        *   **Reason:** Ensure the `--allweeks` functionality uses the improved week range.
*   **Key Concepts/Context to Understand:**
    *   Difference between `fetch_timetable_for_week` (fetches main grid) and `fetch_weeks_data` (fetches week selector).
    *   Purpose and potential usage of the `v` parameter in API calls (`v_override`).

**5. Detailed Steps / Sub-Tasks:**

    *   **Step 1: Refactor `parse_timetable_html` for Direct Extraction**
        *   **Goal:** Reliably extract week number, start date, end date, and year directly from the HTML content of `udvalg.asp` responses.
        *   **Files to Modify:**
            *   `glasir_timetable/extractors/timetable.py`
        *   **Detailed Changes/Actions:**
            *   Inside `parse_timetable_html`, locate the week selector table (e.g., `<table border=1 ...>`).
            *   Find the `<a>` tag with class `UgeKnapValgt` within this table. Extract text (e.g., "Vika 14") and parse the integer week number. Store in `extracted_week_num`. Log success and source.
            *   Find the text node immediately following the week selector table. Use regex `(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}\.\d{2}\.\d{4})` to extract start/end date strings. Store in `start_date_str`, `end_date_str`. Log success and source.
            *   Attempt to parse `start_date_str` and `end_date_str` into `datetime` objects (`parsed_start_date`, `parsed_end_date`). Extract `year` from `parsed_start_date`.
            *   Modify the `week_info` population logic (around lines 485-554):
                *   Check if `extracted_week_num`, `parsed_start_date`, and `parsed_end_date` were successfully obtained.
                *   If yes, use these values to populate `week_info` (week_num, year, start_date, end_date, week_key). Log that "extracted" data was used.
                *   If no, fall back to the *existing* calculation logic (using `first_date_obj`). Log that "calculated" data was used.
            *   Remove the old regex logic for finding the date range within the table parent or other elements (lines ~267-290).
        *   **Expected Outcome/Impact:** `week_info` dictionary will be populated with accurate data directly from the HTML when possible, reducing reliance on calculations. Logs will clearly indicate the source of the week data.

    *   **Step 2: Refactor `extract_week_range` for Robustness**
        *   **Goal:** Make the determination of minimum and maximum available week offsets more reliable by using the dedicated week selector endpoint.
        *   **Files to Modify:**
            *   `glasir_timetable/api_client.py`
        *   **Detailed Changes/Actions:**
            *   Inside `extract_week_range` (lines ~1271-1331):
                *   Remove the call to `fetch_timetable_for_week`.
                *   Add a call to `fetch_weeks_data`, passing necessary arguments (cookies, student_id, lname, timer, potentially `v_override=0` initially).
                *   Check if the HTML content was successfully fetched.
                *   If HTML exists, call `parse_weeks_html_response` with the fetched HTML.
                *   If parsing is successful and returns a dictionary with a 'weeks' list:
                    *   Extract all 'offset' values from the 'weeks' list.
                    *   Calculate and return `min(offsets)` and `max(offsets)`.
                *   If any step fails (fetching, parsing, no offsets), raise a `ValueError` or return a default range (e.g., `(0, 0)`) with appropriate error logging.
        *   **Expected Outcome/Impact:** The function will return a more accurate range of available week offsets based on the actual week selector data.

    *   **Step 3: (Optional) Investigate Multi-Year Week Range**
        *   **Goal:** Extend week range determination across academic years.
        *   **Files to Modify:**
            *   `glasir_timetable/api_client.py` (within `extract_week_range`)
        *   **Detailed Changes/Actions:**
            *   Modify `extract_week_range` to loop through a set of `v_override` values (e.g., `0`, `-52`, `+52`).
            *   Inside the loop, call `fetch_weeks_data` and `parse_weeks_html_response` for each `v_override` value.
            *   Collect all extracted 'offset' values into a single list.
            *   Handle potential errors for each individual fetch/parse.
            *   After the loop, calculate the min/max from the combined list of offsets.
        *   **Expected Outcome/Impact:** `--allweeks` functionality will potentially cover multiple academic years if the API supports it via the `v` parameter.

    *   **Step 4: Verify Integration**
        *   **Goal:** Ensure the refactored functions are used correctly by callers.
        *   **Files to Read/Reference (During Step):**
            *   `glasir_timetable/navigation.py`
            *   `glasir_timetable/main.py`
        *   **Files to Modify:** None (Verification step)
        *   **Detailed Changes/Actions:**
            *   Review `navigation.py::process_weeks` to confirm it correctly handles the `week_info` dictionary returned by the updated `parse_timetable_html`.
            *   Review `navigation.py::extract_min_max_week_offsets` to confirm it calls the updated `api_client.py::extract_week_range`.
            *   Review `main.py` where `--allweeks` is handled to ensure it uses the result from `extract_min_max_week_offsets`.
        *   **Expected Outcome/Impact:** Confidence that the refactored components are correctly integrated into the application flow.

**6. Potential Risks & Considerations:**
*   **HTML Structure Changes:** The direct extraction relies heavily on the current HTML structure of the `udvalg.asp` response. Future changes by Glasir could break the parsing. The fallback mechanism mitigates this partially.
*   **`v_override` Behavior:** The exact behavior of the `v` parameter for fetching different academic years is assumed. If it doesn't work as expected, the multi-year range enhancement might not be feasible.
*   **Error Handling:** Robust error handling is needed during fetching and parsing in both refactored functions.

**7. Testing Strategy:**
*   **Refactor `parse_timetable_html`:**
    *   Run the script for the current week (`--week 0` or default).
    *   **Check Logs:** Verify logs show "Extracted week number..." and "Extracted date range..." and "Using extracted week info...". Confirm the logged values match the raw HTML.
    *   **Check JSON:** Inspect the generated JSON file for week 0. Verify the `weekInfo` section has the correct, directly extracted values.
*   **Refactor `extract_week_range`:**
    *   Run the script with `--allweeks`.
    *   **Check Logs:** Verify the logs indicate the min/max offsets determined by `extract_week_range`. Compare these with the offsets visible in the week selector links in the raw HTML.
    *   **(If multi-year implemented):** Check if the logged range spans expected years and if weeks outside the current academic year are processed.
*   **General:** Manually compare the `weekInfo` in several generated JSON files against their corresponding raw HTML responses in `glasir_timetable/raw_responses/` to ensure accuracy.

**8. Summary / Key Actions:**
*   Modify `parse_timetable_html` to prioritize direct extraction of week number and date range.
*   Modify `extract_week_range` to use `fetch_weeks_data` and `parse_weeks_html_response`.
*   Add logging to track extraction sources.
*   Test thoroughly using logs and generated JSON files.