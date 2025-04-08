import os
from pathlib import Path
from typing import Optional, Dict, List

from .profile import AccountProfile


class AccountManager:
    """
    Manages multiple AccountProfile instances, supports switching active profile.
    """

    def __init__(self, accounts_root: Optional[str] = None):
        self.accounts_root = Path(accounts_root or os.path.join(os.path.dirname(__file__)))
        self.accounts_root.mkdir(parents=True, exist_ok=True)

        self._active_profile: Optional[AccountProfile] = None
        self._profiles_cache: Dict[str, AccountProfile] = {}

    def list_profiles(self) -> List[str]:
        return [
            d.name for d in self.accounts_root.iterdir()
            if d.is_dir()
            and not d.name.startswith('.')
            and d.name not in ("global", "__pycache__")
        ]

    def load_profile(self, username: str) -> AccountProfile:
        if username in self._profiles_cache:
            return self._profiles_cache[username]
        profile = AccountProfile(username, base_dir=self.accounts_root / username)
        self._profiles_cache[username] = profile
        return profile

    def create_profile(self, username: str, credentials: Optional[Dict] = None) -> AccountProfile:
        profile = self.load_profile(username)
        profile.base_dir.mkdir(parents=True, exist_ok=True)
        if credentials:
            profile.save_credentials(credentials)
        # Initialize empty cookies and student info
        if not profile.load_cookies():
            profile.save_cookies({})
        if not profile.load_student_info():
            profile.save_student_info({})
        return profile

    def delete_profile(self, username: str) -> None:
        profile = self.load_profile(username)
        profile.delete_profile()
        if username in self._profiles_cache:
            del self._profiles_cache[username]
        if self._active_profile and self._active_profile.username == username:
            self._active_profile = None

    def rename_profile(self, old_username: str, new_username: str) -> None:
        old_path = self.accounts_root / old_username
        new_path = self.accounts_root / new_username
        if not old_path.exists():
            raise FileNotFoundError(f"Profile '{old_username}' does not exist.")
        if new_path.exists():
            raise FileExistsError(f"Profile '{new_username}' already exists.")
        old_path.rename(new_path)
        # Update cache
        if old_username in self._profiles_cache:
            profile = self._profiles_cache.pop(old_username)
            profile.username = new_username
            profile.base_dir = new_path
            self._profiles_cache[new_username] = profile
        # Update active profile if needed
        if self._active_profile and self._active_profile.username == old_username:
            self._active_profile.username = new_username
            self._active_profile.base_dir = new_path

    def set_active_profile(self, username: str) -> AccountProfile:
        profile = self.load_profile(username)
        self._active_profile = profile
        return profile

    def get_active_profile(self) -> Optional[AccountProfile]:
        return self._active_profile

    def clear_active_profile(self) -> None:
        self._active_profile = None

    def profile_exists(self, username: str) -> bool:
        return (self.accounts_root / username).is_dir()

    def get_all_profiles(self) -> Dict[str, AccountProfile]:
        """
        Return a dict of all profiles keyed by username.
        """
        profiles = {}
        for username in self.list_profiles():
            profiles[username] = self.load_profile(username)
        return profiles

    def interactive_account_selection(self) -> str:
        """
        Interactively prompt the user to select an account profile.

        Returns:
            str: The selected username.
        """
        profiles = self.list_profiles()
        if not profiles:
            print("No accounts available.")
            return None

        print("Available accounts:")
        for idx, username in enumerate(profiles, 1):
            print(f"{idx}. {username}")

        while True:
            choice = input("Select an account by number: ").strip()
            if not choice.isdigit():
                print("Invalid input. Please enter a number.")
                continue
            index = int(choice)
            if 1 <= index <= len(profiles):
                return profiles[index - 1]
            else:
                print(f"Please enter a number between 1 and {len(profiles)}.")