import os
import orjson
import shutil
import aiofiles # Added for async file I/O
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple

from ..shared.constants import (
    CONCURRENCY_CONFIG_FILENAME,
    DEFAULT_WEEK_FETCH_CONCURRENCY, # Corrected name
    DEFAULT_HOMEWORK_FETCH_CONCURRENCY, # Corrected name
    DEFAULT_WEEK_PROCESS_CONCURRENCY, # Added default for processing
)

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
        self.weeks_dir = self.base_dir / "weeks"  # Assuming timetable data is stored here
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
            self.base_dir.mkdir(parents=True, exist_ok=True) # Ensure dir exists
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                # Use orjson for faster serialization with indentation and newline
                options = orjson.OPT_INDENT_2 | orjson.OPT_APPEND_NEWLINE
                await f.write(orjson.dumps(data, option=options).decode('utf-8'))
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
                "week_fetch_limit": DEFAULT_WEEK_FETCH_CONCURRENCY, # Corrected name
                "homework_fetch_limit": DEFAULT_HOMEWORK_FETCH_CONCURRENCY, # Corrected name
                "week_process_limit": DEFAULT_WEEK_PROCESS_CONCURRENCY, # Added default
            }
        # Validate or provide defaults for missing keys? For now, assume structure or defaults.
        # Let's ensure the keys exist, falling back to defaults if necessary.
        return {
            "week_fetch_limit": config_data.get("week_fetch_limit", DEFAULT_WEEK_FETCH_CONCURRENCY), # Corrected name
            "homework_fetch_limit": config_data.get("homework_fetch_limit", DEFAULT_HOMEWORK_FETCH_CONCURRENCY), # Corrected name
            "week_process_limit": config_data.get("week_process_limit", DEFAULT_WEEK_PROCESS_CONCURRENCY), # Added loading with default
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
    _instance: Optional['ProfileManager'] = None

    # Default location relative to this file's directory parent
    DEFAULT_ACCOUNTS_ROOT = Path(__file__).parent.parent / "accounts"

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
            # self.accounts_root = self.DEFAULT_ACCOUNTS_ROOT

        self.accounts_root.mkdir(parents=True, exist_ok=True)
        self._profiles_cache: Dict[str, ProfileData] = {} # Cache loaded profiles

    @classmethod
    def get_instance(cls, accounts_root: Optional[str | Path] = None) -> 'ProfileManager':
        """Gets the singleton instance, initializing if necessary."""
        if cls._instance is None:
            cls._instance = ProfileManager(accounts_root=accounts_root)
        elif accounts_root is not None and cls._instance.accounts_root != Path(accounts_root):
            # If called again with a different root, re-initialize (or raise error)
            # This handles cases like testing where a different root might be needed
            # TODO: Consider if this re-initialization is the desired behavior for a singleton
            print(f"Warning: Re-initializing ProfileManager singleton with new root: {accounts_root}")
            cls._instance = ProfileManager(accounts_root=accounts_root)
        return cls._instance

    def list_profiles(self) -> List[str]:
        """Lists the usernames of all available profiles."""
        return [
            d.name for d in self.accounts_root.iterdir()
            if d.is_dir()
            and not d.name.startswith('.')
            and d.name not in ("global", "__pycache__") # Exclude common non-profile dirs
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
             raise FileNotFoundError(f"Profile directory not found for username: {username}")

        if username in self._profiles_cache:
            return self._profiles_cache[username]

        profile_dir = self.accounts_root / username
        profile = ProfileData(username, base_dir=profile_dir)
        self._profiles_cache[username] = profile
        return profile

    async def create_profile(self, username: str, credentials: Optional[Dict] = None) -> ProfileData:
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
        profile_dir.mkdir(parents=True, exist_ok=True) # Ensure directory exists

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
            await profile.save_student_info({}) # Save empty dict

        # Ensure weeks directory exists
        profile.weeks_dir.mkdir(exist_ok=True)

        return profile

    def delete_profile(self, username: str) -> None:
        """
        Deletes the entire profile directory and removes it from the cache.

        Args:
            username: The username of the profile to delete.

        Raises:
            FileNotFoundError: If the profile directory doesn't exist.
        """
        profile_dir = self.accounts_root / username
        if not profile_dir.is_dir():
            raise FileNotFoundError(f"Profile '{username}' does not exist.")

        try:
            shutil.rmtree(profile_dir)
            # TODO: Replace with proper logging
            print(f"Deleted profile directory: {profile_dir}")
        except OSError as e:
            # TODO: Replace with proper logging
            print(f"Error deleting profile directory {profile_dir}: {e}")
            # Decide if we should re-raise or just log

        # Remove from cache if present
        if username in self._profiles_cache:
            del self._profiles_cache[username]

    def rename_profile(self, old_username: str, new_username: str) -> None:
        """
        Renames a profile's directory and updates the cache.

        Args:
            old_username: The current username of the profile.
            new_username: The desired new username.

        Raises:
            FileNotFoundError: If the old profile doesn't exist.
            FileExistsError: If the new profile name already exists.
        """
        old_path = self.accounts_root / old_username
        new_path = self.accounts_root / new_username

        if not old_path.is_dir():
            raise FileNotFoundError(f"Profile '{old_username}' does not exist.")
        if new_path.exists():
            # Check if it's a directory; could be a file conflict too
            if new_path.is_dir():
                 raise FileExistsError(f"Profile '{new_username}' already exists.")
            else:
                 raise FileExistsError(f"A file named '{new_username}' already exists at the target location.")

        try:
            old_path.rename(new_path)
            # TODO: Replace with proper logging
            print(f"Renamed profile directory from {old_path} to {new_path}")
        except OSError as e:
            # TODO: Replace with proper logging
            print(f"Error renaming profile directory {old_path} to {new_path}: {e}")
            raise # Re-raise the OS error after logging

        # Update cache if the old profile was loaded
        if old_username in self._profiles_cache:
            profile = self._profiles_cache.pop(old_username)
            profile.username = new_username
            profile.base_dir = new_path
            # Update paths within the profile object
            profile.credentials_path = profile.base_dir / "credentials.json"
            profile.cookies_path = profile.base_dir / "cookies.json"
            profile.student_info_path = profile.base_dir / "student-id.json"
            profile.weeks_dir = profile.base_dir / "weeks"
            profile.concurrency_config_path = profile.base_dir / CONCURRENCY_CONFIG_FILENAME
            self._profiles_cache[new_username] = profile

    def get_all_profiles(self) -> Dict[str, ProfileData]:
        """
        Loads and returns all profiles found in the accounts directory.

        Returns:
            A dictionary mapping usernames to their ProfileData instances.
        """
        profiles = {}
        for username in self.list_profiles():
            try:
                profiles[username] = self.load_profile(username)
            except FileNotFoundError:
                 # Should not happen if list_profiles is accurate, but handle defensively
                 # TODO: Replace with proper logging
                 print(f"Warning: Profile '{username}' listed but not found during loading.")
        return profiles

    def get_profile_base_dir(self, username: str) -> Path:
        """Returns the base directory path for a given profile username."""
        return self.accounts_root / username

    def clear_cache(self) -> None:
        """Clears the internal profile cache."""
        self._profiles_cache = {}