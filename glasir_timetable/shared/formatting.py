#!/usr/bin/env python3
"""
Utility functions for formatting and date handling.
"""
from functools import lru_cache


@lru_cache()
def format_academic_year(year_code):
    """
    Parse year code like '2425' into '2024-2025'
    """
    if len(year_code) == 4:
        return f"20{year_code[:2]}-20{year_code[2:]}"
    return year_code  # Return as is if format is unexpected


def parse_time_range(time_range_str):
    """Stub for parse_time_range. Accepts a string and returns it as a tuple (start, end)."""
    # TODO: Implement actual parsing logic if needed
    return time_range_str, time_range_str
