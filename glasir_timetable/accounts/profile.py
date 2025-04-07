import os
import json
from pathlib import Path
from typing import Optional, Dict, Any


class AccountProfile:
    """
    Represents a user account profile, encapsulating paths and data management.
    """

    def __init__(self, username: str, base_dir: Optional[str] = None):
        self.username = username
        self.base_dir = Path(base_dir or os.path.join(os.path.dirname(__file__), username))
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.credentials_path = self.base_dir / "credentials.json"
        self.cookies_path = self.base_dir / "cookies.json"
        self.student_info_path = self.base_dir / "student-id.json"

    def load_credentials(self) -> Optional[Dict[str, Any]]:
        return self._load_json(self.credentials_path)

    def save_credentials(self, credentials: Dict[str, Any]) -> None:
        self._save_json(self.credentials_path, credentials)

    def load_cookies(self) -> Optional[Dict[str, Any]]:
        return self._load_json(self.cookies_path)

    def save_cookies(self, cookies: Dict[str, Any]) -> None:
        self._save_json(self.cookies_path, cookies)

    def load_student_info(self) -> Optional[Dict[str, Any]]:
        return self._load_json(self.student_info_path)

    def save_student_info(self, info: Dict[str, Any]) -> None:
        self._save_json(self.student_info_path, info)

    def delete_profile(self) -> None:
        import shutil
        if self.base_dir.exists() and self.base_dir.is_dir():
            shutil.rmtree(self.base_dir)

    def exists(self) -> bool:
        return self.base_dir.exists() and self.base_dir.is_dir()

    def _load_json(self, path: Path) -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _save_json(self, path: Path, data: Dict[str, Any]) -> None:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save {path}: {e}")

    def __repr__(self):
        return f"<AccountProfile(username={self.username}, base_dir={self.base_dir})>"