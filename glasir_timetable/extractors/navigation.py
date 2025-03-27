#!/usr/bin/env python3
"""
Module for navigating between weeks in the Glasir timetable.

DEPRECATION NOTICE:
------------------
This module provides UI-based navigation which is now deprecated.
The preferred approach is to use JavaScript-based navigation from the
glasir_timetable.js_navigation module, which is faster and more reliable.

This module is kept for backward compatibility and as a fallback when
JavaScript navigation is not available.
"""
import re
import asyncio
import json
from datetime import datetime, timedelta
import logging
from glasir_timetable import logger

async def analyze_week_structure(page):
    """
    Pre-check all weeks in the navigation, identify academic year sections,
    and determine which section the current week belongs to.
    
    Returns:
    - all_weeks: List of all available weeks with their v-values
    - academic_year_sections: Dictionary mapping academic year names to their week data
    - current_section: The academic year section the current week belongs to
    """
    logger.info("Analyzing timetable week structure...")
    
    # Extract all week buttons and their v-values with row information
    all_weeks = await page.evaluate("""
    () => {
        // Find all week buttons
        const buttons = Array.from(document.querySelectorAll('.UgeKnap, .UgeKnapValgt'));
        
        // Map to store months by row (week buttons are usually in rows by month)
        const monthsByRow = {};
        
        // Find month headers
        document.querySelectorAll('td').forEach(td => {
            const text = td.textContent.trim().toLowerCase();
            const monthMatch = text.match(/jan|feb|mar|apr|mai|jun|jul|aug|sep|okt|nov|des/i);
            if (monthMatch) {
                const month = monthMatch[0].toLowerCase();
                // Find the row this month header belongs to
                const row = td.closest('tr');
                if (row) {
                    const rowIndex = Array.from(document.querySelectorAll('tr')).indexOf(row);
                    if (!(rowIndex in monthsByRow)) {
                        monthsByRow[rowIndex] = [];
                    }
                    monthsByRow[rowIndex].push({
                        month: month,
                        position: Array.from(row.querySelectorAll('td')).indexOf(td)
                    });
                }
            }
        });
        
        // Parse each button with precise location information
        const result = buttons.map(btn => {
            const onclick = btn.getAttribute('onclick') || '';
            const vMatch = onclick.match(/v=(-?\\d+)/);
            const v = vMatch ? parseInt(vMatch[1]) : null;
            const weekText = btn.textContent.trim();
            const weekNum = weekText.match(/\\d+/) ? parseInt(weekText.match(/\\d+/)[0]) : null;
            
            // Get precise location in the table
            let rowIndex = -1;
            let colIndex = -1;
            let parentTd = btn.closest('td');
            let parentTr = parentTd ? parentTd.closest('tr') : null;
            
            if (parentTr) {
                rowIndex = Array.from(document.querySelectorAll('tr')).indexOf(parentTr);
                colIndex = Array.from(parentTr.querySelectorAll('td')).indexOf(parentTd);
            }
            
            // Determine the month based on row and column position
            let month = null;
            if (rowIndex in monthsByRow) {
                // Find closest month header in this row
                let closest = null;
                let minDistance = Infinity;
                
                for (const monthInfo of monthsByRow[rowIndex]) {
                    const distance = Math.abs(monthInfo.position - colIndex);
                    if (distance < minDistance) {
                        minDistance = distance;
                        closest = monthInfo;
                    }
                }
                
                if (closest) {
                    month = closest.month;
                }
            }
            
            // Is this the currently selected week?
            const isCurrentWeek = btn.className.includes('UgeKnapValgt');
            
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
        
        // Add year information based on row and month patterns
        // First half academic year: Aug-Dec (33-52)
        // Second half academic year: Jan-Jul (1-32)
        const firstHalfMonths = ['aug', 'sep', 'okt', 'nov', 'des'];
        const secondHalfMonths = ['jan', 'feb', 'mar', 'apr', 'mai', 'jun', 'jul'];
        
        // Group weeks by row to identify year breaks
        const rowGroups = {};
        result.forEach(week => {
            if (!(week.rowIndex in rowGroups)) {
                rowGroups[week.rowIndex] = [];
            }
            rowGroups[week.rowIndex].push(week);
        });
        
        // Sort rows by index
        const sortedRows = Object.keys(rowGroups).map(Number).sort((a, b) => a - b);
        
        // Identify academic year boundaries by analyzing rows
        let currentYear = 1;
        let previousRow = null;
        
        sortedRows.forEach(rowIndex => {
            const currentRow = rowGroups[rowIndex];
            
            // Sort weeks in this row by column
            currentRow.sort((a, b) => a.colIndex - b.colIndex);
            
            // Check if this row starts a new academic year
            let startsNewYear = false;
            
            if (previousRow) {
                const prevLastWeek = previousRow[previousRow.length - 1];
                const currFirstWeek = currentRow[0];
                
                // If week number jumps significantly or resets, likely a new year
                if (currFirstWeek.weekNum < prevLastWeek.weekNum && 
                    (prevLastWeek.weekNum - currFirstWeek.weekNum > 20)) {
                    startsNewYear = true;
                }
                
                // If month transitions from July to August, likely a new year
                if (prevLastWeek.month === 'jul' && currFirstWeek.month === 'aug') {
                    startsNewYear = true;
                }
            }
            
            if (startsNewYear) {
                currentYear++;
            }
            
            // Assign year to all weeks in this row
            currentRow.forEach(week => {
                week.academicYear = currentYear;
                
                // More precise academic year calculation
                if (week.month) {
                    if (firstHalfMonths.includes(week.month)) {
                        // First half (Aug-Dec): Year X/X+1
                        week.academicYearText = `${new Date().getFullYear()}/${new Date().getFullYear() + 1}`;
                    } else if (secondHalfMonths.includes(week.month)) {
                        // Second half (Jan-Jul): Year X-1/X
                        week.academicYearText = `${new Date().getFullYear() - 1}/${new Date().getFullYear()}`;
                    } else {
                        week.academicYearText = `Year ${week.academicYear}`;
                    }
                } else {
                    week.academicYearText = `Year ${week.academicYear}`;
                }
            });
            
            previousRow = currentRow;
        });
        
        return result;
    }
    """)
    
    logger.info(f"Found {len(all_weeks)} week buttons in the navigation")
    
    # Sort weeks by v-value to examine the pattern
    sorted_by_v = sorted(all_weeks, key=lambda w: w.get('v', 0))
    
    # Group weeks by academic year
    academic_year_sections = {}
    for week in all_weeks:
        year_key = week.get('academicYearText', f"Year {week.get('academicYear', 1)}")
        if year_key not in academic_year_sections:
            academic_year_sections[year_key] = []
        academic_year_sections[year_key].append(week)
    
    # Create direct mappings of week numbers to v-values for each academic year
    for year_key, weeks in academic_year_sections.items():
        # Group weeks with same week number to find duplicates
        week_num_groups = {}
        for week in weeks:
            week_num = week['weekNum']
            if week_num not in week_num_groups:
                week_num_groups[week_num] = []
            week_num_groups[week_num].append(week)
        
        # Log duplicate week numbers for debugging
        duplicates = {num: weeks for num, weeks in week_num_groups.items() if len(weeks) > 1}
        if duplicates:
            logger.info(f"Section {year_key} has duplicate week numbers: {', '.join(map(str, duplicates.keys()))}")
            for week_num, dup_weeks in duplicates.items():
                logger.info(f"  Week {week_num}: v-values {', '.join(map(lambda w: str(w['v']), dup_weeks))}")
    
    # Determine which section contains the current week
    current_section_key = None
    for key, section in academic_year_sections.items():
        if any(w.get('isCurrentWeek', False) for w in section):
            current_section_key = key
            logger.info(f"Current week belongs to section: {key}")
            break
    
    # If we couldn't find the current section, fallback to a heuristic
    if not current_section_key and academic_year_sections:
        # Estimate best section based on current date
        now = datetime.now()
        current_month = now.month
        if 8 <= current_month <= 12:  # August-December: first half of academic year
            year_key = f"{now.year}/{now.year+1}"
        else:  # January-July: second half of academic year
            year_key = f"{now.year-1}/{now.year}"
            
        # Find a section that best matches this year pattern
        for section_key in academic_year_sections.keys():
            if year_key in section_key:
                current_section_key = section_key
                break
        
        # If still no match, use the most recent section
        if not current_section_key:
            current_section_key = list(academic_year_sections.keys())[-1]
            
        logger.info(f"Estimated current week belongs to section: {current_section_key}")
    
    # Print comprehensive information about each section
    for key, section in academic_year_sections.items():
        sorted_weeks = sorted(section, key=lambda w: w['weekNum'])
        week_nums = [w['weekNum'] for w in sorted_weeks]
        
        # Create a v-value mapping for each week number
        v_mapping = {}
        for week in sorted_weeks:
            week_num = week['weekNum']
            # Ensure we don't overwrite v-values for the currently selected week
            if week_num not in v_mapping or week.get('isCurrentWeek', False):
                v_mapping[week_num] = week['v']
        
        # Add the mapping to each week section
        academic_year_sections[key] = {
            'weeks': section,
            'v_mapping': v_mapping
        }
        
        logger.info(f"Section {key}: Weeks {', '.join(map(str, week_nums))}")
        logger.info(f"  V-value mapping: {json.dumps(v_mapping)}")
    
    return all_weeks, academic_year_sections, current_section_key

