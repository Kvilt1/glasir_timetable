import os
import json
import shutil

# New imports for refactored account management
from glasir_timetable.accounts.manager import AccountManager as _NewAccountManager
from glasir_timetable.accounts.profile import AccountProfile

# Singleton instance of the new AccountManager
_manager = _NewAccountManager(os.path.join(os.path.dirname(__file__), "accounts"))

ACCOUNTS_DIR = os.path.join(os.path.dirname(__file__), "accounts")


def ensure_accounts_dir():
    os.makedirs(ACCOUNTS_DIR, exist_ok=True)


def list_accounts():
    """
    Deprecated: Use AccountManager.list_profiles() instead.
    """
    return _manager.list_profiles()


def account_exists(username):
    """
    Deprecated: Use AccountManager.profile_exists() instead.
    """
    return _manager.profile_exists(username)


def create_account(username, credentials):
    """
    Deprecated: Use AccountManager.create_profile() instead.
    """
    _manager.create_profile(username, credentials)


def delete_account(username):
    """
    Deprecated: Use AccountManager.delete_profile() instead.
    """
    _manager.delete_profile(username)


def rename_account(old_username, new_username):
    """
    Deprecated: Use AccountManager.rename_profile() instead.
    """
    _manager.rename_profile(old_username, new_username)


def get_account_path(username):
    """
    Deprecated: Use AccountProfile.base_dir instead.
    """
    profile = _manager.load_profile(username)
    return str(profile.base_dir)


def load_account_data(username, data_type):
    """
    Deprecated: Use AccountProfile.load_* methods instead.
    """
    profile = _manager.load_profile(username)
    if data_type == "credentials":
        return profile.load_credentials()
    elif data_type == "cookies":
        return profile.load_cookies()
    elif data_type == "student_id":
        return profile.load_student_info()
    else:
        return None


def save_account_data(username, data_type, data):
    """
    Deprecated: Use AccountProfile.save_* methods instead.
    """
    profile = _manager.load_profile(username)
    if data_type == "credentials":
        profile.save_credentials(data)
    elif data_type == "cookies":
        profile.save_cookies(data)
    elif data_type == "student_id":
        profile.save_student_info(data)


def interactive_account_selection():
    ensure_accounts_dir()
    while True:
        accounts = list_accounts()
        print("\nAvailable accounts:")
        for idx, acc in enumerate(accounts):
            print(f"  {idx + 1}. {acc}")
        print("  N. Create new account")
        print("  D. Delete an account")
        print("  R. Rename an account")
        choice = input("Select account number, or N/D/R: ").strip().lower()

        if choice == "n":
            username = input("Enter new username: ").strip()
            if not username:
                print("Invalid username.")
                continue
            if account_exists(username):
                print("Account already exists.")
                continue
            # Prompt for credentials
            uname = input("Username (without @glasir.fo): ").strip()
            import getpass
            pwd = getpass.getpass("Password: ")
            credentials = {"username": uname, "password": pwd}
            create_account(username, credentials)
            print(f"Account '{username}' created.")
            return username

        elif choice == "d":
            del_name = input("Enter username to delete: ").strip()
            if not account_exists(del_name):
                print("Account does not exist.")
                continue
            confirm = input(f"Are you sure you want to delete '{del_name}'? (y/n): ").strip().lower()
            if confirm == "y":
                delete_account(del_name)
                print(f"Account '{del_name}' deleted.")
            continue

        elif choice == "r":
            old_name = input("Enter current username: ").strip()
            if not account_exists(old_name):
                print("Account does not exist.")
                continue
            new_name = input("Enter new username: ").strip()
            if not new_name or account_exists(new_name):
                print("Invalid or existing new username.")
                continue
            rename_account(old_name, new_name)
            print(f"Account '{old_name}' renamed to '{new_name}'.")
            continue

        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(accounts):
                    return accounts[idx]
                else:
                    print("Invalid selection.")
            except ValueError:
                print("Invalid input.")