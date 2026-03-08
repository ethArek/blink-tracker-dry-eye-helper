import os
import sys
import tempfile

from blink_app.metadata import APP_POSIX_DATA_DIR, APP_WINDOWS_DATA_DIR


def ensure_writable_directory(path: str) -> str:
    absolute_path = os.path.abspath(path)
    os.makedirs(absolute_path, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=absolute_path, delete=True):
        pass

    return absolute_path


def default_output_dir() -> str:
    if os.name == "nt":
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            return os.path.join(local_app_data, APP_WINDOWS_DATA_DIR)

    if sys.platform == "darwin":
        return os.path.join(
            os.path.expanduser("~"),
            "Library",
            "Application Support",
            APP_WINDOWS_DATA_DIR,
        )

    xdg_data_home = os.getenv("XDG_DATA_HOME")
    if xdg_data_home:
        return os.path.join(xdg_data_home, APP_POSIX_DATA_DIR)

    return os.path.join(os.path.expanduser("~"), ".local", "share", APP_POSIX_DATA_DIR)


def resolve_runtime_output_dir(path: str, allow_fallback: bool) -> tuple[str, str | None]:
    try:
        resolved_path = ensure_writable_directory(path)

        return resolved_path, None
    except OSError as exc:
        if not allow_fallback:
            raise

        fallback_path = default_output_dir()
        if os.path.abspath(path) == os.path.abspath(fallback_path):
            raise

        resolved_fallback = ensure_writable_directory(fallback_path)
        warning_message = (
            f"Output directory '{path}' is not writable ({exc}). "
            f"Using '{resolved_fallback}' instead."
        )

        return resolved_fallback, warning_message
