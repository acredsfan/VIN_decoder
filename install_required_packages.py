import subprocess
import sys
import os


def setup_virtualenv(venv_dir: str | None = None) -> str:
    """Create (if needed) and return the Python executable inside a venv.

    Target environment: Raspberry Pi OS (Bookworm).
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    venv_dir = venv_dir or os.path.join(base_dir, ".venv")

    # Create venv if missing
    if not os.path.isdir(venv_dir):
        subprocess.check_call([sys.executable, "-m", "venv", venv_dir])

    python_exec = os.path.join(venv_dir, "bin", "python")
    if not os.path.isfile(python_exec):
        raise FileNotFoundError(f"Virtualenv python executable not found at: {python_exec}")

    return python_exec

# Automatically install missing dependencies
def install_packages(packages, python_exec):
    subprocess.check_call([python_exec, '-m', 'pip', 'install', '--upgrade', 'pip'])
    for package in packages:
        subprocess.check_call([python_exec, "-m", "pip", "install", package])


# Setup virtual environment and get Python executable
python_executable = setup_virtualenv()

# List of required packages
required_packages = [
    "flask",
    "requests",
    "pandas",
    "werkzeug",
    "Flask-Limiter",
    "openpyxl",
    "python-dotenv",
]
install_packages(required_packages, python_executable)