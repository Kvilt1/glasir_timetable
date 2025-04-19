from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles  # Added for async file I/O
import orjson

from ..shared.constants import DEFAULT_HOMEWORK_FETCH_CONCURRENCY  # Corrected name
from ..shared.constants import DEFAULT_WEEK_FETCH_CONCURRENCY  # Corrected name
from ..shared.constants import (
    DEFAULT_WEEK_PROCESS_CONCURRENCY,
)  # Added default for processing
from ..shared.constants import CONCURRENCY_CONFIG_FILENAME

# Assuming AccountProfile will be moved here or its definition adjusted
# For now, let's define a minimal structure or import from the old location
# We will remove the old accounts directory later.
# Let's define the structure needed directly for now.


class ProfileData:
    """Represents the data structure and paths for a single profile."""

    def __init__(self, username: str, base_dir: Path):
        self.username = username
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.credentials_path = self.base_dir / "credentials.json"
        self.cookies_path = self.base_dir / "cookies.json"
        self.student_info_path = self.base_dir / "student-id.json"
        self.weeks_dir = (
            self.base_dir / "weeks"
        )  # Assuming timetable data is stored here
        self.concurrency_config_path = self.base_dir / CONCURRENCY_CONFIG_FILENAME

    async def _load_json(self, path: Path) -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None
        try:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                # Read the whole file content and parse with orjson
                content = await f.read()
                return orjson.loads(content)
        except (orjson.JSONDecodeError, IOError) as e:
            # TODO: Replace with proper logging
            print(f"Error loading JSON from {path}: {e}")
            return None

    async def _save_json(self, path: Path, data: Dict[str, Any]) -> None:
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)  # Ensure dir exists
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                # Use orjson for faster serialization with indentation and newline
                options = orjson.OPT_INDENT_2 | orjson.OPT_APPEND_NEWLINE
                await f.write(orjson.dumps(data, option=options).decode("utf-8"))
        except IOError as e:
            # TODO: Replace with proper logging
            print(f"Error saving JSON to {path}: {e}")

    async def load_credentials(self) -> Optional[Dict[str, Any]]:
        return await self._load_json(self.credentials_path)

    async def save_credentials(self, credentials: Dict[str, Any]) -> None:
        await self._save_json(self.credentials_path, credentials)

    async def load_cookies(self) -> Optional[Dict[str, Any]]:
        return await self._load_json(self.cookies_path)

    async def save_cookies(self, cookies: Dict[str, Any]) -> None:
        await self._save_json(self.cookies_path, cookies)

    async def load_student_info(self) -> Optional[Dict[str, Any]]:
        return await self._load_json(self.student_info_path)

    async def save_student_info(self, info: Dict[str, Any]) -> None:
        await self._save_json(self.student_info_path, info)

    async def load_concurrency_config(self) -> Dict[str, int]:
        """
        Loads concurrency limits from the profile's config file.

        Returns:
            A dictionary with 'week_fetch_limit', 'homework_fetch_limit', and 'week_process_limit'.
            Returns default values if the file doesn't exist or is invalid.
        """
        config_data = await self._load_json(self.concurrency_config_path)
        if config_data is None:
            # Return defaults if file not found or error during load
            return {
                "week_fetch_limit": DEFAULT_WEEK_FETCH_CONCURRENCY,  # Corrected name
                "homework_fetch_limit": DEFAULT_HOMEWORK_FETCH_CONCURRENCY,  # Corrected name
                "week_process_limit": DEFAULT_WEEK_PROCESS_CONCURRENCY,  # Added default
            }
        # Validate or provide defaults for missing keys? For now, assume structure or defaults.
        # Let's ensure the keys exist, falling back to defaults if necessary.
        return {
            "week_fetch_limit": config_data.get(
                "week_fetch_limit", DEFAULT_WEEK_FETCH_CONCURRENCY
            ),  # Corrected name
            "homework_fetch_limit": config_data.get(
                "homework_fetch_limit", DEFAULT_HOMEWORK_FETCH_CONCURRENCY
            ),  # Corrected name
            "week_process_limit": config_data.get(
                "week_process_limit", DEFAULT_WEEK_PROCESS_CONCURRENCY
            ),  # Added loading with default
        }

    async def save_concurrency_config(self, config_data: Dict[str, int]) -> None:
        """Saves the concurrency limits (fetch and process) to the profile's config file."""
        await self._save_json(self.concurrency_config_path, config_data)

    def __repr__(self):
        return f"<ProfileData(username={self.username}, base_dir={self.base_dir})>"