async def find_week_v_value(page, target_week_offset):
    """
    Find the v-value required to navigate to a specific week relative to the current week.
    target_week_offset: 0 for current week, 1 for next week, -1 for previous week, etc.
    Returns the v-value needed to navigate to that week.
    
    Enhanced to stay within the same academic year when navigating.
    """
    logger.info(f"Finding v-value for week offset: {target_week_offset}")
    
    # Get current week number
    current_week_info = await get_current_week_info(page)
    current_week_num = current_week_info.get('weekNumber')
    
    if current_week_num is None:
        logger.warning("Warning: Could not determine current week number, using default v-value.")
        return target_week_offset  # Fallback to the old behavior
    
    # Calculate the target week number
    target_week_num = current_week_num + target_week_offset
    
    # Extract all week navigation buttons with their months and positions
    week_buttons = await page.evaluate("""
    () => {
        // Helper function to determine academic year for a week button
        function determineAcademicYear(weekNum, month, position) {
            // Standard academic year has weeks 33-52 (Aug-Dec) followed by weeks 1-32 (Jan-Jul)
            // First half of academic year has higher week numbers (33-52)
            // Second half has lower week numbers (1-32)
            
            // If we have month information, use it to determine the half of the academic year
            if (month) {
                const firstHalfMonths = ['aug', 'sep', 'okt', 'nov', 'des'];
                const secondHalfMonths = ['jan', 'feb', 'mar', 'apr', 'mai', 'jun', 'jul'];
                
                const isFirstHalf = firstHalfMonths.includes(month.toLowerCase());
                const isSecondHalf = secondHalfMonths.includes(month.toLowerCase());
                
                if (isFirstHalf) {
                    return position <= 7 ? 'year1' : 'year2'; // First 7 positions are first academic year
                } else if (isSecondHalf) {
                    return position <= 7 ? 'year1' : 'year2'; // First 7 positions are first academic year
                }
            }
            
            // Fallback to using position in the table
            return position <= 7 ? 'year1' : 'year2';
        }
        
        // Find all week buttons and their parent cells
        const buttons = Array.from(document.querySelectorAll('.UgeKnap, .UgeKnapValgt'));
        
        // Get all the table cells that might contain month information
        const monthCells = Array.from(document.querySelectorAll('td')).filter(td => {
            const text = td.textContent.trim().toLowerCase();
            return ['jan', 'feb', 'mar', 'apr', 'mai', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'des'].some(
                month => text.includes(month)
            );
        });
        
        // Parse each button
        return buttons.map((btn, index) => {
            const onclick = btn.getAttribute('onclick') || '';
            const vMatch = onclick.match(/v=(-?\\d+)/);
            const v = vMatch ? vMatch[1] : null;
            const weekText = btn.textContent.trim();
            const weekNum = weekText.match(/\\d+/) ? parseInt(weekText.match(/\\d+/)[0]) : null;
            
            // Find the closest month cell for this button
            let month = null;
            let position = index; // Button position in the sequence
            
            // Try to find the month by looking at parent cell's previous siblings
            let parentTd = btn.closest('td');
            if (parentTd) {
                let parentTr = parentTd.closest('tr');
                if (parentTr) {
                    // Find all TDs in this row
                    const tdElements = Array.from(parentTr.querySelectorAll('td'));
                    // Find position of parent TD in the row
                    position = tdElements.indexOf(parentTd);
                    
                    // Check for month information
                    const monthCell = monthCells.find(cell => {
                        // If this month cell is in the same column as the button's parent 
                        const cellIndex = Array.from(cell.parentNode.children).indexOf(cell);
                        return cellIndex === position;
                    });
                    
                    if (monthCell) {
                        const monthMatch = monthCell.textContent.trim().match(/jan|feb|mar|apr|mai|jun|jul|aug|sep|okt|nov|des/i);
                        if (monthMatch) {
                            month = monthMatch[0].toLowerCase();
                        }
                    }
                }
            }
            
            // Determine which academic year this button belongs to
            const academicYear = determineAcademicYear(weekNum, month, position);
            
            // Is this the currently selected week?
            const isCurrentWeek = btn.className.includes('UgeKnapValgt');
            
            return {
                weekNum,
                v,
                text: weekText,
                month,
                position,
                academicYear,
                isCurrentWeek
            };
        }).filter(item => item.weekNum !== null && item.v !== null);
    }
    """)
    
    # Identify which academic year the current week belongs to
    current_academic_year = None
    for button in week_buttons:
        if button.get('isCurrentWeek', False):
            current_academic_year = button.get('academicYear')
            break
    
    if not current_academic_year:
        logger.warning("Warning: Could not determine current academic year, will use all week buttons.")
    else:
        logger.info(f"Current week is in academic year: {current_academic_year}")
        # Filter to only include buttons from the same academic year
        week_buttons = [btn for btn in week_buttons if btn.get('academicYear') == current_academic_year]
    
    # Sort the buttons by week number to ensure proper sequencing
    week_buttons.sort(key=lambda btn: btn['weekNum'])
    
    # Find the button with the current week
    current_week_button = None
    for button in week_buttons:
        if button.get('isCurrentWeek', False):
            current_week_button = button
            break
    
    if not current_week_button:
        logger.warning("Warning: Could not find the button for the current week.")
        # Find the button that matches our target week number
        for button in week_buttons:
            if button['weekNum'] == target_week_num:
                logger.info(f"Found v-value {button['v']} for week {target_week_num}")
                return button['v']
    else:
        # Find the button at the right offset from the current week
        current_index = week_buttons.index(current_week_button)
        target_index = current_index + target_week_offset
        
        if 0 <= target_index < len(week_buttons):
            target_button = week_buttons[target_index]
            logger.info(f"Found v-value {target_button['v']} for week {target_button['weekNum']} (offset {target_week_offset} from current week {current_week_num})")
            return target_button['v']
    
    logger.warning(f"Warning: Could not find v-value for target week (offset {target_week_offset}), using default v-value.")
    return target_week_offset  # Fallback to the old behavior

