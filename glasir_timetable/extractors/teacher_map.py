#!/usr/bin/env python3
"""
Module for extracting teacher mapping from the Glasir timetable.
"""

async def extract_teacher_map(page):
    """
    Extract teacher map from the timetable page.
    Returns a dictionary mapping teacher initials to full names with initials.
    
    Args:
        page: The Playwright page object.
        
    Returns:
        dict: A mapping of teacher initials to full names.
    """
    print("Extracting teacher mapping from page...")
    
    # Use JavaScript to extract teacher information from the table
    teacher_map = await page.evaluate("""
    () => {
      // Find the teacher table - it's usually the one containing "Lærari" as header
      const tables = Array.from(document.querySelectorAll('table'));
      let teacherTable = null;
      
      for (const table of tables) {
        const text = table.innerText;
        if (text.includes('Lærari') && text.includes('Hold')) {
          teacherTable = table;
          break;
        }
      }
      
      if (!teacherTable) return {};
      
      const teacherMap = {};
      const rows = teacherTable.querySelectorAll('tr');
      
      // Start from row 1 (skip header row)
      for (let i = 1; i < rows.length; i++) {
        const cells = rows[i].querySelectorAll('td');
        if (cells.length === 0) continue;
        
        const teacherCell = cells[0];
        const text = teacherCell.textContent.trim();
        
        // Check if this is a teacher cell (contains initials in parentheses)
        const match = text.match(/(.*?)\\s*\\(([A-Z]{2,4})\\)\\s*$/);
        if (match) {
          const fullName = match[1].trim();
          const initials = match[2].trim();
          teacherMap[initials] = `${fullName} (${initials})`;
        }
      }
      
      return teacherMap;
    }
    """)
    
    if not teacher_map:
        print("Warning: Could not extract teacher mapping from the page. Using default mapping.")
        # Fallback to a minimal default mapping if extraction fails
        teacher_map = {
            "BIJ": "Brynjálvur I. Johansen (BIJ)",
            "DTH": "Durita Thomsen (DTH)",
            "HSV": "Henriette Svenstrup (HSV)",
            "JBJ": "Jan Berg Jørgensen (JBJ)",
            "JOH": "Jón Mikael Degn í Haraldstovu (JOH)",
            "PEY": "Pætur Eysturskarð (PEY)",
            "TJA": "Tina Kildegaard Jakobsen (TJA)"
        }
    else:
        print(f"Successfully extracted teacher mapping for {len(teacher_map)} teachers.")
    
    return teacher_map 