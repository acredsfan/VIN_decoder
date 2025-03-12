import subprocess
import sys
import os

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