class ProfileManager:
    """
    Manages user profile storage and retrieval.
    Handles creation, deletion, listing, and loading of profiles.
    """

    _instance: Optional["ProfileManager"] = None

    def __init__(self, accounts_root: Optional[str | Path] = None):
        """
        Initializes the ProfileManager.

        Args:
            accounts_root: The root directory where profiles are stored.
                           Defaults to 'glasir_timetable/accounts'.
        """
        if accounts_root:
            self.accounts_root = Path(accounts_root)
        else:
            # Determine default path relative to project structure if needed
            # Assuming a standard project layout where this file is in storage/
            project_root = Path(__file__).parent.parent.parent
            self.accounts_root = project_root / "glasir_timetable" / "accounts"
            # Fallback if structure is different (less robust)

        self.accounts_root.mkdir(parents=True, exist_ok=True)
        self._profiles_cache: Dict[str, ProfileData] = {}  # Cache loaded profiles

    @classmethod
    def get_instance(
        cls, accounts_root: Optional[str | Path] = None
    ) -> "ProfileManager":
        """Gets the singleton instance, initializing if necessary."""
        if cls._instance is None:
            cls._instance = ProfileManager(accounts_root=accounts_root)
        elif accounts_root is not None and cls._instance.accounts_root != Path(
            accounts_root
        ):
            # If called again with a different root, re-initialize (or raise error)
            # This handles cases like testing where a different root might be needed
            # TODO: Consider if this re-initialization is the desired behavior for a singleton
            print(
                f"Warning: Re-initializing ProfileManager singleton with new root: {accounts_root}"
            )
            cls._instance = ProfileManager(accounts_root=accounts_root)
        return cls._instance

    def list_profiles(self) -> List[str]:
        """Lists the usernames of all available profiles."""
        return [
            d.name
            for d in self.accounts_root.iterdir()
            if d.is_dir()
            and not d.name.startswith(".")
            and d.name
            not in ("global", "__pycache__")  # Exclude common non-profile dirs
        ]

    def profile_exists(self, username: str) -> bool:
        """Checks if a profile directory exists for the given username."""
        return (self.accounts_root / username).is_dir()

    def load_profile(self, username: str) -> ProfileData:
        """
        Loads profile data for a given username.

        Uses a cache to avoid redundant disk lookups.

        Args:
            username: The username of the profile to load.

        Returns:
            A ProfileData instance for the user.

        Raises:
            FileNotFoundError: If the profile directory doesn't exist.
        """
        if not self.profile_exists(username):
            raise FileNotFoundError(
                f"Profile directory not found for username: {username}"
            )

        if username in self._profiles_cache:
            return self._profiles_cache[username]

        profile_dir = self.accounts_root / username
        profile = ProfileData(username, base_dir=profile_dir)
        self._profiles_cache[username] = profile
        return profile

    async def create_profile(
        self, username: str, credentials: Optional[Dict] = None
    ) -> ProfileData:
        """
        Creates a new profile directory and initializes basic files.

        If the profile already exists, it loads the existing one.
        Optionally saves initial credentials.

        Args:
            username: The username for the new profile.
            credentials: Optional dictionary of credentials to save initially.

        Returns:
            The created or loaded ProfileData instance.
        """
        profile_dir = self.accounts_root / username
        profile_dir.mkdir(parents=True, exist_ok=True)  # Ensure directory exists

        # Use load_profile to potentially get from cache or create ProfileData instance
        # Need to handle case where load_profile raises FileNotFoundError if dir *just* created
        # Let's adjust logic slightly: create ProfileData directly if not in cache
        if username in self._profiles_cache:
            profile = self._profiles_cache[username]
        else:
            profile = ProfileData(username, base_dir=profile_dir)
            self._profiles_cache[username] = profile

        # Save credentials if provided
        if credentials:
            await profile.save_credentials(credentials)

        # Initialize student info if missing (create empty file)
        if not profile.student_info_path.exists():
            await profile.save_student_info({})  # Save empty dict

        # Ensure weeks directory exists
        profile.weeks_dir.mkdir(exist_ok=True)

        return profile
