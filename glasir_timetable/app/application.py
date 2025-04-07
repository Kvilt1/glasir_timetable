"""
Application state container for Glasir Timetable.

- Defines the Application class.
- Holds runtime state: config, logger, credentials, services, student info, cookies, etc.
- Provides a central object to pass to orchestrator and other components.
"""

class Application:
    def __init__(self, config: dict):
        self.config = config
        self.args = config.get("args")
        self.username = config.get("username")
        self.credentials = config.get("credentials")
        self.api_only_mode = config.get("api_only_mode", False)
        self.cached_student_info = config.get("cached_student_info")
        self.account_path = config.get("account_path")
        self.cookie_path = config.get("cookie_path")
        self.output_dir = config.get("output_dir")
        self.student_id_path = config.get("student_id_path")

        # Placeholder for runtime state
        self.logger = None
        self.services = {}
        self.api_cookies = {}
        self.stats = {}

    def set_logger(self, logger_obj):
        self.logger = logger_obj

    def set_services(self, services_dict):
        self.services = services_dict

    def set_api_cookies(self, cookies_dict):
        self.api_cookies = cookies_dict

    def set_stats(self, stats_dict):
        self.stats = stats_dict