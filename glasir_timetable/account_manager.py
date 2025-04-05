import os
import json
import shutil

ACCOUNTS_DIR = os.path.join(os.path.dirname(__file__), "accounts")


def ensure_accounts_dir():
    os.makedirs(ACCOUNTS_DIR, exist_ok=True)


def list_accounts():
    ensure_accounts_dir()
    return [
        name for name in os.listdir(ACCOUNTS_DIR)
        if os.path.isdir(os.path.join(ACCOUNTS_DIR, name)) and name != "global"
    ]


def account_exists(username):
    return os.path.isdir(os.path.join(ACCOUNTS_DIR, username))


def create_account(username, credentials):
    account_path = os.path.join(ACCOUNTS_DIR, username)
    os.makedirs(account_path, exist_ok=True)
    save_account_data(username, "credentials", credentials)
    # Empty cookies and student-id initially
    save_account_data(username, "cookies", {})
    save_account_data(username, "student_id", {})


def delete_account(username):
    account_path = os.path.join(ACCOUNTS_DIR, username)
    if os.path.isdir(account_path):
        shutil.rmtree(account_path)


def rename_account(old_username, new_username):
    old_path = os.path.join(ACCOUNTS_DIR, old_username)
    new_path = os.path.join(ACCOUNTS_DIR, new_username)
    if os.path.isdir(old_path):
        os.rename(old_path, new_path)


def get_account_path(username):
    return os.path.join(ACCOUNTS_DIR, username)


def load_account_data(username, data_type):
    """
    data_type: 'credentials', 'cookies', 'student_id'
    """
    filename = {
        "credentials": "credentials.json",
        "cookies": "cookies.json",
        "student_id": "student-id.json"
    }[data_type]
    path = os.path.join(ACCOUNTS_DIR, username, filename)
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def save_account_data(username, data_type, data):
    filename = {
        "credentials": "credentials.json",
        "cookies": "cookies.json",
        "student_id": "student-id.json"
    }[data_type]
    path = os.path.join(ACCOUNTS_DIR, username, filename)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


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