import json
import os
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHORTCUTS_FILE = os.path.join(BASE_DIR, "shortcuts.json")

DEFAULT_SHORTCUTS = {
    "a": "Hello",
    "d": "Doctor",
    "h": "Help",
}

_lock = threading.Lock()


def _load():
    try:
        with open(SHORTCUTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data):
    with open(SHORTCUTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_user_shortcuts(username):
    with _lock:
        data = _load()
        return data.get(username, dict(DEFAULT_SHORTCUTS))


def update_user_shortcuts(username, shortcuts):
    with _lock:
        data = _load()
        data[username] = shortcuts
        _save(data)
