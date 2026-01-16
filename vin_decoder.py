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

# Base directory for templates/static/uploads.
# Raspberry Pi default; optionally override via VIN_DECODER_BASE_DIR environment variable.
BASE_DIR = os.getenv('VIN_DECODER_BASE_DIR') or '/home/pi/VIN_decoder'
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

# Fleet-focused field set (ICE + EV + key safety/ADAS + operational specs).
# Keys are the output column names; values are the official vPIC "Variable" names.
FLEET_FIELD_MAP = {
    # Core identification
    "Make": "Make",
    "Model": "Model",
    "Model Year": "Model Year",
    "Vehicle Type": "Vehicle Type",
    "Body Type": "Body Class",  # legacy output name used by this app
    "Body Class": "Body Class",
    "Trim": "Trim",
    "Trim2": "Trim2",
    "Series": "Series",
    "Series2": "Series2",
    "Manufacturer Name": "Manufacturer Name",
    "Destination Market": "Destination Market",

    # Manufacturing / plant
    "Plant Country": "Plant Country",
    "Plant State": "Plant State",
    "Plant City": "Plant City",
    "Plant Company Name": "Plant Company Name",

    # Weight / class / dimensions (fleet operations, compliance, upfit)
    "Vehicle Class": "Gross Vehicle Weight Rating From",  # legacy output name used by this app
    "GVWR From": "Gross Vehicle Weight Rating From",
    "GVWR To": "Gross Vehicle Weight Rating To",
    "GCWR From": "Gross Combination Weight Rating From",
    "GCWR To": "Gross Combination Weight Rating To",
    "Curb Weight (pounds)": "Curb Weight (pounds)",
    "Wheel Base (inches) From": "Wheel Base (inches) From",
    "Wheel Base (inches) To": "Wheel Base (inches) To",
    "Track Width (inches)": "Track Width (inches)",

    # Truck / chassis configuration
    "Cab Type": "Cab Type",
    "Bed Type": "Bed Type",
    "Bed Length (inches)": "Bed Length (inches)",
    "Doors": "Doors",
    "Number of Seats": "Number of Seats",
    "Number of Seat Rows": "Number of Seat Rows",
    "Number of Wheels": "Number of Wheels",
    "Wheel Size Front (inches)": "Wheel Size Front (inches)",
    "Wheel Size Rear (inches)": "Wheel Size Rear (inches)",
    "Axles": "Axles",
    "Axle Configuration": "Axle Configuration",
    "Drive Type": "Drive Type",
    "Steering Location": "Steering Location",
    "Brake System Type": "Brake System Type",
    "Brake System Description": "Brake System Description",
    "Trailer Body Type": "Trailer Body Type",
    "Trailer Type Connection": "Trailer Type Connection",
    "Trailer Length (feet)": "Trailer Length (feet)",

    # Powertrain (ICE/Hybrid/EV)
    "Fuel Type": "Fuel Type - Primary",  # legacy output name used by this app
    "Fuel Type - Primary": "Fuel Type - Primary",
    "Fuel Type - Secondary": "Fuel Type - Secondary",
    "Electrification Level": "Electrification Level",
    "Engine Manufacturer": "Engine Manufacturer",
    "Engine Model": "Engine Model",
    "Displacement (L)": "Displacement (L)",
    "Displacement (CC)": "Displacement (CC)",
    "Displacement (CI)": "Displacement (CI)",
    "Engine Number of Cylinders": "Engine Number of Cylinders",
    "Engine Configuration": "Engine Configuration",
    "Valve Train Design": "Valve Train Design",
    "Fuel Delivery / Fuel Injection Type": "Fuel Delivery / Fuel Injection Type",
    "Cooling Type": "Cooling Type",
    "Engine Stroke Cycles": "Engine Stroke Cycles",
    "Turbo": "Turbo",
    "Engine Power (kW)": "Engine Power (kW)",
    "Engine Brake (hp) From": "Engine Brake (hp) From",
    "Engine Brake (hp) To": "Engine Brake (hp) To",
    "Other Engine Info": "Other Engine Info",
    "Transmission Style": "Transmission Style",
    "Transmission Speeds": "Transmission Speeds",
    "Top Speed (MPH)": "Top Speed (MPH)",

    # EV / battery / charging
    "Battery Type": "Battery Type",
    "Battery Energy (kWh) From": "Battery Energy (kWh) From",
    "Battery Energy (kWh) To": "Battery Energy (kWh) To",
    "Battery Voltage (Volts) From": "Battery Voltage (Volts) From",
    "Battery Voltage (Volts) To": "Battery Voltage (Volts) To",
    "Battery Current (Amps) From": "Battery Current (Amps) From",
    "Battery Current (Amps) To": "Battery Current (Amps) To",
    "Number of Battery Cells per Module": "Number of Battery Cells per Module",
    "Number of Battery Modules per Pack": "Number of Battery Modules per Pack",
    "Number of Battery Packs per Vehicle": "Number of Battery Packs per Vehicle",
    "EV Drive Unit": "EV Drive Unit",
    "Charger Level": "Charger Level",
    "Charger Power (kW)": "Charger Power (kW)",
    "Other Battery Info": "Other Battery Info",

    # Safety / ADAS (useful for safety programs, policy, insurance; availability varies)
    "Anti-lock Braking System (ABS)": "Anti-lock Braking System (ABS)",
    "Electronic Stability Control (ESC)": "Electronic Stability Control (ESC)",
    "Traction Control": "Traction Control",
    "Tire Pressure Monitoring System (TPMS) Type": "Tire Pressure Monitoring System (TPMS) Type",
    "Backup Camera": "Backup Camera",
    "Parking Assist": "Parking Assist",
    "Rear Cross Traffic Alert": "Rear Cross Traffic Alert",
    "Rear Automatic Emergency Braking": "Rear Automatic Emergency Braking",
    "Adaptive Cruise Control (ACC)": "Adaptive Cruise Control (ACC)",
    "Forward Collision Warning (FCW)": "Forward Collision Warning (FCW)",
    "Crash Imminent Braking (CIB)": "Crash Imminent Braking (CIB)",
    "Dynamic Brake Support (DBS)": "Dynamic Brake Support (DBS)",
    "Pedestrian Automatic Emergency Braking (PAEB)": "Pedestrian Automatic Emergency Braking (PAEB)",
    "Lane Departure Warning (LDW)": "Lane Departure Warning (LDW)",
    "Lane Keeping Assistance (LKA)": "Lane Keeping Assistance (LKA)",
    "Lane Centering Assistance": "Lane Centering Assistance",
    "Blind Spot Warning (BSW)": "Blind Spot Warning (BSW)",
    "Blind Spot Intervention (BSI)": "Blind Spot Intervention (BSI)",
    "Automatic Crash Notification (ACN) / Advanced Automatic Crash Notification (AACN)": "Automatic Crash Notification (ACN) / Advanced Automatic Crash Notification (AACN)",
    "Event Data Recorder (EDR)": "Event Data Recorder (EDR)",
    "Keyless Ignition": "Keyless Ignition",
    "Daytime Running Light (DRL)": "Daytime Running Light (DRL)",
    "Headlamp Light Source": "Headlamp Light Source",
    "Semiautomatic Headlamp Beam Switching": "Semiautomatic Headlamp Beam Switching",
    "Adaptive Driving Beam (ADB)": "Adaptive Driving Beam (ADB)",
    "Auto-Reverse System for Windows and Sunroofs": "Auto-Reverse System for Windows and Sunroofs",
    "Automatic Pedestrian Alerting Sound (for Hybrid and EV only)": "Automatic Pedestrian Alerting Sound (for Hybrid and EV only)",
    "SAE Automation Level From": "SAE Automation Level From",
    "SAE Automation Level To": "SAE Automation Level To",
    "Active Safety System Note": "Active Safety System Note",

    # Passive safety (sometimes useful for safety/compliance reporting)
    "Front Air Bag Locations": "Front Air Bag Locations",
    "Side Air Bag Locations": "Side Air Bag Locations",
    "Curtain Air Bag Locations": "Curtain Air Bag Locations",
    "Knee Air Bag Locations": "Knee Air Bag Locations",
    "Seat Cushion Air Bag Locations": "Seat Cushion Air Bag Locations",
    "Seat Belt Type": "Seat Belt Type",
    "Pretensioner": "Pretensioner",

    # Decode quality / debugging
    "Error Code": "Error Code",
    "Error Text": "Error Text",
    "Additional Error Text": "Additional Error Text",
    "Suggested VIN": "Suggested VIN",
    "Possible Values": "Possible Values",
    "Vehicle Descriptor": "Vehicle Descriptor",
    "Note": "Note",
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_vin_data(vin):
    response = requests.get(f"{NHTSA_API_BASE}{vin}?format=json")
    if response.status_code == 200:
        results = response.json().get('Results', [])
        decoded_lookup = {}
        for item in results:
            var_name = item.get('Variable')
            if not var_name:
                continue
            decoded_lookup[var_name] = item.get('Value')

        def pick(var_name):
            val = decoded_lookup.get(var_name)
            if val is None:
                return "Not Found"
            if isinstance(val, str) and val.strip() == "":
                return "Not Found"
            return val

        vin_data = {out_key: pick(var_name) for out_key, var_name in FLEET_FIELD_MAP.items()}
        return vin_data
    else:
        return {key: "Invalid VIN" for key in FLEET_FIELD_MAP.keys()}

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
        if file and file.filename and allowed_file(file.filename):
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
<head>
    <title>Status</title>
</head>
<body>
<p id="status">Starting...</p>
<script>
const interval = setInterval(() => {
  // Using a relative URL: since the current URL is /vin-lookup/ this becomes /vin-lookup/status
  fetch('status')
    .then(res => res.json())
    .then(data => {
      document.getElementById('status').innerText = data.progress;
      if (data.completed) {
        clearInterval(interval);
        // Relative URL: becomes /vin-lookup/download/<filename>
        window.location.href = 'download/' + data.file;
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
