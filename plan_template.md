# Plan: [Brief Title of Task/Feature/Refactor]

**1. Overall Goal:**
*   _Clearly state the main objective. What is the desired outcome?_
    *   Example: Refactor the data processing pipeline to improve performance by 30%.
    *   Example: Implement user authentication using OAuth2.

**2. Current State & Motivation (Observation):**
*   _Describe the current situation, the problem being solved, or the reason for this plan. Why is this change necessary?_
*   _Reference specific observations, performance metrics, or user feedback if applicable._
    *   Example: The current timetable fetching process is sequential and takes X minutes for Y weeks.
    *   Example: Users currently lack a way to save their preferences.

**3. Proposed Solution / High-Level Approach:**
*   _Outline the general strategy, design, or architecture for achieving the goal._
*   _This section provides context before diving into detailed steps._
*   _(Optional: Include a Mermaid diagram for visualization if the approach is complex)._
    ```mermaid
    graph TD
        A[Start] --> B{Decision};
        B -- Yes --> C[Process 1];
        B -- No --> D[Process 2];
        C --> E[End];
        D --> E;
    ```

**4. Information Gathering / Pre-computation:**
*   _List files, code sections, or documentation that should be reviewed **before** starting the detailed steps. This ensures necessary context is understood upfront._
*   **Files/Areas to Review:**
    *   `[path/to/file1.ext]`:
        *   **Lines:** [e.g., `10-25`, `150-200` | `All lines`]
        *   **Focus:** [e.g., `function_name()`, `ClassName`, `Overall structure`, `Configuration values`]
        *   **Reason:** [e.g., Understand current data fetching logic, Identify relevant constants]
    *   `[path/to/file2.ext]`:
        *   **Lines:** [e.g., `All lines`]
        *   **Focus:** [e.g., Data models used in module X]
        *   **Reason:** [e.g., Ensure new code is compatible with existing data structures]
    *   `[path/to/directory/]`:
        *   **Focus:** [e.g., General structure of utility functions]
        *   **Reason:** [e.g., Identify potential reusable functions]
*   **Key Concepts/Context to Understand:**
    *   [e.g., Existing error handling patterns]
    *   [e.g., API rate limits for external service X]

**5. Detailed Steps / Sub-Tasks:**
*   _Break down the solution into specific, actionable steps._

    *   **Step 1: [Descriptive Title for Step 1]**
        *   **Goal:** [Specific objective for *this* step.]
        *   **Files to Read/Reference (During Step):** _(Optional: Files specifically needed *while* working on this step)_
            *   `[path/to/relevant_file.ext]`: [Lines M-N | Specific function]
        *   **Files to Modify:**
            *   `[path/to/modified_file1.ext]`
            *   `[path/to/created_file.ext]` (Indicate if new)
        *   **Detailed Changes/Actions:**
            *   [Describe the specific code changes, logic adjustments, configuration updates, or actions required.]
            *   [Use bullet points, code snippets (if brief), or clear descriptions.]
            *   [Be specific enough for another developer to understand the task.]
        *   **Expected Outcome/Impact:** [What will be achieved or changed by completing *this* step? How does it contribute to the overall goal?]

    *   **Step 2: [Descriptive Title for Step 2]**
        *   **Goal:** ...
        *   **Files to Modify:** ...
        *   **Detailed Changes/Actions:** ...
        *   **Expected Outcome/Impact:** ...

    *   **(Add more steps as needed)**

**6. Potential Risks & Considerations:**
*   _Identify potential challenges, dependencies, or side effects._
    *   [Risk 1: e.g., Breaking change for downstream consumers.]
    *   [Consideration 1: e.g., Need to update documentation.]
    *   [Consideration 2: e.g., Performance impact on other system parts.]

**7. Testing Strategy:**
*   _Outline how the changes will be verified._
    *   [e.g., Add new unit tests for function X.]
    *   [e.g., Update integration test Y.]
    *   [e.g., Manual testing steps: 1. Log in, 2. Navigate to Z, 3. Verify data format.]

**8. Summary / Key Actions:**
*   _(Optional: Briefly reiterate the main phases or most critical actions.)_