async def navigate_to_week(page, target_week_offset):
    """
    Navigate to a specific week relative to the current week
    target_week_offset: 0 for current week, 1 for next week, -1 for previous week, etc.
    """
    logger.info(f"Navigating to week with offset: {target_week_offset}...")
    
    # Get current week info before navigation
    current_week_info = await get_current_week_info(page)
    current_week_num = current_week_info.get('weekNumber')
    expected_week_num = current_week_num + target_week_offset if current_week_num else None
    
    if expected_week_num:
        logger.info(f"Current week: {current_week_num}, expecting to navigate to week: {expected_week_num}")
    
    # Find the correct v-value for the target week
    v_value = await find_week_v_value(page, target_week_offset)
    
    # Determine the current URL pattern
    current_url = page.url
    base_url = current_url.split('#')[0]
    
    # Try to find and click the link with the appropriate v parameter
    link_found = await page.evaluate(f"""
    () => {{
        // Look for links that have both the correct v-value and week number in the text
        const links = Array.from(document.querySelectorAll('a[onclick*="v={v_value}"]')).filter(a => {{
            const weekNum = {expected_week_num};
            // Text could be either the number or "Vika <number>"
            const text = a.textContent.trim();
            return text === String(weekNum) || text === `Vika ${{weekNum}}`;
        }});
        
        if (links.length > 0) {{
            links[0].click();
            return true;
        }}
        
        // Fallback to just using the v-value if no match with week number
        const linksWithV = Array.from(document.querySelectorAll('a[onclick*="v={v_value}"]'));
        if (linksWithV.length > 0) {{
            linksWithV[0].click();
            return true;
        }}
        
        return false;
    }}
    """)
    
    if not link_found:
        # Fallback: Navigate directly by URL
        # Extract the id parameter from current URL if possible
        id_match = re.search(r'id=\{([^}]+)\}', current_url)
        id_param = id_match.group(0) if id_match else "id={E79174A3-7D8D-4AA7-A8F7-D8C869E5FF36}"
        
        # Construct and navigate to the URL
        target_url = f"{base_url}#{id_param}&v={v_value}"
        await page.goto(target_url)
    
    # Wait for the page to load with new data
    await page.wait_for_load_state("networkidle")
    
    # Add a longer delay to ensure DOM is updated with new week data
    await asyncio.sleep(5)  # Increased from 2 to 5 seconds
    
    # Wait for the week button to be selected (UgeKnapValgt class)
    try:
        await page.wait_for_selector('.UgeKnapValgt', state="visible", timeout=5000)
    except:
        logger.warning("Warning: Could not find selected week button after navigation")
    
    # Get week info after navigation
    week_info = await get_current_week_info(page)
    loaded_week_num = week_info.get('weekNumber')
    
    # Verify we loaded the expected week
    max_retries = 3
    retry_count = 0
    
    while expected_week_num and loaded_week_num != expected_week_num and retry_count < max_retries:
        logger.info(f"Expected week {expected_week_num} but loaded week {loaded_week_num}. Retrying navigation...")
        retry_count += 1
        
        # Try to directly find and click the button with the expected week number
        direct_click = await page.evaluate(f"""
        () => {{
            const weekNum = {expected_week_num};
            const weekLinks = Array.from(document.querySelectorAll('a')).filter(a => {{
                const text = a.textContent.trim();
                return text === String(weekNum) || text === `Vika ${{weekNum}}`;
            }});
            
            if (weekLinks.length > 0) {{
                weekLinks[0].click();
                return true;
            }}
            return false;
        }}
        """)
        
        if not direct_click:
            # If direct click failed, try clicking the link with v-value again
            link_found = await page.evaluate(f"""
            () => {{
                const links = Array.from(document.querySelectorAll('a[onclick*="v={v_value}"]'));
                if (links.length > 0) {{
                    links[0].click();
                    return true;
                }}
                return false;
            }}
            """)
            
            if not link_found:
                # Last resort: Navigate directly by URL
                target_url = f"{base_url}#{id_param}&v={v_value}"
                await page.goto(target_url)
        
        # Wait for the page to load with new data
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(5)  # Increased delay for retries
        
        # Try to wait for the week button to be selected
        try:
            await page.wait_for_selector('.UgeKnapValgt', state="visible", timeout=5000)
        except:
            logger.warning("Warning: Could not find selected week button after retry")
        
        # Check week info again
        week_info = await get_current_week_info(page)
        loaded_week_num = week_info.get('weekNumber')
    
    if expected_week_num and loaded_week_num != expected_week_num:
        logger.warning(f"Warning: Failed to navigate to week {expected_week_num}, loaded week {loaded_week_num} instead.")
    else:
        logger.info(f"Successfully navigated to week {loaded_week_num}")
    
    return week_info

