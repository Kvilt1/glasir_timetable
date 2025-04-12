import asyncio
import re
from typing import Optional, Dict, Any
from playwright.async_api import Page, Error as PlaywrightError
from glasir_timetable.shared import logger
from glasir_timetable.storage.profile_manager import ProfileManager

# Compiled regex patterns for performance
_RE_GUID = re.compile(r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}")
_RE_NAME_CLASS = re.compile(r"N[æ&aelig;]mingatímatalva:\s*([^,<]+?)\s*,\s*([^\s<]+)", re.IGNORECASE)
async def _extract_student_info_from_page(page: Page) -> Optional[Dict[str, Any]]:
    """
    Extracts student ID, name, and class from the timetable page content.
    This function ONLY extracts, it does not load/save from/to files.

    Args:
        page: The Playwright page object, assumed to be on the timetable page.

    Returns:
        A dictionary with 'id', 'name', 'class' keys, or None if extraction fails.
        Values might be None if specific parts aren't found.
    """
    logger.debug("Attempting to extract student info from page content...")
    try:
        content = await page.content()
    except Exception as e:
        logger.error(f"Cannot get page content for student info extraction: {e}")
        return None

    student_info = {"id": None, "name": None, "class": None}

    # Extract GUID (Student ID)
    guid_match = _RE_GUID.search(content)
    if guid_match:
        student_info["id"] = guid_match.group(0).strip()
        logger.debug(f"Extracted student ID: {student_info['id']}")
    else:
        logger.warning("Could not extract student ID (GUID) from page content.")
        # If ID extraction fails, the whole process is likely useless, but we continue for name/class just in case
        # Consider returning None here if ID is strictly required.

    # Extract name and class
    # Regex updated slightly to be more robust against variations
    name_class_match = _RE_NAME_CLASS.search(content)
    if name_class_match:
        student_info["name"] = name_class_match.group(1).strip()
        student_info["class"] = name_class_match.group(2).strip()
        logger.debug(f"Extracted student name: {student_info['name']}")
        logger.debug(f"Extracted student class: {student_info['class']}")
    else:
        logger.warning("Could not extract student name and class from page content.")
        # Attempt extraction via JS as a fallback (similar to old student_utils)
        try:
            student_name_js = await page.evaluate(
                "() => document.querySelector('.main-content h1')?.textContent.trim()"
            )
            # Assuming class might be in a paragraph nearby - this is less reliable
            class_name_js = await page.evaluate(
                "() => document.querySelector('.main-content p')?.textContent.match(/Class: ([^,]+)/)?.[1].trim()"
            )
            if student_name_js and not student_info["name"]:
                 student_info["name"] = student_name_js
                 logger.debug(f"Extracted student name via JS: {student_info['name']}")
            if class_name_js and not student_info["class"]:
                 student_info["class"] = class_name_js
                 logger.debug(f"Extracted student class via JS: {student_info['class']}")
        except Exception as e:
            logger.warning(f"Error extracting student name/class via JS fallback: {e}")


    # Return the dictionary if ID was found, otherwise None might be more appropriate
    # depending on requirements. For now, return dict even with missing parts.
    if student_info["id"]:
        logger.info(f"Successfully extracted student info: {student_info}")
        return student_info
    else:
        logger.error("Failed to extract essential student ID. Cannot return student info.")
        return None


async def login(page: Page, username: str, password: str, domain: str = "glasir.fo") -> None:
    """
    Async login to Glasir timetable via Microsoft OAuth + ADFS.

    Args:
        page: Playwright page object
        username: Username without domain
        password: Password
        domain: Email domain (default: glasir.fo)

    Raises:
        Exception if login fails
    """
    email = f"{username}@{domain}"
    try:
        logger.info(f"Navigating to https://tg.glasir.fo for user {email}")
        await page.goto("https://tg.glasir.fo", timeout=30000)

        logger.info("Filling username/email")
        await page.wait_for_selector("#i0116", state="visible", timeout=10000)
        await page.fill("#i0116", email)
        await page.click("#idSIButton9")

        logger.info("Filling password")
        await page.wait_for_selector("#passwordInput", state="visible", timeout=10000)
        await page.fill("#passwordInput", password)

        logger.info("Checking 'Keep me signed in'")
        await page.check("#kmsiInput")

        logger.info("Submitting login form")
        await page.click("#submitButton")

        logger.info("Waiting for redirect to timetable")
        await page.wait_for_url("https://tg.glasir.fo/132n/**", timeout=30000)

        logger.info("Waiting for timetable table to appear")
        await page.wait_for_selector("table.time_8_16", state="visible", timeout=15000)

        logger.info("Login successful")

        # --- Ensure student info is loaded/extracted after successful login ---
        try:
            profile_manager = ProfileManager.get_instance()
            # ensure_student_info needs the extraction logic, which is now in this file
            # We need to make ensure_student_info async or run extraction synchronously
            # Let's make ensure_student_info async for consistency with page operations
            # (Requires modifying ProfileManager again, or calling extract here directly)

            # --- Load the specific profile for the current user and save student info ---
            try:
                # Load the profile corresponding to the username used for login
                user_profile = profile_manager.load_profile(username)
                current_info = user_profile.load_student_info()

                # Check if info is missing or incomplete
                if not current_info or not all(k in current_info and current_info[k] for k in ("id", "name", "class")):
                    logger.info(f"Student info missing/incomplete for {username}. Extracting...")
                    extracted_info = await _extract_student_info_from_page(page)

                    if extracted_info and extracted_info.get("id"):
                        # Merge with existing data if any (prefer extracted non-empty values)
                        merged_info = current_info or {}
                        for key, value in extracted_info.items():
                            if value: # Only update if extracted value is not None/empty
                                merged_info[key] = value
                        # Ensure all keys exist, default to "Unknown" if needed (though ID should exist)
                        merged_info.setdefault("id", extracted_info.get("id"))
                        merged_info.setdefault("name", "Unknown")
                        merged_info.setdefault("class", "Unknown")

                        # Save the updated info using the profile object's method
                        user_profile.save_student_info(merged_info)
                        logger.info(f"Saved extracted/updated student info for {username}")
                    else:
                        logger.warning(f"Failed to extract student info for {username} after login.")
                else:
                    logger.info(f"Student info already present and complete for {username}.")
            except FileNotFoundError:
                 logger.error(f"Profile '{username}' not found after login. Cannot save student info.")
            except Exception as e_info:
                 logger.error(f"Error loading/saving student info for profile '{username}': {e_info}")
            # --- End Student Info Handling ---

        except Exception as e:
            logger.error(f"Error ensuring student info after login: {e}")
            # Continue login process even if student info fails

    except PlaywrightError as e:
        logger.error(f"Playwright error during login: {e}")
        # Consider saving page source/screenshot for debugging
        # await page.screenshot(path="login_error_screenshot.png")
        # html = await page.content()
        # with open("login_error_page.html", "w") as f: f.write(html)
        raise
    except Exception as e:
        logger.error(f"Login failed: {e}")
        raise