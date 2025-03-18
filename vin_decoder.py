import os
import threading
import uuid
import dotenv
from flask import Flask, request, render_template, send_file, session, jsonify, url_for
import requests
import pandas as pd
from werkzeug.utils import secure_filename
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
# from pyngrok import ngrok
import re

# Clean ngrok agents
# os.system("pkill ngrok")

# Load environment variables
# dotenv.load_dotenv()

# Get custom domain from .env
# custom_domain = os.getenv('PUBLIC_URL')

# Flask app setup
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls', 'csv'}
app.secret_key = os.urandom(24)

# Rate Limiter setup
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["500 per minute"]
)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

NHTSA_API_BASE = 'https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/'

STATUS = {"progress": "Not started", "current": 0, "total": 0, "completed": False, "file": ""}

VIN_REGEX = re.compile(r'^(?!.*[IOQ])[A-HJ-NPR-Z0-9]{17}$', re.IGNORECASE)

# Helper Functions
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
            "Trim": next((item['Value'] for item in results if item ['Variable'] == 'Trim'), "Not Found"),
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
        if df[column].astype(str).str.match(r'^[A-HJ-NPR-Z0-9]{17}$').any():
            return column
    return None

def find_first_vin_row(df, vin):
    for index, row in df.iterrows():
        if row[vin] and VIN_REGEX.match(row[vin]):
            print(f"Found VIN at row {index}")
            return index

def get_mpg(make, model, year):
    url = f'https://www.fueleconomy.gov/ws/rest/vehicle/menu/options?year={year}&make={make}&model={model}&format=json'
    try:
        response = requests.get(url, headers={"Accept": "application/json"}, timeout=5)
        if response.status_code == 200:
            data = response.json()

            if isinstance(data, dict):
                options = data.get('menuItem', [])
                if isinstance(options, list) and options:
                    vehicle_id = options[0].get('value')
                    if vehicle_id:
                        mpg_url = f'https://www.fueleconomy.gov/ws/rest/vehicle/{vehicle_id}?format=json'
                        mpg_response = requests.get(mpg_url, headers={"Accept": "application/json"}, timeout=5)
                        if mpg_response.status_code == 200:
                            mpg_data = mpg_response.json()
                            return {
                                "MPG City": mpg_data.get("city08", "Not Found"),
                                "MPG Highway": mpg_data.get("highway08", "Not Found"),
                                "MPG Combined": mpg_data.get("comb08", "Not Found")
                            }
    except requests.RequestException as e:
        print(f"RequestException: {e}")

    # Fallback response
    return {"MPG City": "No Data", "MPG Highway": "No Data", "MPG Combined": "No Data"}


def process_vins_in_background(vin_series, batch_size=100):
    global STATUS

    vin_details_list = []
    STATUS["total"] = len(vin_series)
    STATUS["completed"] = False

    total_batches = (len(vin_series) - 1) // batch_size + 1
    vin_count = 0

    for current_batch, start in enumerate(range(0, len(vin_series), batch_size), 1):
        batch = vin_series[start:start + batch_size]

        for idx, vin in enumerate(batch, start=1):
            current_position = start + idx
            STATUS['progress'] = f"Processing VIN {current_position} of {STATUS['total']}"
            vin = vin.strip().upper()
            if len(vin) == 17:
                vin_data = get_vin_data(vin)
                mpg_data = get_mpg(vin_data["Make"], vin_data["Model"], vin_data["Model Year"])
                vin_data.update(mpg_data)
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
                    "MPG City": "Invalid VIN",
                    "MPG Highway": "Invalid VIN",
                    "MPG Combined": "Invalid VIN"
                })

            vin_count += 1
            STATUS['current'] = vin_count

    # Ensure VIN column is first in output
    results_df = pd.DataFrame(vin_details_list).astype(str).fillna('Not Found')
    cols = results_df.columns.tolist()
    if 'VIN' in cols:
        cols.insert(0, cols.pop(cols.index('VIN')))
        results_df = results_df[cols]

    results_filepath = os.path.join(
        app.config['UPLOAD_FOLDER'],
        f"decoded_vins_results_{uuid.uuid4().hex}.xlsx"
    )
    results_df.to_excel(results_filepath, index=False)

    STATUS["completed"] = True
    STATUS["progress"] = "Completed"
    STATUS["file"] = os.path.basename(results_filepath)

@app.route('/', methods=['GET', 'POST'])
@limiter.limit("500 per minute")
def index():
    global STATUS
    STATUS = {"progress": "Not started", "current": 0, "total": 0, "completed": False, "file": ""}

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
                vin_row_start = find_first_vin_row(df, vin_column)

                if vin_column is None:
                    return render_template('index.html', error="No valid VIN column found.")

                vin_series = df[vin_column][vin_row_start:].dropna().astype(str).str.upper().unique()

                thread = threading.Thread(target=process_vins_in_background, args=(vin_series,))
                thread.start()

                return render_template('status.html')

            except Exception as e:
                return render_template('index.html', error=f"Error processing file: {str(e)}")

    return render_template('index.html')

@app.route('/status')
def status():
    return jsonify(STATUS)

@app.route('/download/<filename>')
def download(filename):
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return "File not found.", 404

# Templates
with open('templates/index.html', 'w') as f:
    f.write('''
<!doctype html>
<html lang="en">
<head>
    <title>VIN Decoder</title>
</head>
<body>
<form method="POST" enctype="multipart/form-data">
    <input type="file" name="file" required>
    <button type="submit">Decode VINs</button>
</form>
{% if error %}<p>{{error}}</p>{% endif %}
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
let downloadTriggered = false;
const interval = setInterval(() => {
  fetch('/status')
    .then(response => response.json())
    .then(data => {
      document.getElementById('status').innerText = data.progress;
      if (data.completed && !downloadTriggered) {
        downloadTriggered = true;
        clearInterval(interval);
        window.location.href = '/download/' + data.file;
      }
    });
}, 3000);  // update every 3 seconds
</script>
</body>
</html>
''')


if __name__ == '__main__':
    port = 5000

    # os.system("pkill ngrok")

    # if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        # public_url = ngrok.connect(port, domain=custom_domain, bind_tls=True).public_url
        # print(f" * Public URL: {public_url}")

    app.run(debug=True, host='0.0.0.0', port=port)
