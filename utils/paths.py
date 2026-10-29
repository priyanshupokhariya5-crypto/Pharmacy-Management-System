"""
Path resolution manager for development and compiled desktop environments.
Handles source-mode, portable executable, and protected-installation paths
with zero filesystem side-effects at import time.
"""
import os
import sys
import uuid
from typing import Optional


def get_project_root() -> str:
    """Returns the source project root directory."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_data_dir() -> str:
    """
    Returns the appropriate directory path for database and log storage.
    Performs pure string calculations; does not create folders at import time.
    """
    # 1. Explicit environment variable override
    env_dir = os.environ.get("PHARMACY_DATA_DIR")
    if env_dir:
        return os.path.abspath(env_dir)

    # 2. Frozen mode (Compiled PyInstaller executable)
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        portable_data_dir = os.path.join(exe_dir, "data")
        portable_db_file = os.path.join(portable_data_dir, "pharmacy.db")

        # Authoritative: If portable database or data directory exists, never switch away
        if os.path.exists(portable_db_file) or os.path.exists(portable_data_dir):
            return portable_data_dir

        # Clean first launch: use portable dir if executable directory is writable
        if _is_writable_location(exe_dir):
            return portable_data_dir

        # Clean first launch in protected folder (e.g. Program Files)
        local_appdata = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        return os.path.join(local_appdata, "PharmacyManagementSystem", "data")

    # 3. Source mode (Development and unit tests)
    return os.path.join(get_project_root(), "data")


def _is_writable_location(path: str) -> bool:
    """
    Checks if a path or its nearest existing parent directory allows file creation.
    Uses a uniquely named probe, explicitly closes it before removal,
    and cleans up safely without leaving persistent files.
    """
    target = os.path.abspath(path)
    while target and not os.path.exists(target):
        parent = os.path.dirname(target)
        if parent == target:
            break
        target = parent

    if not target or not os.path.isdir(target):
        return False

    probe_name = f".perm_probe_{os.getpid()}_{uuid.uuid4().hex}.tmp"
    probe_path = os.path.join(target, probe_name)
    probe_file = None
    try:
        probe_file = open(probe_path, "wb")
        probe_file.write(b"")
        probe_file.close()
        probe_file = None
        return True
    except (OSError, PermissionError):
        return False
    finally:
        if probe_file is not None:
            try:
                probe_file.close()
            except OSError:
                pass
        if os.path.exists(probe_path):
            try:
                os.remove(probe_path)
            except OSError:
                pass


def get_default_db_path() -> str:
    """Returns the default SQLite database path."""
    return os.path.join(get_data_dir(), "pharmacy.db")


def get_default_benchmark_db_path() -> str:
    """Returns the default benchmark SQLite database path."""
    return os.path.join(get_data_dir(), "benchmark.db")


def get_default_log_path() -> str:
    """Returns the default application log file path."""
    return os.path.join(get_data_dir(), "app_quality.log")
