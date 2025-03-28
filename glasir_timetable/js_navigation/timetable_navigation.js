/**
 * Glasir Timetable Navigation Module
 * 
 * This script provides functions to navigate the Glasir timetable system
 * using the MyUpdate() JavaScript function as described in the analysis report.
 */

// Configuration object to control behavior
window.glasirTimetable = window.glasirTimetable || {
  // When true, allows UI-based methods as fallback when JS methods fail
  // When false, will only use JavaScript methods and fail fast
  useUIFallback: false,
  
  // Set debug level: 0=none, 1=warnings, 2=info, 3=debug
  debugLevel: 1,
  
  // Cache for storing frequently accessed data
  _cache: {
    weekInfo: null,
    studentId: null,
    allWeeks: null,
    domQueries: {},  // Map of query selector to element references
    homeworkContent: {}  // Map of lesson ID to homework content
  },
  
  /**
   * Clear all cache entries
   */
  clearCache: function() {
    this._cache.weekInfo = null;
    this._cache.studentId = null;
    this._cache.allWeeks = null;
    this._cache.domQueries = {};
    this._cache.homeworkContent = {};
    console.log("Cache cleared");
  },
  
  /**
   * Clear specific cache entry or category
   * 
   * @param {string} cacheType - Type of cache to clear: 'weekInfo', 'studentId', 
   *                            'allWeeks', 'domQueries', 'homeworkContent', or 'all'
   */
  clearCacheType: function(cacheType) {
    if (!cacheType || cacheType === 'all') {
      this.clearCache();
      return;
    }
    
    if (cacheType in this._cache) {
      if (typeof this._cache[cacheType] === 'object' && !Array.isArray(this._cache[cacheType])) {
        this._cache[cacheType] = {};
      } else {
        this._cache[cacheType] = null;
      }
      console.log(`Cache '${cacheType}' cleared`);
    } else {
      console.warn(`Unknown cache type: ${cacheType}`);
    }
  },
  
  // DOM Utilities
  dom: {
    /**
     * Query a DOM element with caching
     * 
     * @param {string} selector - CSS selector
     * @param {HTMLElement} context - Optional element to query within (defaults to document)
     * @returns {HTMLElement} - The found element
     */
    querySelector: function(selector, context = document) {
      const cacheKey = `qs:${selector}:${context === document ? 'doc' : context.tagName}`;
      if (!glasirTimetable._cache.domQueries[cacheKey]) {
        glasirTimetable._cache.domQueries[cacheKey] = context.querySelector(selector);
      }
      return glasirTimetable._cache.domQueries[cacheKey];
    },
    
    /**
     * Query multiple DOM elements with caching
     * 
     * @param {string} selector - CSS selector
     * @param {HTMLElement} context - Optional element to query within (defaults to document)
     * @returns {Array<HTMLElement>} - Array of found elements
     */
    querySelectorAll: function(selector, context = document) {
      const cacheKey = `qsa:${selector}:${context === document ? 'doc' : context.tagName}`;
      if (!glasirTimetable._cache.domQueries[cacheKey]) {
        glasirTimetable._cache.domQueries[cacheKey] = Array.from(context.querySelectorAll(selector));
      }
      return glasirTimetable._cache.domQueries[cacheKey];
    },
    
    /**
     * Find closest parent matching a selector
     * 
     * @param {HTMLElement} element - Starting element
     * @param {string} selector - CSS selector to match
     * @returns {HTMLElement|null} - The found parent or null
     */
    closest: function(element, selector) {
      if (!element) return null;
      return element.closest(selector);
    },
    
    /**
     * Get text content from an element
     * 
     * @param {HTMLElement} element - Element to get text from
     * @returns {string} - Trimmed text content
     */
    getText: function(element) {
      if (!element) return '';
      return (element.innerText || element.textContent || '').trim();
    }
  },
  
  // String and Date Utilities
  utils: {
    /**
     * Format a date string to a consistent format (YYYY.MM.DD)
     * 
     * @param {string} dateStr - Date string to format
     * @returns {string|null} - Formatted date or null if invalid
     */
    formatDate: function(dateStr) {
      if (!dateStr) return null;
      
      // Replace slashes with dots for consistency
      dateStr = dateStr.replace(/\//g, '.').replace(/-/g, '.');
      
      // Check if year is at the end (DD.MM.YYYY)
      if (!dateStr.match(/^\d{4}/)) {
        // If year is at the end, move it to front
        const parts = dateStr.split('.');
        if (parts.length === 3 && parts[2].length === 4) {
          return `${parts[2]}.${parts[1]}.${parts[0]}`;
        }
      }
      
      return dateStr;
    },
    
    /**
     * Parse a week number from a string
     * 
     * @param {string} text - Text to parse
     * @returns {number|null} - Week number or null if not found
     */
    parseWeekNumber: function(text) {
      if (!text) return null;
      
      // Try standard "Vika XX" format with specific pattern
      let weekMatch = text.match(/Vika\s+(\d{1,2})(?:\s|$|\.|\,|\:|;)/i);
      
      // Try alternate format if first one fails
      if (!weekMatch) {
        weekMatch = text.match(/Vika\s+(\d{1,2})/i);
      }
      
      if (weekMatch && weekMatch[1]) {
        const weekNumber = parseInt(weekMatch[1]);
        
        // Validate week number
        if (weekNumber < 1 || weekNumber > 53) {
          console.warn(`Invalid week number detected: ${weekNumber}, may be incorrect`);
        }
        
        return weekNumber;
      }
      
      return null;
    },
    
    /**
     * Extract date range from text
     * 
     * @param {string} text - Text to parse
     * @returns {Object} - Object with startDate and endDate
     */
    extractDateRange: function(text) {
      if (!text) return { startDate: null, endDate: null };
      
      // Try standard format (DD.MM.YYYY - DD.MM.YYYY)
      let dateRangeMatch = text.match(/(\d{1,2}\.\d{1,2}\.\d{4})\s*-\s*(\d{1,2}\.\d{1,2}\.\d{4})/);
      
      // Try alternative format if the first one fails
      if (!dateRangeMatch) {
        dateRangeMatch = text.match(/(\d{1,2}\/\d{1,2}[\/\-]\d{4})\s*-\s*(\d{1,2}\/\d{1,2}[\/\-]\d{4})/);
      }
      
      // Extract and normalize date format
      const startDate = dateRangeMatch ? this.formatDate(dateRangeMatch[1]) : null;
      const endDate = dateRangeMatch ? this.formatDate(dateRangeMatch[2]) : null;
      
      return { startDate, endDate };
    },
    
    /**
     * Get the day name for an index
     * 
     * @param {number} index - Day index (0=Monday, 6=Sunday)
     * @returns {string} - Day name
     */
    getDayName: function(index) {
      const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
      return (index >= 0 && index < days.length) ? days[index] : '';
    },
    
    /**
     * Extract year from a date string or use current year
     * 
     * @param {string} dateStr - Date string
     * @returns {number} - Year as integer
     */
    extractYear: function(dateStr) {
      if (!dateStr) return new Date().getFullYear();
      
      const yearMatch = dateStr.match(/\d{4}/);
      return yearMatch ? parseInt(yearMatch[0]) : new Date().getFullYear();
    }
  },
  
  // Data Extraction Methods
  extractors: {
    /**
     * Extract information about the currently displayed week
     * 
     * @returns {Object} - Information about the current week
     */
    weekInfo: function() {
      try {
        // Check if we have cached week info
        if (glasirTimetable._cache.weekInfo) {
          return glasirTimetable._cache.weekInfo;
        }
        
        // Get the week information from body text
        const bodyText = document.body.innerText;
        
        // Parse week number
        const weekNumber = glasirTimetable.utils.parseWeekNumber(bodyText);
        
        if (!weekNumber) {
          console.warn("Could not extract week number from page");
        }
        
        // Extract date range
        const { startDate, endDate } = glasirTimetable.utils.extractDateRange(bodyText);
        
        if (!startDate || !endDate) {
          console.warn("Could not extract date range from page");
        }
        
        // Get year from the date if available, otherwise current year
        const year = glasirTimetable.utils.extractYear(startDate);
        
        // Create week info object
        const weekInfo = {
          weekNumber,
          year,
          startDate,
          endDate
        };
        
        // Cache the result
        glasirTimetable._cache.weekInfo = weekInfo;
        
        return weekInfo;
      } catch (error) {
        throw new Error(`Failed to extract week info: ${error.message}`);
      }
    },
    
    /**
     * Extract classes from the timetable
     * 
     * @returns {Array} - Array of class objects
     */
    classes: function() {
      try {
        const classes = [];
        
        // Use our utility for querying with caching
        const classLinks = glasirTimetable.dom.querySelectorAll('a[onclick*="group&v=0&id="]');
        
        if (classLinks.length === 0) {
          console.warn("No class links found in the timetable");
        }
        
        classLinks.forEach(link => {
          try {
            // Get the parent cell to find associated teacher and room
            const cell = glasirTimetable.dom.closest(link, 'td');
            if (!cell) {
              console.warn(`Cannot find parent cell for class: ${link.innerText}`);
              return;
            }
            
            // Find teacher and room links
            const teacherLink = glasirTimetable.dom.querySelector('a[onclick*="teach&v=0&id="]', cell);
            const roomLink = glasirTimetable.dom.querySelector('a[onclick*="room_&v=0&id="]', cell);
            
            // Try to determine the day and time from the table structure
            const dayIndex = this.getDayIndex(cell);
            const timeSlot = this.getTimeSlot(cell);
            
            classes.push({
              className: glasirTimetable.dom.getText(link),
              teacher: teacherLink ? glasirTimetable.dom.getText(teacherLink) : null,
              teacherFullName: this.getTeacherFullName(teacherLink ? teacherLink.innerText.trim() : null),
              room: roomLink ? glasirTimetable.dom.getText(roomLink) : null,
              day: dayIndex,
              timeSlot: timeSlot
            });
          } catch (error) {
            console.warn(`Failed to extract data for a class: ${error.message}`);
          }
        });
        
        return classes;
      } catch (error) {
        throw new Error(`Failed to extract classes: ${error.message}`);
      }
    },
    
    /**
     * Get the day index (0-6) for a cell in the timetable
     * 
     * @param {HTMLElement} cell - The cell element
     * @returns {number} - The day index (0 = Monday, 6 = Sunday)
     */
    getDayIndex: function(cell) {
      try {
        const tr = glasirTimetable.dom.closest(cell, 'tr');
        if (!tr) return null;
        
        const allCells = Array.from(tr.children);
        const cellIndex = allCells.indexOf(cell);
        
        // Adjust index based on table structure (first column may be time labels)
        return Math.max(0, cellIndex - 1);
      } catch (error) {
        console.warn(`Failed to get day index: ${error.message}`);
        return null;
      }
    },
    
    /**
     * Get the time slot for a cell in the timetable
     * 
     * @param {HTMLElement} cell - The cell element
     * @returns {Object} - Time slot information
     */
    getTimeSlot: function(cell) {
      try {
        const tr = glasirTimetable.dom.closest(cell, 'tr');
        if (!tr) return { text: '' };
        
        const timeCell = tr.firstElementChild;
        const timeText = glasirTimetable.dom.getText(timeCell);
        
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
    },
    
    /**
     * Get teacher's full name from initials (if available)
     * 
     * @param {string} initials - Teacher initials
     * @returns {string|null} - Full name or null if not found
     */
    getTeacherFullName: function(initials) {
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
    },
    
    /**
     * Get the student ID from the page
     * 
     * @returns {string|null} - The student ID GUID
     */
    studentId: function() {
      try {
        // Check cache first
        if (glasirTimetable._cache.studentId) {
          return glasirTimetable._cache.studentId;
        }
        
        // Look for student ID in links on the page
        const studentLinks = glasirTimetable.dom.querySelectorAll('a[onclick*="stude&id="]');
        for (const link of studentLinks) {
          const onclick = link.getAttribute('onclick') || '';
          const idMatch = onclick.match(/stude&id=([^&]+)/);
          if (idMatch && idMatch[1]) {
            // Store in cache before returning
            glasirTimetable._cache.studentId = idMatch[1];
            return glasirTimetable._cache.studentId;
          }
        }
        
        // Alternative: try to find it in the URL
        const urlParams = new URLSearchParams(window.location.search);
        const idParam = urlParams.get('id');
        if (idParam) {
          // Store in cache before returning
          glasirTimetable._cache.studentId = idParam;
          return glasirTimetable._cache.studentId;
        }
        
        console.warn("Could not find student ID in the page");
        return null;
      } catch (error) {
        console.warn(`Failed to get student ID: ${error.message}`);
        return null;
      }
    },
    
    /**
     * Extract homework content for a specific lesson
     * 
     * @param {string} lessonId - The lesson ID from the speech bubble onclick attribute
     * @returns {string} - The extracted homework content
     */
    homeworkContent: function(lessonId) {
      try {
        // Check cache first
        if (glasirTimetable._cache.homeworkContent[lessonId]) {
          console.log(`Using cached homework content for lesson ${lessonId}`);
          return glasirTimetable._cache.homeworkContent[lessonId];
        }
        
        console.log(`Extracting homework for lesson ${lessonId} directly...`);
        
        // Find the note button
        const noteButtonSelector = `input[type="image"][src*="note.gif"][onclick*="${lessonId}"]`;
        const noteButton = glasirTimetable.dom.querySelector(noteButtonSelector);
        
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
          
          // Extract and clean the homework text
          let homework = glasirTimetable.dom.getText(tempDiv);
          
          // Remove Heimaarbeiði prefix that appears at the beginning
          homework = homework.replace(/^Heimaarbeiði\s*/i, '');
          
          // Cache the result before returning
          glasirTimetable._cache.homeworkContent[lessonId] = homework;
          
          return homework;
        } else {
          return "Failed to retrieve homework content";
        }
      } catch (error) {
        console.warn(`Error extracting homework: ${error.message}`);
        return `Error: ${error.message}`;
      }
    },
    
    /**
     * Extract homework content for multiple lessons one by one
     * 
     * @param {Array<string>} lessonIds - Array of lesson IDs to extract homework for
     * @returns {Object} - Mapping of lesson IDs to their homework content
     */
    allHomeworkContent: function(lessonIds) {
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
            const content = this.homeworkContent(lessonId);
            
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
    },
    
    /**
     * Get all available weeks from the timetable navigation.
     * @returns {Array} Array of week objects with properties: weekNum, v, weekText, isCurrentWeek
     */
    allWeeks: function() {
      try {
        // Return cached result if available
        if (glasirTimetable._cache.allWeeks) {
          console.log("Using cached weeks data");
          return glasirTimetable._cache.allWeeks;
        }
        
        // Find all week buttons
        const buttons = glasirTimetable.dom.querySelectorAll('.UgeKnap, .UgeKnapValgt');
        console.log("Found week buttons:", buttons.length);
        
        // Process each button
        const weeks = buttons.map(btn => {
          const onclick = btn.getAttribute('onclick') || '';
          const vMatch = onclick.match(/v=(-?\d+)/);
          const v = vMatch ? parseInt(vMatch[1]) : null;
          const weekText = glasirTimetable.dom.getText(btn);
          const weekNum = weekText.match(/\d+/) ? parseInt(weekText.match(/\d+/)[0]) : null;
          
          // Is this the currently selected week?
          const isCurrentWeek = btn.className.includes('UgeKnapValgt');
          
          // Get position information
          let rowIndex = -1;
          let colIndex = -1;
          let month = null;
          
          // Get location in the table
          const parentTd = glasirTimetable.dom.closest(btn, 'td');
          const parentTr = parentTd ? glasirTimetable.dom.closest(parentTd, 'tr') : null;
          
          if (parentTr) {
            rowIndex = Array.from(document.querySelectorAll('tr')).indexOf(parentTr);
            colIndex = Array.from(parentTr.querySelectorAll('td')).indexOf(parentTd);
            
            // Try to determine the month from nearby month headers
            const monthHeaders = Array.from(parentTr.querySelectorAll('td')).filter(td => {
              const text = glasirTimetable.dom.getText(td).toLowerCase();
              return text.match(/jan|feb|mar|apr|mai|jun|jul|aug|sep|okt|nov|des/i);
            });
            
            if (monthHeaders.length > 0) {
              // Find closest month header
              let closestHeader = null;
              let minDistance = Infinity;
              
              for (const header of monthHeaders) {
                const headerIndex = Array.from(parentTr.querySelectorAll('td')).indexOf(header);
                const distance = Math.abs(headerIndex - colIndex);
                
                if (distance < minDistance) {
                  minDistance = distance;
                  closestHeader = header;
                }
              }
              
              if (closestHeader) {
                const text = glasirTimetable.dom.getText(closestHeader).toLowerCase();
                const monthMatch = text.match(/jan|feb|mar|apr|mai|jun|jul|aug|sep|okt|nov|des/i);
                if (monthMatch) {
                  month = monthMatch[0].toLowerCase();
                }
              }
            }
          }
          
          return {
            weekNum,
            v,
            weekText,
            rowIndex,
            colIndex,
            month,
            isCurrentWeek
          };
        }).filter(item => item.weekNum !== null && item.v !== null);
        
        // Cache the processed weeks before returning
        glasirTimetable._cache.allWeeks = weeks;
        
        return weeks;
      } catch (error) {
        console.error(`Error getting all weeks: ${error.message}`);
        return [];
      }
    }
  },
  
  // Public API methods (for backward compatibility)
  /**
   * Check if the MyUpdate function exists and is callable
   * 
   * @returns {boolean} - True if the MyUpdate function exists and is callable
   */
  checkMyUpdateExists: function() {
    return typeof MyUpdate === 'function';
  },
  
  /**
   * Navigate to a specific week using the week offset parameter
   * 
   * @param {number} weekOffset - The offset from the current week (0 = current, 1 = next, -1 = previous)
   * @param {string} studentId - The student ID GUID
   * @returns {Promise<Object>} - Information about the week that was navigated to
   */
  navigateToWeek: function(weekOffset, studentId) {
    return new Promise((resolve, reject) => {
      try {
        // First check if MyUpdate function exists
        if (!this.checkMyUpdateExists()) {
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
        
        // Clear week info cache on navigation
        this._cache.weekInfo = null;
        
        // Execute the navigation
        MyUpdate('/i/udvalg.asp', `stude&id=${studentId}&v=${weekOffset}`, 'MyWindowMain');
        
        // Allow minimal time for the navigation to complete - reduced from 500ms to 300ms
        setTimeout(() => {
          try {
            // Extract information about the current week
            const weekInfo = this.extractors.weekInfo();
            resolve(weekInfo);
          } catch (error) {
            reject(new Error(`Failed to extract week info after navigation: ${error.message}`));
          }
        }, 300);
      } catch (error) {
        reject(new Error(`Navigation failed: ${error.message}`));
      }
    });
  },
  
  /**
   * Extract information about the currently displayed week
   * 
   * @returns {Object} - Information about the current week
   */
  extractWeekInfo: function() {
    return this.extractors.weekInfo();
  },
  
  /**
   * Extract all timetable data from the current view
   * 
   * @returns {Object} - Structured timetable data
   */
  extractTimetableData: function() {
    try {
      // Get the week information
      const weekInfo = this.extractors.weekInfo();
      
      // Extract classes
      const classes = this.extractors.classes();
      
      return {
        weekInfo,
        classes
      };
    } catch (error) {
      throw new Error(`Failed to extract timetable data: ${error.message}`);
    }
  },
  
  /**
   * Get the student ID from the page
   * 
   * @returns {string|null} - The student ID GUID
   */
  getStudentId: function() {
    return this.extractors.studentId();
  },
  
  /**
   * Extract homework content for a specific lesson
   * 
   * @param {string} lessonId - The lesson ID from the speech bubble onclick attribute
   * @returns {string} - The extracted homework content
   */
  extractHomeworkContent: function(lessonId) {
    return this.extractors.homeworkContent(lessonId);
  },
  
  /**
   * Extract homework content for multiple lessons one by one
   * 
   * @param {Array<string>} lessonIds - Array of lesson IDs to extract homework for
   * @returns {Object} - Mapping of lesson IDs to their homework content
   */
  extractAllHomeworkContent: function(lessonIds) {
    return this.extractors.allHomeworkContent(lessonIds);
  },
  
  /**
   * Get all available weeks from the timetable navigation.
   * @returns {Array} Array of week objects
   */
  getAllWeeks: function() {
    return this.extractors.allWeeks();
  }
};

// For backwards compatibility, make some functions directly accessible
// This allows existing code to call these functions without the namespace
function checkMyUpdateExists() {
  return glasirTimetable.checkMyUpdateExists();
}

function navigateToWeek(weekOffset, studentId) {
  return glasirTimetable.navigateToWeek(weekOffset, studentId);
}

function extractWeekInfo() {
  return glasirTimetable.extractWeekInfo();
}

function extractTimetableData() {
  return glasirTimetable.extractTimetableData();
}

function getStudentId() {
  return glasirTimetable.getStudentId();
}

function extractHomeworkContent(lessonId) {
  return glasirTimetable.extractHomeworkContent(lessonId);
}

function extractAllHomeworkContent(lessonIds) {
  return glasirTimetable.extractAllHomeworkContent(lessonIds);
}

function getAllWeeks() {
  return glasirTimetable.getAllWeeks();
} 