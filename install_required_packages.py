import subprocess
import sys
import os
from typing import Iterable, Optional


MINIMUM_PYTHON = (3, 8)
REQUIRED_PACKAGES = [
    "flask",
    "requests",
    "pandas",
    "werkzeug",
    "Flask-Limiter",
    "openpyxl",
    "python-dotenv",
]


def ensure_supported_python() -> None:
    if sys.version_info < MINIMUM_PYTHON:
        version = ".".join(str(part) for part in MINIMUM_PYTHON)
        raise SystemExit(f"Python {version}+ is required. Current version: {sys.version.split()[0]}")


def find_virtualenv_python(venv_dir: str) -> str:
    candidates = [
        os.path.join(venv_dir, "Scripts", "python.exe"),
        os.path.join(venv_dir, "Scripts", "python"),
        os.path.join(venv_dir, "bin", "python3"),
        os.path.join(venv_dir, "bin", "python"),
    ]

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    raise FileNotFoundError(
        f"Virtualenv python executable not found in: {venv_dir}. Checked: {', '.join(candidates)}"
    )


def setup_virtualenv(venv_dir: Optional[str] = None) -> str:
    """Create (if needed) and return the Python executable inside a venv.

    Target environment: Raspberry Pi OS (Bookworm).
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    venv_dir = venv_dir or os.path.join(base_dir, ".venv")

    # Create venv if missing
    if not os.path.isdir(venv_dir):
        subprocess.check_call([sys.executable, "-m", "venv", venv_dir])

    return find_virtualenv_python(venv_dir)


def install_packages(packages: Iterable[str], python_exec: str) -> None:
    """Install required runtime packages into the chosen virtual environment."""
    subprocess.check_call([python_exec, '-m', 'pip', 'install', '--upgrade', 'pip'])
    for package in packages:
        subprocess.check_call([python_exec, "-m", "pip", "install", package])


def main() -> None:
    ensure_supported_python()
    python_executable = setup_virtualenv()
    install_packages(REQUIRED_PACKAGES, python_executable)


if __name__ == '__main__':
    main()