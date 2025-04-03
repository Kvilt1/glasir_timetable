#!/usr/bin/env python3
"""
Test script for student info extraction.
"""
import os
import sys
import json
import asyncio
import logging
from pathlib import Path

# Add the parent directory to the path so we can import the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from glasir_timetable.student_utils import get_student_id
from glasir_timetable.extractors.timetable import extract_student_info
from glasir_timetable.constants import STUDENT_ID_FILE

# Setup basic logging
logging.basicConfig(level=logging.INFO, 
                   format='[%(asctime)s] %(levelname)s - %(message)s',
                   datefmt='%Y-%m-%d %H:%M:%S')

logger = logging.getLogger("test_student_info")

class MockPage:
    """Mock page object for testing."""
    
    def __init__(self, title_text="", content_html=""):
        self.title_text = title_text
        self.content_html = content_html
    
    async def title(self):
        return self.title_text
    
    async def content(self):
        return self.content_html
    
    async def evaluate(self, script):
        """Mock evaluate to handle different script patterns."""
        if "localStorage.getItem" in script:
            return None
        elif "querySelector" in script:
            return None
        elif "() => {" in script:
            # This is the complex script for finding student info in elements
            if "Næmingatímatalva: Rókur Kvilt Meitilberg, 22y" in self.content_html:
                return {
                    "student_name": "Rókur Kvilt Meitilberg", 
                    "class": "22y"
                }
            return None
        return None

async def test_student_info_extraction():
    """Test the student info extraction functionality."""
    logger.info("Starting student info extraction test")
    
    # Remove the student-id.json file if it exists to test extraction
    if os.path.exists(STUDENT_ID_FILE):
        logger.info(f"Removing existing {STUDENT_ID_FILE} for testing")
        os.remove(STUDENT_ID_FILE)
    
    # Create a mock page with the test data
    mock_page = MockPage(
        title_text="Næmingatímatalva: Rókur Kvilt Meitilberg, 22y", 
        content_html="<td>Næmingatímatalva: Rókur Kvilt Meitilberg, 22y</td>"
    )
    
    # Test the extract_student_info function
    student_info = await extract_student_info(mock_page)
    
    logger.info(f"Extracted student info: {student_info}")
    
    # Verify that the student info was extracted correctly
    assert student_info is not None, "Student info should not be None"
    assert student_info["student_name"] == "Rókur Kvilt Meitilberg", "Student name should match"
    assert student_info["class"] == "22y", "Class should match"
    
    # Test that the student-id.json file was not created (since we couldn't get an ID)
    assert not os.path.exists(STUDENT_ID_FILE), "student-id.json should not exist since we couldn't get an ID"
    
    logger.info("Student info extraction test passed!")

if __name__ == "__main__":
    asyncio.run(test_student_info_extraction()) 