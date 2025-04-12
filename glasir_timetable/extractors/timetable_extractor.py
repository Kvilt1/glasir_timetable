import asyncio
from typing import Dict, List, Optional
from glasir_timetable.api.client import AsyncApiClient
from glasir_timetable.parsers.timetable_parser import parse_timetable_html
from glasir_timetable.parsers.homework_parser import parse_homework_html
from glasir_timetable.parsers.teacher_parser import parse_teacher_html
from glasir_timetable.shared import logger

class TimetableExtractor:
    def __init__(self, api_client: AsyncApiClient):
        self.api = api_client

    async def fetch_teacher_map(self, cookies: Dict[str, str]) -> Dict[str, str]:
        try:
            resp = await self.api.post("/i/teachers.asp", data={"fname": "Henry"}, inject_params=True)
            return parse_teacher_html(resp.text)
        except Exception as e:
            logger.error("Failed to fetch teacher map")
            return {}

    async def fetch_week_html(
        self,
        week_offset: int = 0,
        student_id: str = None,
        lname_value: str = None,
        timer_value: str = None
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
            resp = await self.api.post("/i/udvalg.asp", data=data, inject_params=False) # Don't inject potentially stale session params
            return resp.text
        except Exception as e:
            logger.error(f"Failed to fetch week {week_offset}")
            return ""

    async def fetch_homework_for_lessons(self, lesson_ids: List[str]) -> Dict[str, str]:
        results = {}
        sem = asyncio.Semaphore(10)
        async def fetch_one(lesson_id):
            async with sem:
                try:
                    data = {
                        "fname": "Henry",
                        "q": lesson_id,
                        "MyFunktion": "ReadNotesToLessonWithLessonRID"
                    }
                    resp = await self.api.post("/i/note.asp", data=data, inject_params=True)
                    parsed = parse_homework_html(resp.text)
                    if lesson_id in parsed:
                        results[lesson_id] = parsed[lesson_id]
                except Exception as e:
                    logger.warning(f"Failed to fetch homework for lesson")

        await asyncio.gather(*(fetch_one(lid) for lid in lesson_ids))
        return results

    async def fetch_timetable_with_homework(
        self,
        week_offset: int = 0,
        student_id: str = None,
        lname_value: str = None,
        timer_value: str = None,
        student_info: Optional[Dict[str, str]] = None
    ) -> Dict:
        # Fetch teacher map first
        teacher_map = await self.fetch_teacher_map({})
        html = await self.fetch_week_html(
            week_offset=week_offset,
            student_id=student_id,
            lname_value=lname_value,
            timer_value=timer_value
        )
        timetable_data, homework_ids = parse_timetable_html(html, teacher_map=teacher_map)
        homework_map = await self.fetch_homework_for_lessons(homework_ids)
        # Merge homework into events
        for event in timetable_data.get("events", []):
            lesson_id = event.get("lessonId")
            if lesson_id and lesson_id in homework_map:
                event["description"] = homework_map[lesson_id]
        # Overwrite studentInfo with profile data if provided
        if student_info:
            timetable_data["studentInfo"] = student_info
        return timetable_data