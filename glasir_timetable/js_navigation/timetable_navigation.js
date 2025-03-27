/**
 * Glasir Timetable Navigation Module
 * 
 * This script provides functions to navigate the Glasir timetable system
 * using the MyUpdate() JavaScript function as described in the analysis report.
 */

/**
 * Check if the MyUpdate function exists and is callable
 * 
 * @returns {boolean} - True if the MyUpdate function exists and is callable
 */
function checkMyUpdateExists() {
  return typeof MyUpdate === 'function';
}

/**
 * Navigate to a specific week using the week offset parameter
 * 
 * @param {number} weekOffset - The offset from the current week (0 = current, 1 = next, -1 = previous)
 * @param {string} studentId - The student ID GUID
 * @returns {Promise<Object>} - Information about the week that was navigated to
 */
function navigateToWeek(weekOffset, studentId) {
  return new Promise((resolve, reject) => {
    try {
      // First check if MyUpdate function exists
      if (!checkMyUpdateExists()) {
        reject(new Error("MyUpdate function not found. Navigation not possible."));
        return;
      }
      
      // Validate inputs
      if (typeof weekOffset !== 'number') {
        reject(new Error(`Week offset must be a number, got ${typeof weekOffset}`));
        return;
      }
      
      if (!studentId || typeof studentId !== 'string') {
        reject(new Error("Valid student ID is required for navigation"));
        return;
      }
      
      // Execute the navigation
      MyUpdate('/i/udvalg.asp', `stude&id=${studentId}&v=${weekOffset}`, 'MyWindowMain');
      
      // Allow minimal time for the navigation to complete - reduced from 500ms to 300ms
      // Using MutationObserver would be better but this is a simple optimization
      setTimeout(() => {
        try {
          // Extract information about the current week
          const weekInfo = extractWeekInfo();
          resolve(weekInfo);
        } catch (error) {
          reject(new Error(`Failed to extract week info after navigation: ${error.message}`));
        }
      }, 300);
    } catch (error) {
      reject(new Error(`Navigation failed: ${error.message}`));
    }
  });
}

/**
 * Extract information about the currently displayed week
 * 
 * @returns {Object} - Information about the current week
 */
