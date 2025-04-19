import os
from datetime import datetime  # Import datetime
from typing import Any, Dict, Optional

import aiofiles  # Added for async file I/O
import orjson

from glasir_timetable.shared import logger
from glasir_timetable.shared.date_utils import to_iso_date


async def save_json(data: Dict[str, Any], path: str) -> bool:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            # Use orjson for faster serialization, ensuring indentation and newline
            options = orjson.OPT_INDENT_2 | orjson.OPT_APPEND_NEWLINE
            await f.write(orjson.dumps(data, option=options).decode("utf-8"))
        logger.info("Saved JSON successfully")
        return True
    except Exception:
        logger.error("Failed to save JSON")
        return False


async def save_timetable_export(
    timetable_data: Dict[str, Any],
    output_dir: str,
    filename: Optional[str] = None,
    user_id: Optional[str] = None,
) -> str:
    """
    Save timetable data as JSON file in output_dir.
    Returns the file path.
    """
    if not filename:
        week_info = timetable_data.get("weekInfo", {})
        start_date_iso = week_info.get("startDate")  # Expects YYYY-MM-DD

        try:
            if start_date_iso:
                # Parse the start date and get ISO calendar info
                date_obj = datetime.fromisoformat(start_date_iso)
                iso_year, iso_week, _ = date_obj.isocalendar()
                # Use ISO year and week for filename
                filename = f"{iso_year}-W{iso_week:02d}.json"
            else:
                raise ValueError("Start date is missing in weekInfo")
        except (ValueError, TypeError) as e:
            # Fallback if startDate is missing, invalid, or parsing fails
            logger.warning(
                f"Could not determine ISO week/year from startDate '{start_date_iso}' ({e}). Falling back."
            )
            # Try fallback using year/weekNumber from weekInfo if available
            year = week_info.get("year")
            week_num = week_info.get("weekNumber")
            if year and isinstance(week_num, int):
                filename = (
                    f"{year}-W{week_num:02d}.json"  # Use originally parsed year/week
                )
                logger.warning(f"Using originally parsed year/week: {filename}")
            else:
                # Last resort: use old format with dates
                logger.warning("Falling back to old filename format with dates.")
                week_num_str = str(week_num) if week_num is not None else "unknown"
                end_date_str = week_info.get("endDate")
                end_date_iso = to_iso_date(end_date_str) if end_date_str else "unknown"
                start_date_iso_fallback = start_date_iso or "unknown"  # Ensure not None
                end_date_iso_fallback = end_date_iso or "unknown"  # Ensure not None
                filename = f"week_{week_num_str}_{start_date_iso_fallback}_to_{end_date_iso_fallback}.json"
    # The output_dir should already point to the correct user-specific weeks directory.
    # No need to append user_id again here.
    user_dir = output_dir
    os.makedirs(user_dir, exist_ok=True)
    path = os.path.join(user_dir, filename)
    await save_json(timetable_data, path)
    return path
