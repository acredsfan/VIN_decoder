import subprocess
import sys
import os


# Check and create virtual environment if it doesn't exist
def setup_virtualenv(venv_name='venv'):
    if not os.path.exists(venv_name):
        subprocess.check_call([sys.executable, '-m', 'venv', venv_name])

    if sys.platform == 'win32':
        activate_script = os.path.join(venv_name, 'Scripts', 'python.exe')
    else:
        activate_script = os.path.join(venv_name, 'bin', 'python')

    return activate_script


# Automatically install missing dependencies
def install_packages(packages, python_exec):
    subprocess.check_call([python_exec, '-m', 'pip', 'install', '--upgrade', 'pip'])
    for package in packages:
        subprocess.check_call([python_exec, "-m", "pip", "install", package])


# Setup virtual environment and get Python executable
python_executable = setup_virtualenv()

# List of required packages
required_packages = ["flask", "requests", "pandas", "werkzeug", "flask_limiter", "openpyxl", "pyngrok", "pandas", "python-dotenv"]
install_packages(required_packages, python_executable)