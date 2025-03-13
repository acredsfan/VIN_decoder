import os
import shutil

from flask import Flask, request, render_template, send_file, url_for, session
import requests
import pandas as pd
from werkzeug.utils import secure_filename
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import uuid
from pyngrok import ngrok
import dotenv
import sys
import subprocess

# Check and create virtual environment if it doesn't exist
def setup_virtualenv(venv_name='venv'):
    if not os.path.exists(venv_name):
        subprocess.check_call([sys.executable, '-m', 'venv', venv_name])

    if sys.platform == 'win32':
        activate_script = os.path.join(venv_name, 'Scripts', 'python.exe')
    else:
        activate_script = os.path.join(venv_name, 'bin', 'python')

    return activate_script

# kill ngrok agents via admin to prevent multiple agents running
os.system("sudo pkill ngrok")

# Load .env file
dotenv.load_dotenv()

# Load Public URL from .env
custom_domain = os.getenv('PUBLIC_URL')

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls', 'csv'}
app.secret_key = os.urandom(24)

# Rate Limiter to prevent abuse
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["500 per minute"]
)

# Ensure upload folder exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

NHTSA_API_BASE = 'https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/'

# Helper functions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def clean_uploads_folder():
    for filename in os.listdir(app.config['UPLOAD_FOLDER']):
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print('Failed to delete %s. Reason: %s' % (file_path, e))


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
        return {key: "Invalid VIN" for key in ["Make", "Model", "Model Year", "Body Type", "Vehicle Class", "Fuel Type"]}


def find_vin_column(df):
    for column in df.columns:
        if df[column].astype(str).str.match(r'^[A-HJ-NPR-Z0-9]{17}$').any():
            return column
    return None


@app.route('/', methods=['GET', 'POST'])
@limiter.limit("500 per minute")
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template('index.html', error="No file part")
        file = request.files['file']
        if file.filename == '':
            return render_template('index.html', error="No selected file")
        if file and allowed_file(file.filename):
            unique_filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)

            try:
                df = pd.read_excel(filepath) if unique_filename.endswith(('xlsx', 'xls')) else pd.read_csv(filepath)
                vin_column = find_vin_column(df)
                if vin_column is None:
                    return render_template('index.html', error="No valid VIN column found in the spreadsheet")

                batch_size = 100
                vin_series = df[vin_column].dropna().astype(str).str.strip().str.upper()
                vin_details_list = []

                for start in range(0, len(vin_series), batch_size):
                    batch = vin_series[start:start + batch_size]
                    batch_results = [get_vin_data(vin) | {'VIN': vin} if len(vin) == 17 else
                                     {"VIN": vin, "Make": "Invalid VIN", "Model": "Invalid VIN", "Model Year": "Invalid VIN",
                                      "Body Type": "Invalid VIN", "Vehicle Class": "Invalid VIN", "Fuel Type": "Invalid VIN"}
                                     for vin in batch]
                    vin_details_list.extend(batch_results)

                results_df = pd.DataFrame(vin_details_list).astype(str).fillna('Not Found')

                results_filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"decoded_vins_results_{uuid.uuid4().hex}.xlsx")
                results_df.to_excel(results_filepath, index=False)

                session['results_filepath'] = results_filepath

                clean_uploads_folder()

                return render_template('results.html', tables=[results_df.to_html(classes='table table-bordered table-striped', index=False)],
                                       download_link=url_for('download', filename=os.path.basename(results_filepath)))
            except Exception as e:
                return render_template('index.html', error=f"Error processing file: {str(e)}")

    return render_template('index.html')

@app.route('/download/<filename>')
def download(filename):
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    return send_file(path, as_attachment=True) if os.path.exists(path) else "No file available for download", 404

@app.route('/favicon.ico')
def favicon():
    return send_file(os.path.join(app.root_path, 'static', 'favicon.ico'))

if __name__ == '__main__':
    os.system("sudo pkill ngrok")
    public_url = ngrok.connect(5000, domain=custom_domain, bind_tls=True).public_url
    print(f" * Public URL: {public_url}")
    app.run(debug=True, host='0.0.0.0', port=5000)
