#!/usr/bin/env python3
"""
Parser for homework HTML responses from the Glasir timetable API.

This module extracts homework text from the HTML responses returned by the note.asp
API endpoint, mapping each homework item to its corresponding lesson ID.
"""

import re
import logging
from typing import Dict, Optional, List, Any
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class ParsingError(Exception):
    """Exception raised when homework HTML parsing fails."""
    pass

def parse_homework_html_response(html_content: str) -> Dict[str, str]:
    """
    Parses the HTML response from the note.asp API to extract homework.

    Args:
        html_content: The HTML string returned by the API.

    Returns:
        A dictionary mapping lessonId to homework description text.
    """
    if not html_content or len(html_content.strip()) < 10:
        logger.warning("Empty or very short HTML content received for parsing")
        return {}

    homework_map = {}
    
    try:
        # Create BeautifulSoup object for parsing HTML
        soup = BeautifulSoup(html_content, 'lxml')
        
        # Try container-based parsing first (most likely to succeed)
        homework_containers = soup.find_all('div', id=lambda x: x and x.startswith('MyWindow') and x.endswith('Main'))
        
        if homework_containers:
            logger.debug(f"Found {len(homework_containers)} homework containers using container-based parsing")
            
            for container in homework_containers:
                # Extract lesson ID from the container's ID
                container_id = container.get('id', '')
                # Format: MyWindow{LESSON_ID}Main
                lesson_id_match = re.search(r'MyWindow(.*?)Main', container_id)
                
                if not lesson_id_match:
                    continue
                
                lesson_id = lesson_id_match.group(1)
                
                # Find all paragraphs that might contain homework text
                paragraphs = container.find_all(['p', 'div'], class_=lambda x: x != 'faste')
                
                # Concatenate text from all paragraphs
                if paragraphs:
                    homework_text = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
                    if homework_text:
                        homework_map[lesson_id] = homework_text
                        logger.debug(f"Extracted homework for lesson ID: {lesson_id}")
        else:
            # Fallback: Try alternative parsing methods if container-based parsing didn't find anything
            logger.debug("No homework containers found, trying fallback parsing methods")
            
            # Fallback 1: Look for note-content divs
            note_contents = soup.find_all('div', class_='note-content')
            if note_contents:
                logger.debug(f"Found {len(note_contents)} note-content divs")
                
                for note in note_contents:
                    # Look for some identifier that might relate to the lesson ID
                    parent = note.find_parent('div', id=lambda x: x and 'Window' in x)
                    if parent and parent.get('id'):
                        id_match = re.search(r'Window(.*?)(?:Main|Content)', parent.get('id', ''))
                        if id_match:
                            lesson_id = id_match.group(1)
                            homework_text = note.get_text(strip=True)
                            if homework_text:
                                homework_map[lesson_id] = homework_text
            
            # Fallback 2: Look for any divs with IDs containing 'note' and lesson IDs
            if not homework_map:
                note_divs = soup.find_all('div', id=lambda x: x and ('note' in x.lower() or 'lesson' in x.lower()))
                for div in note_divs:
                    div_id = div.get('id', '')
                    # Try to extract anything that looks like a GUID or lesson ID
                    id_match = re.search(r'([A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12})', div_id, re.IGNORECASE)
                    if id_match:
                        lesson_id = id_match.group(1)
                        homework_text = div.get_text(strip=True)
                        if homework_text:
                            homework_map[lesson_id] = homework_text
    
    except Exception as e:
        logger.error(f"Error parsing homework HTML: {str(e)}")
        # Don't raise here - return whatever was successfully parsed
    
    if not homework_map:
        logger.warning("No homework content could be extracted from the HTML response")
    else:
        logger.info(f"Successfully extracted {len(homework_map)} homework items")
    
    return homework_map

