"""
Application state container for Glasir Timetable.

- Defines the Application class.
- Holds runtime state: config, logger, credentials, services, student info, cookies, etc.
- Provides a central object to pass to orchestrator and other components.
"""


class Application:  # noqa: F841 # Used in main.py to hold application state
    def __init__(self, config: dict):
        self.config = config
        self.args = config.get("args")
        self.username = config.get("username")
        self.credentials = config.get("credentials")
        self.api_only_mode = config.get("api_only_mode", False)
        self.cached_student_info = config.get("cached_student_info")
        self.output_dir = config.get("output_dir")
        self.profile = config.get("profile")  # Add profile attribute from config
        self.concurrency_config = config.get(
            "concurrency_config"
        )  # Add concurrency config attribute
        self.force_max_concurrency = (
            self.args.force_max_concurrency if self.args else False
        )  # Read from args
        # Placeholder for runtime state
        self.logger = None
        self.api_cookies = {}

    def set_api_cookies(self, cookies_dict):
        self.api_cookies = cookies_dict
