"""Application entry point for the DeMark desktop app."""

from __future__ import annotations

import importlib
import logging
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

MIN_SUPPORTED_PYTHON = (3, 8)
MAX_TESTED_PYTHON = (3, 11)
REQUIRED_MODULES = ("customtkinter", "aiohttp", "requests", "selenium", "PIL")
RUNTIME_SWITCH_ENV = "DEMARK_RUNTIME_SWITCHED"


def _python_version_label(version: tuple[int, int] | tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in version)


def _is_supported_python() -> bool:
    current = sys.version_info[:2]
    return MIN_SUPPORTED_PYTHON <= current <= MAX_TESTED_PYTHON


def find_missing_modules() -> list[str]:
    """Return the list of required modules missing from the current interpreter."""
    missing_modules: list[str] = []
    for module_name in REQUIRED_MODULES:
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError:
            missing_modules.append(module_name)
    return missing_modules


def find_compatible_python() -> Path | None:
    """Locate an interpreter that matches the project's tested runtime."""
    candidates: list[Path] = []

    local_virtualenv = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if local_virtualenv.exists():
        candidates.append(local_virtualenv)

    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        python310 = Path(local_appdata) / "Programs" / "Python" / "Python310" / "python.exe"
        if python310.exists():
            candidates.append(python310)

    current_executable = Path(sys.executable).resolve()
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved == current_executable or resolved in seen:
            continue

        seen.add(resolved)
        if _interpreter_is_ready(resolved):
            return resolved

    return None


def _interpreter_is_ready(python_exe: Path) -> bool:
    """Check whether a candidate interpreter has the modules required to start the GUI."""
    probe_command = [
        str(python_exe),
        "-c",
        "import customtkinter, aiohttp, requests, selenium, PIL",
    ]
    result = subprocess.run(
        probe_command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _build_runtime_error(missing_modules: list[str]) -> str:
    current_version = _python_version_label(sys.version_info[:3])
    message_lines = ["Unable to start DeMark."]

    if not _is_supported_python():
        supported_range = (
            f"{_python_version_label(MIN_SUPPORTED_PYTHON)}-"
            f"{_python_version_label(MAX_TESTED_PYTHON)}"
        )
        message_lines.append(
            f"- Current Python is {current_version}. This project is tested on {supported_range}."
        )

    if missing_modules:
        message_lines.append(
            "- Missing modules in the current interpreter: "
            + ", ".join(missing_modules)
        )

    message_lines.append("- Recommended fixes:")

    compatible_python = None
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        python310 = Path(local_appdata) / "Programs" / "Python" / "Python310" / "python.exe"
        if python310.exists():
            compatible_python = python310

    if compatible_python:
        message_lines.append(f'  1. "{compatible_python}" -m pip install -r requirements.txt')
        message_lines.append(f'  2. "{compatible_python}" main.py')
        message_lines.append("  3. Or run .\\run_app.bat")
    else:
        message_lines.append("  1. python -m pip install -r requirements.txt")
        message_lines.append("  2. python main.py")

    return "\n".join(message_lines)


def ensure_runtime_ready() -> None:
    """Restart with a compatible interpreter when the current one is unsuitable."""
    missing_modules = find_missing_modules()
    if _is_supported_python() and not missing_modules:
        return

    if os.environ.get(RUNTIME_SWITCH_ENV) != "1":
        compatible_python = find_compatible_python()
        if compatible_python is not None:
            print(
                f"DeMark is restarting with a compatible Python runtime: {compatible_python}",
                file=sys.stderr,
            )
            child_env = os.environ.copy()
            child_env[RUNTIME_SWITCH_ENV] = "1"
            result = subprocess.run(
                [str(compatible_python), str(PROJECT_ROOT / "main.py"), *sys.argv[1:]],
                env=child_env,
                check=False,
            )
            raise SystemExit(result.returncode)

    raise RuntimeError(_build_runtime_error(missing_modules))


def setup_logging(settings) -> None:
    """Configure application logging."""
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL),
        format=settings.LOG_FORMAT,
        handlers=[
            logging.FileHandler(settings.LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def create_directories(settings) -> None:
    """Create the directories used by the application at runtime."""
    for directory in (settings.DOWNLOAD_PATH, "logs", "cache"):
        Path(directory).mkdir(parents=True, exist_ok=True)


def main() -> None:
    """Launch the desktop application."""
    try:
        ensure_runtime_ready()

        if "--startup-check" in sys.argv:
            print(f"runtime-ok:{sys.executable}")
            return

        from config.settings import Settings
        from gui.main_window import MainWindow

        setup_logging(Settings)
        create_directories(Settings)

        logging.info("Starting DeMark desktop application")

        app = MainWindow()
        app.run()

    except SystemExit:
        raise
    except Exception as exc:
        logging.error("Application startup failed: %s", exc)
        print(f"Application startup failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
