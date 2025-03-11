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
required_packages = ["flask", "requests", "pandas", "werkzeug", "flask_limiter", "openpyxl", "pyngrok"]
install_packages(required_packages, python_executable)

from flask import Flask, request, render_template, send_file, redirect, url_for, session
import requests
import pandas as pd
from werkzeug.utils import secure_filename
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import uuid
from pyngrok import ngrok
from flask import Flask

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls', 'csv'}
app.secret_key = os.urandom(24)

# Rate Limiter to prevent abuse
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["60 per minute"]
)

# Ensure upload folder exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

NHTSA_API_BASE = 'https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/'


# Helper functions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def get_vin_data(vin):
    response = requests.get(f"{NHTSA_API_BASE}{vin}?format=json")
    if response.status_code == 200:
        results = response.json().get('Results', [])
        vin_data = {
            "Make": next((item['Value'] for item in results if item['Variable'] == 'Make'), "Not Found"),
            "Model": next((item['Value'] for item in results if item['Variable'] == 'Model'), "Not Found"),
            "Model Year": next((item['Value'] for item in results if item['Variable'] == 'Model Year'), "Not Found"),
            "Body Type": next((item['Value'] for item in results if item['Variable'] == 'Body Class'), "Not Found"),
            "Curb Weight": next((item['Value'] for item in results if item['Variable'] == 'Curb Weight (pounds)'), "Not Found"),
            "Vehicle Class": next((item['Value'] for item in results if item['Variable'] == 'Gross Vehicle Weight Rating From'), "Not Found"),
            "Fuel Type": next((item['Value'] for item in results if item['Variable'] == 'Fuel Type - Primary'), "Not Found"),
        }
        return vin_data
    else:
        return {
            "Make": "Invalid VIN",
            "Model": "Invalid VIN",
            "Model Year": "Invalid VIN",
            "Body Type": "Invalid VIN",
            "Vehicle Class": "Invalid VIN",
            "Fuel Type": "Invalid VIN",
        }


def find_vin_column(df):
    for column in df.columns:
        if df[column].astype(str).str.match(r'^[A-HJ-NPR-Z0-9]{17}$').any():
            return column
    return None


# Routes
@app.route('/', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def index():
    if request.method == 'POST':
        # Handle file upload
        if 'file' not in request.files:
            return render_template('index.html', error="No file part")
        file = request.files['file']
        if file.filename == '':
            return render_template('index.html', error="No selected file")
        if file and allowed_file(file.filename):
            unique_filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)

            # Process the spreadsheet
            try:
                df = pd.read_excel(filepath) if unique_filename.endswith(('xlsx', 'xls')) else pd.read_csv(filepath)
                vin_column = find_vin_column(df)
                if vin_column is None:
                    return render_template('index.html', error="No valid VIN column found in the spreadsheet")

                # Get VIN details for each row
                vin_details_list = []
                for vin in df[vin_column].dropna().astype(str):
                    vin = vin.strip().upper()
                    if len(vin) == 17:
                        vin_data = get_vin_data(vin)
                        vin_data['VIN'] = vin
                        vin_details_list.append(vin_data)
                    else:
                        vin_details_list.append({
                            "VIN": vin,
                            "Make": "Invalid VIN",
                            "Model": "Invalid VIN",
                            "Model Year": "Invalid VIN",
                            "Body Type": "Invalid VIN",
                            "Vehicle Class": "Invalid VIN",
                            "Fuel Type": "Invalid VIN",
                        })

                # Create a DataFrame with results
                results_df = pd.DataFrame(vin_details_list)

                # Replace any NaN values with 'Not Found' to avoid empty cells in the HTML output
                results_df.fillna('Not Found', inplace=True)

                # Save to Excel
                results_filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"decoded_vins_results_{uuid.uuid4().hex}.xlsx")
                results_df.to_excel(results_filepath, index=False)

                # Store the file path in session for download
                session['results_filepath'] = results_filepath

                # Render results page
                return render_template('results.html', tables=[results_df.to_html(classes='table table-bordered table-striped', index=False)],
                                       download_link=url_for('download', filename=os.path.basename(results_filepath)))
            except Exception as e:
                return render_template('index.html', error=f"Error processing file: {str(e)}")

    return render_template('index.html')


@app.route('/download/<filename>')
def download(filename):
    results_filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(results_filepath):
        return send_file(results_filepath, as_attachment=True)
    else:
        return "No file available for download", 404


@app.route('/favicon.ico')
def favicon():
    return send_file(os.path.join(app.root_path, 'static', 'favicon.ico'))


if __name__ == '__main__':
	public_url = ngrok.connect(port).public_url
    print(f" * ngrok tunnel available at {public_url}")

    # Launch Flask app
    app.run(host='0.0.0.0', port=port)

# HTML Templates
# index.html
index_html = '''
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VIN Decoder</title>
    <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">
</head>
<body>
<div class="container mt-5">
    <h1 class="text-center">VIN Decoder</h1>
    <form method="POST" enctype="multipart/form-data">
        <div class="form-group">
            <label for="file">Upload Spreadsheet (xlsx, xls, csv):</label>
            <input type="file" class="form-control-file" id="file" name="file" required>
        </div>
        <button type="submit" class="btn btn-primary">Upload and Decode VINs</button>
    </form>
    {% if error %}
        <div class="alert alert-danger mt-3" role="alert">
            {{ error }}
        </div>
    {% endif %}
</div>
</body>
</html>
'''

# results.html
results_html = '''
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VIN Decoder Results</title>
    <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">
</head>
<body>
<div class="container mt-5">
    <h1 class="text-center">VIN Decoder Results</h1>
    <div class="table-responsive">
        {{ tables|safe }}
    </div>
    <a href="{{ download_link }}" class="btn btn-success mt-3">Download Results as Excel</a>
</div>
</body>
</html>
'''

# Save HTML Templates to Files
with open('templates/index.html', 'w') as f:
    f.write(index_html)

with open('templates/results.html', 'w') as f:
    f.write(results_html)