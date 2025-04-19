import asyncio
from typing import Dict, List, Optional
from cachetools import TTLCache, cached
from glasir_timetable.api.client import AsyncApiClient
from glasir_timetable.parsers.homework_parser import parse_homework_html
from glasir_timetable.parsers.teacher_parser import parse_teacher_html
from glasir_timetable.shared import logger
from glasir_timetable.shared.constants import TEACHER_MAP_CACHE_TTL # HOMEWORK_FETCH_CONCURRENCY no longer needed here
from glasir_timetable.shared.concurrency_manager import ConcurrencyManager

# Module-level cache for teacher map with TTL
teacher_cache = TTLCache(maxsize=1, ttl=TEACHER_MAP_CACHE_TTL)
class TimetableExtractor:
    def __init__(self, api_client: AsyncApiClient):
        self.api = api_client

    @cached(teacher_cache)
    async def fetch_teacher_map(self) -> Dict[str, str]:
        """
        Fetches the teacher map from the Glasir API.
        Uses a TTL cache to avoid redundant requests.
        """
        logger.info("Fetching fresh teacher map from API...")
        try:
            # The actual API call doesn't seem to depend on specific cookies for the teacher list itself,
            # relying on the session managed by the api_client.
            resp = await self.api.post("/i/teachers.asp", data={"fname": "Henry"}, inject_params=True)
            resp.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            return parse_teacher_html(resp.text)
        except Exception as e:
            logger.error(f"Failed to fetch or parse teacher map: {e}")
            # Return empty dict on failure, which will also be cached for the TTL duration
            return {}

    async def fetch_week_html( # Add force_max_concurrency flag
        self,
        week_offset: int = 0,
        student_id: str = None,
        lname_value: str = None,
        timer_value: str = None,
        week_concurrency_manager: Optional[ConcurrencyManager] = None,
        force_max_concurrency: bool = False # New flag
    ) -> str:
        try:
            data = {
                "fname": "Henry",
                "timex": timer_value,
                "lname": lname_value,
                "id": student_id,
                "q": "stude",
                "v": str(week_offset)
            }
            resp = await self.api.post(
                "/i/udvalg.asp",
                data=data,
                inject_params=False, # Don't inject potentially stale session params
                concurrency_manager=week_concurrency_manager,
                force_max_concurrency=force_max_concurrency # Pass flag
            )
            return resp.text
        except Exception:
            logger.error(f"Failed to fetch week {week_offset}")
            return ""

    async def fetch_homework_for_lessons( # Add force_max_concurrency flag
        self,
        lesson_ids: List[str],
        concurrency_manager: ConcurrencyManager, # Renamed for consistency
        force_max_concurrency: bool = False # New flag
    ) -> Dict[str, str]:
        results = {}
        async def fetch_one(lesson_id, force_flag): # Accept flag
            # async with sem: # Removed
            try:
                data = {
                    "fname": "Henry",
                    "q": lesson_id,
                    "MyFunktion": "ReadNotesToLessonWithLessonRID"
                }
                # Pass the manager to the API call
                resp = await self.api.post(
                    "/i/note.asp",
                    data=data,
                    inject_params=True,
                    concurrency_manager=concurrency_manager,
                    force_max_concurrency=force_flag # Pass flag
                )
                parsed = parse_homework_html(resp.text)
                if lesson_id in parsed:
                    results[lesson_id] = parsed[lesson_id]
                # Success/failure reporting is now handled by the API client via the manager
            except Exception as e:
                # Failure reporting is now handled by the API client
                logger.warning(f"Failed to fetch homework for lesson {lesson_id}: {e}")

        await asyncio.gather(*(fetch_one(lid, force_max_concurrency) for lid in lesson_ids)) # Pass flag to fetch_one
        return results
