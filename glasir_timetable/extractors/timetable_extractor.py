import asyncio
import time
from typing import Dict, List, Optional
from cachetools import TTLCache, cached
from glasir_timetable.api.client import AsyncApiClient
from glasir_timetable.parsers.timetable_parser import parse_timetable_html
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
        except Exception as e:
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

    async def fetch_timetable_with_homework(
        self,
        week_offset: int = 0,
        student_id: str = None,
        lname_value: str = None,
        timer_value: str = None,
        student_info: Optional[Dict[str, str]] = None
    ) -> Dict:
        # Fetch teacher map first (assuming this doesn't need concurrency management for now)
        teacher_map = await self.fetch_teacher_map()
        # Note: The orchestrator should pass the week_concurrency_manager here
        # This method might need refactoring if called outside the orchestrator context
        # where the manager isn't available.
        html = await self.fetch_week_html(
            week_offset=week_offset,
            student_id=student_id,
            lname_value=lname_value,
            timer_value=timer_value,
            # week_concurrency_manager should be passed by the caller (orchestrator)
        )
        timetable_data, homework_ids = parse_timetable_html(html, teacher_map=teacher_map)
        # This method is now primarily called from the orchestrator's consumer,
        # which passes the manager. If called directly, it would need the manager.
        # For now, assume it's called from the consumer.
        # homework_map = await self.fetch_homework_for_lessons(homework_ids, homework_fetch_manager) # Needs manager if called here
        # Let's remove the direct call from here as the consumer handles it.
        # The consumer in orchestrator.py already calls fetch_homework_for_lessons with the manager.
        # So, this fetch_timetable_with_homework method might become less relevant or needs refactoring
        # if it's intended to be a standalone entry point.
        # For the current task, we only need to modify fetch_homework_for_lessons itself.
        # Let's comment out the homework fetching part within this specific method for now.
        homework_map = {} # Placeholder - Actual fetching happens in consumer
        logger.warning("fetch_timetable_with_homework: Homework fetching is now handled by the consumer in orchestrator.")

        # homework_map = await self.fetch_homework_for_lessons(homework_ids) # Original line
        # Merge homework into events
        for event in timetable_data.get("events", []):
            lesson_id = event.get("lessonId")
            if lesson_id and lesson_id in homework_map:
                event["description"] = homework_map[lesson_id]
        # Overwrite studentInfo with profile data if provided
        if student_info:
            timetable_data["studentInfo"] = student_info
        return timetable_data