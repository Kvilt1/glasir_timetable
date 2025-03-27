# JavaScript-based Timetable Navigation

This implementation uses direct JavaScript navigation via the `MyUpdate()` function as described in the analysis report, rather than simulating UI clicks through Playwright.

## Architecture

This JavaScript navigation implementation consists of:

1. **timetable_navigation.js**: Core JavaScript functions for navigating and extracting timetable data
2. **js_integration.py**: Python module that injects the JavaScript and provides an interface for the main application
3. **main_js.py**: Modified main script that uses the JavaScript-based navigation

## Key Advantages

- **Direct API Use**: Uses the site's `MyUpdate()` function directly rather than simulating UI interactions
- **Faster Navigation**: No need to wait for UI elements to become clickable 
- **More Reliable**: Less likely to break if UI elements change position/style
- **Simpler Implementation**: Uses the site's internal navigation API as described in the analysis report

## How It Works

1. After login, the JavaScript file is injected into the page
2. The student ID is extracted from the page
3. Week navigation is performed using the `MyUpdate()` function directly
4. Timetable data is extracted using JavaScript DOM manipulation
5. Data is returned to Python and saved in the same format as before

## Usage

Run the JavaScript-based implementation using the `run_js_timetable.py` script:

```bash
python3 run_js_timetable.py --credentials-file credentials.json --weekforward 2 --weekbackward 2
```

Or run the modified main script directly:

```bash
python3 -m scripts.main_js --credentials-file credentials.json --weekforward 2 --weekbackward 2
```

### Testing the JavaScript Integration

You can test the JavaScript integration before extracting any data by using the `--test-js` flag:

```bash
python3 run_js_timetable.py --credentials-file credentials.json --test-js
```

This will verify that:
1. The JavaScript injection works correctly
2. The `MyUpdate()` function exists and is callable
3. Student ID can be extracted from the page
4. Week info can be extracted properly
5. Simple navigation works as expected

### Non-Headless Mode

By default, the browser runs in headless mode. If you want to see the browser while it's running (useful for debugging), disable headless mode:

```bash
python3 run_js_timetable.py --credentials-file credentials.json --weekforward 2
```

Or explicitly enable it:
```bash
python3 run_js_timetable.py --credentials-file credentials.json --weekforward 2 --headless
```

### Error Handling

The implementation now includes comprehensive error handling:

- JavaScript errors are properly caught and reported
- Screenshots are automatically saved when errors occur
- When errors happen during week navigation, the system attempts to continue with other weeks
- Descriptive error messages help diagnose issues quickly

## JavaScript Navigation Explained

The Glasir timetable system uses a JavaScript function called `MyUpdate()` for all navigation, with this signature:

```javascript
function MyUpdate(MyUrl, MyValue, MyInsertAreaId)
```

Parameters:
- `MyUrl`: The endpoint to call (typically '/i/udvalg.asp')
- `MyValue`: A query string with parameters:
  - `stude`: Indicates a student view
  - `id`: A GUID identifying the student/user
  - `v`: A week offset parameter controlling which week to display
- `MyInsertAreaId`: The DOM element ID where to insert the response (typically 'MyWindowMain')

Our implementation directly calls this function with the appropriate parameters, avoiding the need to simulate UI clicks. 