function extractWeekInfo() {
  try {
    // Get the week information
    const bodyText = document.body.innerText;
    
    // Improved week number extraction - look for standard "Vika XX" format with more specific pattern
    // This regex now only captures 1-2 digits (weeks 1-53) and requires a delimiter after the number
    let weekMatch = bodyText.match(/Vika\s+(\d{1,2})(?:\s|$|\.|\,|\:|;)/i);
    
    // If that fails, try one more variation that might appear but still with strict digit limit
    if (!weekMatch) {
      weekMatch = bodyText.match(/Vika\s+(\d{1,2})/i); 
    }
    
    // If we have a match, parse the week number
    let weekNumber = null;
    if (weekMatch && weekMatch[1]) {
      weekNumber = parseInt(weekMatch[1]);
      
      // Simple validation that the week number is reasonable (1-53)
      if (weekNumber < 1 || weekNumber > 53) {
        console.warn(`Invalid week number detected: ${weekNumber}, may be incorrect`);
        // Don't try to "fix" it - better to know it's wrong than guess incorrectly
      }
    }
    
    if (!weekNumber) {
      console.warn("Could not extract week number from page");
    }
    
    // Get the date range - improved to handle various formats
    let dateRangeMatch = bodyText.match(/(\d{1,2}\.\d{1,2}\.\d{4})\s*-\s*(\d{1,2}\.\d{1,2}\.\d{4})/);
    
    // Try alternative format if the first one fails
    if (!dateRangeMatch) {
      dateRangeMatch = bodyText.match(/(\d{1,2}\/\d{1,2}[\/\-]\d{4})\s*-\s*(\d{1,2}\/\d{1,2}[\/\-]\d{4})/);
    }
    
    // Extract and normalize date format
    const startDate = dateRangeMatch ? dateRangeMatch[1].replace(/\//g, '.').replace(/-/g, '.') : null;
    const endDate = dateRangeMatch ? dateRangeMatch[2].replace(/\//g, '.').replace(/-/g, '.') : null;
    
    // Ensure full date format (YYYY.MM.DD)
    let formattedStartDate = startDate;
    let formattedEndDate = endDate;
    
    if (startDate && !startDate.match(/^\d{4}/)) {
      // If year is at the end (DD.MM.YYYY), move it to front
      const parts = startDate.split('.');
      if (parts.length === 3 && parts[2].length === 4) {
        formattedStartDate = `${parts[2]}.${parts[1]}.${parts[0]}`;
      }
    }
    
    if (endDate && !endDate.match(/^\d{4}/)) {
      // If year is at the end (DD.MM.YYYY), move it to front
      const parts = endDate.split('.');
      if (parts.length === 3 && parts[2].length === 4) {
        formattedEndDate = `${parts[2]}.${parts[1]}.${parts[0]}`;
      }
    }
    
    if (!startDate || !endDate) {
      console.warn("Could not extract date range from page");
    }
    
    // Get year from the date if available, otherwise current year
    const year = startDate ? parseInt(startDate.match(/\d{4}/)[0]) : new Date().getFullYear();
    
    return {
      weekNumber,
      year,
      startDate: formattedStartDate,
      endDate: formattedEndDate
    };
  } catch (error) {
    throw new Error(`Failed to extract week info: ${error.message}`);
  }
}

/**
 * Extract all timetable data from the current view
 * 
 * @returns {Object} - Structured timetable data
 */
function extractTimetableData() {
  try {
    // Get the week information
    const weekInfo = extractWeekInfo();
    
    // Extract classes from the timetable
    const classes = [];
    const classLinks = document.querySelectorAll('a[onclick*="group&v=0&id="]');
    
    if (classLinks.length === 0) {
      console.warn("No class links found in the timetable");
    }
    
    classLinks.forEach(link => {
      try {
        // Get the parent cell to find associated teacher and room
        const cell = link.closest('td');
        if (!cell) {
          console.warn(`Cannot find parent cell for class: ${link.innerText}`);
          return;
        }
        
        const teacherLink = cell.querySelector('a[onclick*="teach&v=0&id="]');
        const roomLink = cell.querySelector('a[onclick*="room_&v=0&id="]');
        
        // Try to determine the day and time from the table structure
        const dayIndex = getDayIndex(cell);
        const timeSlot = getTimeSlot(cell);
        
        classes.push({
          className: link.innerText,
          teacher: teacherLink ? teacherLink.innerText : null,
          teacherFullName: getTeacherFullName(teacherLink ? teacherLink.innerText : null),
          room: roomLink ? roomLink.innerText : null,
          day: dayIndex,
          timeSlot: timeSlot
        });
      } catch (error) {
        console.warn(`Failed to extract data for a class: ${error.message}`);
      }
    });
    
    return {
      weekInfo,
      classes
    };
  } catch (error) {
    throw new Error(`Failed to extract timetable data: ${error.message}`);
  }
}

/**
 * Get the day index (0-6) for a cell in the timetable
 * 
 * @param {HTMLElement} cell - The cell element
 * @returns {number} - The day index (0 = Monday, 6 = Sunday)
 */
function getDayIndex(cell) {
  try {
    // This is a simplified implementation and may need adjustments based on the actual table structure
    const tr = cell.closest('tr');
    if (!tr) return null;
    
    const allCells = Array.from(tr.children);
    const cellIndex = allCells.indexOf(cell);
    
    // Adjust index based on table structure (first column may be time labels)
    return Math.max(0, cellIndex - 1);
  } catch (error) {
    console.warn(`Failed to get day index: ${error.message}`);
    return null;
  }
}

/**
 * Get the time slot for a cell in the timetable
 * 
 * @param {HTMLElement} cell - The cell element
 * @returns {Object} - Time slot information
 */
function getTimeSlot(cell) {
  try {
    // This is a simplified implementation and may need adjustments based on the actual table structure
    const tr = cell.closest('tr');
    if (!tr) return { text: '' };
    
    const timeCell = tr.firstElementChild;
    const timeText = timeCell ? timeCell.innerText.trim() : '';
    
    // Try to parse time information
    const timeMatch = timeText.match(/(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})/);
    if (timeMatch) {
      return {
        startTime: `${timeMatch[1]}:${timeMatch[2]}`,
        endTime: `${timeMatch[3]}:${timeMatch[4]}`,
        text: timeText
      };
    }
    
    return { text: timeText };
  } catch (error) {
    console.warn(`Failed to get time slot: ${error.message}`);
    return { text: '' };
  }
}

/**
 * Get teacher's full name from initials (if available)
 * 
 * @param {string} initials - Teacher initials
 * @returns {string|null} - Full name or null if not found
 */
function getTeacherFullName(initials) {
  try {
    // This would need to be populated from data available in the system
    const teacherMap = {
      // Example mappings
      'BIJ': 'Bjarni Johnson',
      'JOH': 'Johannes Hansen',
      'HSV': 'Helena Svabo'
      // Real implementation would need to populate this from the system
    };
    
    return initials && teacherMap[initials] ? teacherMap[initials] : null;
  } catch (error) {
    console.warn(`Failed to get teacher full name: ${error.message}`);
    return null;
  }
}

/**
 * Get the student ID from the page
 * 
 * @returns {string|null} - The student ID GUID
 */
function getStudentId() {
  try {
    // Look for student ID in links on the page
    const studentLinks = document.querySelectorAll('a[onclick*="stude&id="]');
    for (const link of studentLinks) {
      const onclick = link.getAttribute('onclick') || '';
      const idMatch = onclick.match(/stude&id=([^&]+)/);
      if (idMatch && idMatch[1]) {
        return idMatch[1];
      }
    }
    
    // Alternative: try to find it in the URL
    const urlParams = new URLSearchParams(window.location.search);
    const idParam = urlParams.get('id');
    if (idParam) {
      return idParam;
    }
    
    console.warn("Could not find student ID in the page");
    return null;
  } catch (error) {
    console.warn(`Failed to get student ID: ${error.message}`);
    return null;
  }
}

/**
 * Extract homework content for a specific lesson
 * 
 * @param {string} lessonId - The lesson ID from the speech bubble onclick attribute
 * @returns {string} - The extracted homework content
 */
function extractHomeworkContent(lessonId) {
  try {
    console.log(`Extracting homework for lesson ${lessonId} directly...`);
    
    // Find the note button
    const noteButton = document.querySelector(`input[type="image"][src*="note.gif"][onclick*="${lessonId}"]`);
    if (!noteButton) {
      console.warn(`Note button for lesson ${lessonId} not found`);
      return "Homework note button not found";
    }
    
    // Get the onclick attribute to analyze how the popup is created
    const onclickAttr = noteButton.getAttribute('onclick');
    if (!onclickAttr) {
      console.warn(`Note button has no onclick attribute for lesson ${lessonId}`);
      return "Homework button missing onclick attribute";
    }
    
    // Parse the onclick attribute
    const match = onclickAttr.match(/MyUpdate\s*\(\s*['"]([^'"]+)['"]\s*,\s*['"]([^'"]+)['"]/);
    if (!match) {
      console.warn(`Could not parse onclick attribute for lesson ${lessonId}`);
      return "Could not parse note button attributes";
    }
    
    const [_, url, params] = match;
    console.log(`Extracted URL: ${url}, Params: ${params}`);
    
    // Use XMLHttpRequest directly to fetch the content
    // This is more reliable than trying to use the existing MyUpdate function
    let homeworkContent = null;
    let syncRequest = new XMLHttpRequest();
    
    // Make a synchronous request to get the data immediately
    syncRequest.open("POST", url, false); // false = synchronous
    syncRequest.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
    
    // Prepare the form data similar to what MyUpdate would send
    const data = `fname=Henry&timex=${window.timer || 0}&rnd=${Math.random()}&MyInsertAreaId=tempContent&lname=Ford39502&q=${params.replace(/ /g, "+")}`;
    
    try {
      console.log(`Making direct XMLHttpRequest to: ${url}`);
      syncRequest.send(data);
      
      if (syncRequest.status === 200) {
        homeworkContent = syncRequest.responseText;
        console.log(`Successfully received content, length: ${homeworkContent.length} characters`);
      } else {
        console.warn(`Request failed: status ${syncRequest.status}`);
        return `Request failed: status ${syncRequest.status}`;
      }
    } catch (requestError) {
      console.warn(`XMLHttpRequest failed: ${requestError.message}`);
      
      // Try an alternative approach with fetch and a longer timeout
      try {
        console.log(`Trying alternative approach with async fetch...`);
        
        // Create a temporary div to hold the content
        let tempDiv = document.createElement('div');
        tempDiv.id = 'tempContentContainer';
        tempDiv.style.display = 'none';
        document.body.appendChild(tempDiv);
        
        // Wait a moment before simulating the click
        setTimeout(() => {
          // Force redirect response to our temporary div
          window.MyUpdate = function(url, params, targetId) {
            fetch(url, {
              method: 'POST',
              headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
              body: `fname=Henry&timex=${window.timer || 0}&rnd=${Math.random()}&MyInsertAreaId=tempContentContainer&lname=Ford39502&q=${params.replace(/ /g, "+")}`
            })
            .then(response => response.text())
            .then(text => {
              document.getElementById('tempContentContainer').innerHTML = text;
            });
          };
          
          // Click the button to trigger the modified MyUpdate
          noteButton.click();
        }, 100);
        
        // Wait longer than normal since this is a fallback
        let startTime = new Date().getTime();
        let maxWaitTime = 5000; // 5 seconds
        while (!homeworkContent && new Date().getTime() - startTime < maxWaitTime) {
          // Check if our temp div has content
          const container = document.getElementById('tempContentContainer');
          if (container && container.innerHTML.length > 30) {
            homeworkContent = container.innerHTML;
            console.log(`Got content through alternate method, length: ${homeworkContent.length}`);
            break;
          }
          
          // Short busy wait
          const waitStart = new Date().getTime();
          while (new Date().getTime() < waitStart + 100) { /* busy wait */ }
        }
        
        // Clean up our temp div
        document.body.removeChild(tempDiv);
      } catch (fetchError) {
        console.warn(`Alternate approach also failed: ${fetchError.message}`);
        return `Failed to fetch homework: ${fetchError.message}`;
      }
    }
    
    // If we have content, extract the actual homework
    if (homeworkContent) {
      // Parse the HTML content
      const tempDiv = document.createElement('div');
      tempDiv.innerHTML = homeworkContent;
      
      // Strategy 1: Look for a textarea with the note content
      const noteTextArea = tempDiv.querySelector('textarea[name="NoteText"]');
      if (noteTextArea) {
        console.log(`Found homework in textarea: ${noteTextArea.value ? noteTextArea.value.substring(0, 30) : "empty"}`);
        if (noteTextArea.value && noteTextArea.value.trim().length > 0) {
          return noteTextArea.value;
        }
      }
      
      // Strategy 2: Look for the text displayed in the form
      const notesTable = tempDiv.querySelector('table.Notes');
      if (notesTable) {
        const noteText = notesTable.textContent.trim();
        if (noteText.length > 0) {
          console.log(`Found homework in notes table: ${noteText.substring(0, 30)}...`);
          return noteText;
        }
      }
      
      // Strategy 3: Look for paragraphs with "Heimaarbeiði"
      const paragraphs = tempDiv.querySelectorAll('p');
      for (const para of paragraphs) {
        if (para.textContent.includes('Heimaarbeiði') || para.innerHTML.includes('Heimaarbeiði')) {
          // For paragraphs with Heimaarbeiði, the content usually comes after a <br>
          if (para.innerHTML.includes('<br>')) {
            const parts = para.innerHTML.split('<br>');
            const content = parts.slice(1).join('<br>').trim();
            console.log(`Found homework after Heimaarbeiði <br>: ${content.substring(0, 30)}...`);
            return content;
          } else {
            const content = para.textContent.replace('Heimaarbeiði', '').trim();
            console.log(`Found homework in Heimaarbeiði paragraph: ${content.substring(0, 30)}...`);
            return content;
          }
        }
      }
      
      // Strategy 4: Get any substantial text
      const allText = tempDiv.textContent.trim();
      if (allText.length > 20) {
        console.log(`Found text content: ${allText.substring(0, 30)}...`);
        return allText;
      }
      
      // Strategy 5: Return the raw HTML as a last resort
      console.log(`No structured content found, returning raw HTML (sanitized)`);
      return homeworkContent.replace(/<[^>]*>/g, ' ').trim() || "No content found in response";
    }
    
    return "Failed to retrieve homework content";
  } catch (error) {
    console.error(`Error extracting homework for ${lessonId}: ${error.message}`);
    return `Error: ${error.message}`;
  }
}

/**
 * Extract homework content for multiple lessons one by one
 * 
 * @param {Array<string>} lessonIds - Array of lesson IDs to extract homework for
 * @returns {Object} - Mapping of lesson IDs to their homework content
 */
function extractAllHomeworkContent(lessonIds) {
  if (!Array.isArray(lessonIds) || lessonIds.length === 0) {
    return {};
  }
  
  const homeworkMap = {};
  
  try {
    console.log(`Processing ${lessonIds.length} homework notes via JavaScript SEQUENTIALLY (direct method)`);
    
    // Process each lesson one at a time
    for (let i = 0; i < lessonIds.length; i++) {
      try {
        const lessonId = lessonIds[i];
        console.log(`Processing homework ${i+1}/${lessonIds.length} for lesson ${lessonId}`);
        
        // Extract homework content directly
        const content = extractHomeworkContent(lessonId);
        
        // Store the result
        homeworkMap[lessonId] = content || "No homework content found";
        
        // Debug output
        if (content) {
          console.log(`Found homework for ${lessonId}: ${content.substring(0, 30)}...`);
        } else {
          console.log(`No homework content found for ${lessonId}`);
        }
        
        // Short delay between processing each note
        const pauseStart = new Date().getTime();
        while (new Date().getTime() < pauseStart + 200) { /* short delay between notes */ }
      } catch (error) {
        console.error(`Error processing lesson ${lessonIds[i]}: ${error.message}`);
        homeworkMap[lessonIds[i]] = `Error: ${error.message}`;
      }
    }
    
    console.log(`Completed processing of ${Object.keys(homeworkMap).length} homework notes`);
  } catch (error) {
    console.error(`Error in batch homework processing: ${error.message}`);
  }
  
  return homeworkMap;
}

// Export functions to make them available to the page context
window.glasirTimetable = {
  checkMyUpdateExists,
  navigateToWeek,
  extractTimetableData,
  extractWeekInfo,
  getStudentId,
  extractHomeworkContent,
  extractAllHomeworkContent
}; 