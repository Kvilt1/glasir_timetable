#!/usr/bin/env python3
"""
Entry point for running the package as a module.
"""
import asyncio
from glasir_timetable.main import main

if __name__ == "__main__":
    asyncio.run(main()) 