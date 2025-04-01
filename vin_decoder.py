import os
import threading
import uuid
import dotenv
from flask import Flask, request, render_template, send_file, jsonify
import requests
import pandas as pd
from werkzeug.utils import secure_filename
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
import re

# Load environment variables
dotenv.load_dotenv()

BASE_DIR = '/home/pi/VIN_decoder'
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'static')
)
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'uploads')
app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls', 'csv'}
app.secret_key = os.urandom(24)
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)

limiter = Limiter(get_remote_address, app=app, default_limits=["500 per minute"])

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

NHTSA_API_BASE = 'https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/'
STATUS = {"progress": "Not started", "current": 0, "total": 0, "completed": False, "file": ""}

VIN_REGEX = re.compile(r'^(?!.*[IOQ])[A-HJ-NPR-Z0-9]{17}$', re.IGNORECASE)

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
            "Trim": next((item['Value'] for item in results if item['Variable'] == 'Trim'), "Not Found"),
            "Body Type": next((item['Value'] for item in results if item['Variable'] == 'Body Class'), "Not Found"),
            "Vehicle Type": next((item['Value'] for item in results if item['Variable'] == 'Vehicle Type'), "Not Found"),
            "Vehicle Class": next((item['Value'] for item in results if item['Variable'] == 'Gross Vehicle Weight Rating From'), "Not Found"),
            "Fuel Type": next((item['Value'] for item in results if item['Variable'] == 'Fuel Type - Primary'), "Not Found"),
        }
        return vin_data
    else:
        return {key: "Invalid VIN" for key in ["Make", "Model", "Model Year", "Body Type", "Vehicle Class", "Fuel Type"]}

def find_vin_column(df):
    for column in df.columns:
        if df[column].astype(str).str.match(VIN_REGEX).any():
            return column
    return None

def find_first_vin_row(df, vin):
    for index, row in df.iterrows():
        if row[vin] and VIN_REGEX.match(row[vin]):
            return index
    return 0

def get_mpg(make, model, year):
    # (unchanged, for brevity)
    return {"MPG City": "No Data", "MPG Highway": "No Data", "MPG Combined": "No Data"}

def process_vins_in_background(vin_series, batch_size=100):
    global STATUS
    vin_details_list = []
    STATUS.update({"total": len(vin_series), "completed": False})
    vin_count = 0

    for start in range(0, len(vin_series), batch_size):
        batch = vin_series[start:start + batch_size]
        for vin in batch:
            STATUS['current'] = vin_count
            STATUS['progress'] = f"Processing VIN {vin_count+1}/{STATUS['total']}"
            vin_data = get_vin_data(vin)
            mpg_data = get_mpg(vin_data["Make"], vin_data["Model"], vin_data["Model Year"])
            vin_data.update(mpg_data)
            vin_data['VIN'] = vin
            vin_details_list.append(vin_data)
            vin_count += 1

    results_df = pd.DataFrame(vin_details_list).fillna('Not Found')
    results_filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"decoded_{uuid.uuid4().hex}.xlsx")
    results_df.to_excel(results_filepath, index=False)
    STATUS.update({"completed": True, "progress": "Completed", "file": os.path.basename(results_filepath)})

@app.route('/', methods=['GET', 'POST'])
@limiter.limit("500 per minute")
def index():
    global STATUS
    STATUS = {"progress": "Not started", "current": 0, "total": 0, "completed": False, "file": ""}
    if request.method == 'POST':
        file = request.files.get('file')
        if file and allowed_file(file.filename):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
            file.save(filepath)
            df = pd.read_excel(filepath) if filepath.endswith(('xlsx', 'xls')) else pd.read_csv(filepath)
            vin_column = find_vin_column(df)
            if vin_column:
                vin_series = df[vin_column].dropna().astype(str).str.upper().unique()
                threading.Thread(target=process_vins_in_background, args=(vin_series,)).start()
                return render_template('status.html')
            else:
                return render_template('index.html', error="No VIN column found.")
    return render_template('index.html')

@app.route('/status')
def status():
    return jsonify(STATUS)

@app.route('/download/<filename>')
def download(filename):
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], filename), as_attachment=True)

with open('templates/index.html', 'w') as f:
    f.write('''
<!doctype html>
<html lang="en">
<head>
    <title>VIN Decoder</title>
    <base href="/vin-lookup/">
</head>
<body>
<form method="POST" enctype="multipart/form-data">
    <input type="file" name="file" required>
    <button type="submit">Decode VINs</button>
</form>
{% if error %}<p>{{ error }}</p>{% endif %}
</body>
</html>
''')

with open('templates/status.html', 'w') as f:
    f.write('''
<!doctype html>
<html>
<head><title>Status</title></head>
<body>
<p id="status">Starting...</p>
<script>
const interval = setInterval(() => {
  fetch('/vin-lookup/status')
    .then(res => res.json())
    .then(data => {
      document.getElementById('status').innerText = data.progress;
      if (data.completed) {
        clearInterval(interval);
        window.location.href = '/vin-lookup/download/' + data.file;
      }
    });
}, 3000);
</script>
</body>
</html>
''')

if __name__ == '__main__':
    port = 5000
    app.run(debug=False, host='0.0.0.0', port=port)