async def get_current_week_info(page):
    """Extract current week information from the page"""
    week_data = await page.evaluate("""
    () => {
        // Get current week number (from the selected week button)
        const selectedWeekBtn = document.querySelector('.UgeKnapValgt');
        const weekText = selectedWeekBtn ? selectedWeekBtn.textContent.trim() : null;
        
        // Get date range
        const dateRangeElement = Array.from(document.querySelectorAll('*')).find(el => {
            const text = el.textContent.trim();
            return /\\d{1,2}\\.\\d{1,2}\\.\\d{4}\\s*-\\s*\\d{1,2}\\.\\d{1,2}\\.\\d{4}/.test(text);
        });
        
        const dateRange = dateRangeElement ? dateRangeElement.textContent.trim() : null;
        const dateMatch = dateRange ? dateRange.match(/(\\d{1,2})\\.(\\d{1,2})\\.(\\d{4})\\s*-\\s*(\\d{1,2})\\.(\\d{1,2})\\.(\\d{4})/) : null;
        
        // Format dates as YYYY-MM-DD
        let startDate = null;
        let endDate = null;
        let year = new Date().getFullYear();
        
        if (dateMatch) {
            const startDay = dateMatch[1].padStart(2, '0');
            const startMonth = dateMatch[2].padStart(2, '0');
            const startYear = dateMatch[3];
            
            const endDay = dateMatch[4].padStart(2, '0');
            const endMonth = dateMatch[5].padStart(2, '0');
            const endYear = dateMatch[6];
            
            startDate = `${startYear}-${startMonth}-${startDay}`;
            endDate = `${endYear}-${endMonth}-${endDay}`;
            year = parseInt(startYear);
        }
        
        // Extract week number from text
        const weekNumberMatch = weekText ? weekText.match(/\\d+/) : null;
        const weekNumber = weekNumberMatch ? parseInt(weekNumberMatch[0]) : null;
        
        return {
            weekText,
            weekNumber,
            dateRange,
            startDate,
            endDate,
            year
        };
    }
    """)
    
    if not week_data or not week_data.get('weekNumber'):
        # Fallback if week info couldn't be extracted
        now = datetime.now()
        week_num = now.isocalendar()[1]
        start_of_week = now - timedelta(days=now.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        
        return {
            "weekText": f"Week {week_num}",
            "weekNumber": week_num,
            "dateRange": f"{start_of_week.strftime('%d.%m.%Y')} - {end_of_week.strftime('%d.%m.%Y')}",
            "startDate": start_of_week.strftime("%Y-%m-%d"),
            "endDate": end_of_week.strftime("%Y-%m-%d"),
            "year": now.year
        }
    
    return week_data

async def return_to_baseline(page, v_value):
    """
    Navigate directly to the baseline week using its specific v-value.
    This ensures we always return to the same instance of the week even if there are duplicates.
    """
    logger.info(f"Returning to baseline week with v-value: {v_value}")
    
    # First try to click the appropriate link
    clicked = await page.evaluate(f"""
    () => {{
        const links = Array.from(document.querySelectorAll('a[onclick*="v={v_value}"]'));
        if (links.length > 0) {{
            links[0].click();
            return true;
        }}
        return false;
    }}
    """)
    
    if not clicked:
        # Fallback to direct URL navigation
        current_url = page.url
        base_url = current_url.split('#')[0]
        id_match = re.search(r'id=\{([^}]+)\}', current_url)
        id_param = id_match.group(0) if id_match else "id={E79174A3-7D8D-4AA7-A8F7-D8C869E5FF36}"
        target_url = f"{base_url}#{id_param}&v={v_value}"
        
        logger.info(f"Navigating directly to baseline URL: {target_url}")
        await page.goto(target_url)
    
    # Wait for page to load
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(5)
    
    # Verify we loaded the correct week instance
    loaded_v_value = await page.evaluate("""
    () => {
        const selectedWeekBtn = document.querySelector('.UgeKnapValgt');
        if (selectedWeekBtn) {
            const onclick = selectedWeekBtn.getAttribute('onclick') || '';
            const vMatch = onclick.match(/v=(-?\\d+)/);
            return vMatch ? parseInt(vMatch[1]) : null;
        }
        return null;
    }
    """)
    
    if loaded_v_value == v_value:
        logger.info(f"Successfully returned to baseline week with v-value: {v_value}")
    else:
        logger.warning(f"Warning: Expected v-value {v_value} but loaded v-value {loaded_v_value}") 