def parse_homework_html_response_structured(html_content: str) -> Dict[str, Any]:
    """
    Parses the HTML response from the note.asp API to extract homework with additional structured data.
    This is an extended version of parse_homework_html_response that provides more detailed information.

    Args:
        html_content: The HTML string returned by the API.

    Returns:
        A dictionary containing structured homework data with additional metadata.
    """
    if not html_content or len(html_content.strip()) < 10:
        logger.warning("Empty or very short HTML content received for structured parsing")
        return {"success": False, "homework": {}, "metadata": {"error": "Empty content"}}

    homework_map = {}
    metadata = {
        "timestamp": logging.Formatter.formatTime(logging.Formatter(), logging.LogRecord("", 0, "", 0, "", (), None)),
        "success": True,
        "parsing_method": None,
        "extracted_count": 0
    }
    
    try:
        # Create BeautifulSoup object for parsing HTML
        soup = BeautifulSoup(html_content, 'lxml')
        
        # Try container-based parsing first (most likely to succeed)
        homework_containers = soup.find_all('div', id=lambda x: x and x.startswith('MyWindow') and x.endswith('Main'))
        
        if homework_containers:
            logger.debug(f"Found {len(homework_containers)} homework containers using container-based parsing")
            metadata["parsing_method"] = "container"
            
            for container in homework_containers:
                # Extract lesson ID from the container's ID
                container_id = container.get('id', '')
                # Format: MyWindow{LESSON_ID}Main
                lesson_id_match = re.search(r'MyWindow(.*?)Main', container_id)
                
                if not lesson_id_match:
                    continue
                
                lesson_id = lesson_id_match.group(1)
                
                # Find all paragraphs that might contain homework text
                paragraphs = container.find_all(['p', 'div'], class_=lambda x: x != 'faste')
                
                # Process paragraphs with more structure
                if paragraphs:
                    # Get raw content first
                    raw_text = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
                    
                    # Look for any dates in the homework content
                    date_matches = re.findall(r'(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})', raw_text)
                    dates = date_matches if date_matches else []
                    
                    # Clean and structure the homework
                    cleaned_text = clean_homework_text(raw_text)
                    
                    if cleaned_text:
                        homework_map[lesson_id] = {
                            "content": cleaned_text,
                            "raw_content": raw_text,
                            "has_content": bool(cleaned_text),
                            "dates_mentioned": dates,
                            "length": len(cleaned_text)
                        }
                        metadata["extracted_count"] += 1
                        logger.debug(f"Extracted structured homework for lesson ID: {lesson_id}")
        else:
            # Fallback: Try alternative parsing methods if container-based parsing didn't find anything
            logger.debug("No homework containers found, trying fallback parsing methods")
            
            # Fallback 1: Look for note-content divs
            note_contents = soup.find_all('div', class_='note-content')
            if note_contents:
                logger.debug(f"Found {len(note_contents)} note-content divs")
                metadata["parsing_method"] = "note_content"
                
                for note in note_contents:
                    # Look for some identifier that might relate to the lesson ID
                    parent = note.find_parent('div', id=lambda x: x and 'Window' in x)
                    if parent and parent.get('id'):
                        id_match = re.search(r'Window(.*?)(?:Main|Content)', parent.get('id', ''))
                        if id_match:
                            lesson_id = id_match.group(1)
                            
                            # Get raw content
                            raw_text = note.get_text(strip=True)
                            
                            # Look for any dates in the homework content
                            date_matches = re.findall(r'(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})', raw_text)
                            dates = date_matches if date_matches else []
                            
                            # Clean and structure
                            cleaned_text = clean_homework_text(raw_text)
                            
                            if cleaned_text:
                                homework_map[lesson_id] = {
                                    "content": cleaned_text,
                                    "raw_content": raw_text,
                                    "has_content": bool(cleaned_text),
                                    "dates_mentioned": dates,
                                    "length": len(cleaned_text)
                                }
                                metadata["extracted_count"] += 1
            
            # Fallback 2: Look for any divs with IDs containing 'note' and lesson IDs
            if not homework_map:
                metadata["parsing_method"] = "id_matching"
                note_divs = soup.find_all('div', id=lambda x: x and ('note' in x.lower() or 'lesson' in x.lower()))
                for div in note_divs:
                    div_id = div.get('id', '')
                    # Try to extract anything that looks like a GUID or lesson ID
                    id_match = re.search(r'([A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12})', div_id, re.IGNORECASE)
                    if id_match:
                        lesson_id = id_match.group(1)
                        
                        # Get raw content
                        raw_text = div.get_text(strip=True)
                        
                        # Look for any dates in the homework content
                        date_matches = re.findall(r'(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})', raw_text)
                        dates = date_matches if date_matches else []
                        
                        # Clean and structure
                        cleaned_text = clean_homework_text(raw_text)
                        
                        if cleaned_text:
                            homework_map[lesson_id] = {
                                "content": cleaned_text,
                                "raw_content": raw_text,
                                "has_content": bool(cleaned_text),
                                "dates_mentioned": dates,
                                "length": len(cleaned_text)
                            }
                            metadata["extracted_count"] += 1
    
    except Exception as e:
        logger.error(f"Error parsing homework HTML in structured mode: {str(e)}")
        metadata["success"] = False
        metadata["error"] = str(e)
    
    if not homework_map:
        logger.warning("No homework content could be extracted from the HTML response for structured parsing")
        metadata["success"] = False
        metadata["error"] = "No content extracted"
    else:
        logger.info(f"Successfully extracted {len(homework_map)} structured homework items")
    
    # Return structured response
    return {
        "success": metadata["success"],
        "homework": homework_map,
        "metadata": metadata
    }

def clean_homework_text(text: str) -> str:
    """
    Cleans and formats homework text for consistent output.
    
    Args:
        text: Raw homework text
        
    Returns:
        Cleaned and formatted homework text
    """
    if not text:
        return ""
    
    # Remove 'Heimaarbeiði' prefix that appears at the beginning
    # This handles both cases where it has a space after it or is directly connected to the next word
    cleaned = re.sub(r'^Heimaarbeiði\s*', '', text)
    
    # Remove excessive whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    # Remove any HTML tags that might have survived
    cleaned = re.sub(r'<[^>]+>', '', cleaned)
    
    return cleaned