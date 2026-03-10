import json
import logging
import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import dotenv
import pandas as pd
import requests
from flask import (
    Flask,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename

from config import get_config_class

SCRIPT_DIR = Path(__file__).resolve().parent
dotenv.load_dotenv(SCRIPT_DIR / ".env")

LOGGER = logging.getLogger("vin_decoder")
CLEANUP_LOCK = threading.Lock()
LAST_CLEANUP_AT = 0.0

VIN_REGEX = re.compile(r"^(?!.*[IOQ])[A-HJ-NPR-Z0-9]{17}$", re.IGNORECASE)

FLEET_FIELD_MAP = {
    "Make": "Make",
    "Model": "Model",
    "Model Year": "Model Year",
    "Vehicle Type": "Vehicle Type",
    "Body Type": "Body Class",
    "Body Class": "Body Class",
    "Trim": "Trim",
    "Trim2": "Trim2",
    "Series": "Series",
    "Series2": "Series2",
    "Manufacturer Name": "Manufacturer Name",
    "Destination Market": "Destination Market",
    "Plant Country": "Plant Country",
    "Plant State": "Plant State",
    "Plant City": "Plant City",
    "Plant Company Name": "Plant Company Name",
    "Vehicle Class": "Gross Vehicle Weight Rating From",
    "GVWR From": "Gross Vehicle Weight Rating From",
    "GVWR To": "Gross Vehicle Weight Rating To",
    "GCWR From": "Gross Combination Weight Rating From",
    "GCWR To": "Gross Combination Weight Rating To",
    "Curb Weight (pounds)": "Curb Weight (pounds)",
    "Wheel Base (inches) From": "Wheel Base (inches) From",
    "Wheel Base (inches) To": "Wheel Base (inches) To",
    "Track Width (inches)": "Track Width (inches)",
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
    "Fuel Type": "Fuel Type - Primary",
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
    "Front Air Bag Locations": "Front Air Bag Locations",
    "Side Air Bag Locations": "Side Air Bag Locations",
    "Curtain Air Bag Locations": "Curtain Air Bag Locations",
    "Knee Air Bag Locations": "Knee Air Bag Locations",
    "Seat Cushion Air Bag Locations": "Seat Cushion Air Bag Locations",
    "Seat Belt Type": "Seat Belt Type",
    "Pretensioner": "Pretensioner",
    "Error Code": "Error Code",
    "Error Text": "Error Text",
    "Additional Error Text": "Additional Error Text",
    "Suggested VIN": "Suggested VIN",
    "Possible Values": "Possible Values",
    "Vehicle Descriptor": "Vehicle Descriptor",
    "Note": "Note",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().strftime("%Y-%m-%d %H:%M:%S")


def parse_datetime(value: str):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def build_requests_session() -> requests.Session:
    session = requests.Session()
    adapter = HTTPAdapter(
        max_retries=Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def ensure_directories(app: Flask) -> None:
    for key in ("BASE_DIR", "UPLOAD_DIR", "DATA_DIR", "LOG_DIR"):
        Path(app.config[key]).mkdir(parents=True, exist_ok=True)


def setup_logging(app: Flask) -> None:
    LOGGER.setLevel(getattr(logging, app.config["LOG_LEVEL"], logging.INFO))
    if LOGGER.handlers:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.propagate = False


def log_event(event: str, **fields) -> None:
    parts = [f'event="{event}"']
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={json.dumps(value, default=str)}")
    LOGGER.info(" ".join(parts))


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(current_app.config["DB_PATH"], timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(app: Flask) -> None:
    with app.app_context():
        conn = sqlite3.connect(app.config["DB_PATH"], timeout=10)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                source_filename TEXT,
                stored_upload_name TEXT,
                status TEXT NOT NULL,
                progress TEXT NOT NULL,
                current INTEGER NOT NULL DEFAULT 0,
                total INTEGER NOT NULL DEFAULT 0,
                completed INTEGER NOT NULL DEFAULT 0,
                error INTEGER NOT NULL DEFAULT 0,
                output_file TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vin_cache (
                vin TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()


def default_status_payload():
    return {
        "job_id": None,
        "status": "idle",
        "progress": "Not started",
        "current": 0,
        "total": 0,
        "completed": False,
        "file": "",
        "error": False,
        "download_url": None,
        "source_filename": None,
        "created_at": None,
        "updated_at": None,
    }


def serialize_job(row):
    if not row:
        return default_status_payload()

    output_file = row["output_file"] or ""
    return {
        "job_id": row["job_id"],
        "status": row["status"],
        "progress": row["progress"],
        "current": row["current"],
        "total": row["total"],
        "completed": bool(row["completed"]),
        "file": output_file,
        "error": bool(row["error"]),
        "download_url": url_for("download_job", job_id=row["job_id"]) if output_file else None,
        "source_filename": row["source_filename"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_job_record(job_id: str, source_filename: str, stored_upload_name: str, total: int) -> None:
    now = utc_now_iso()
    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO jobs (
            job_id, source_filename, stored_upload_name, status, progress,
            current, total, completed, error, output_file, created_at, updated_at, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            source_filename,
            stored_upload_name,
            "queued",
            "Queued",
            0,
            total,
            0,
            0,
            None,
            now,
            now,
            None,
        ),
    )
    conn.commit()
    conn.close()


def update_job_record(job_id: str, **fields) -> None:
    if not fields:
        return

    fields["updated_at"] = utc_now_iso()
    assignments = ", ".join(f"{key} = ?" for key in fields.keys())
    values = [int(value) if isinstance(value, bool) else value for value in fields.values()]
    values.append(job_id)

    conn = get_db_connection()
    conn.execute(f"UPDATE jobs SET {assignments} WHERE job_id = ?", values)
    conn.commit()
    conn.close()


def get_job_record(job_id: str):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    conn.close()
    return row


def get_latest_job_record():
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT 1").fetchone()
    conn.close()
    return row


def list_recent_jobs(limit: int):
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()

    items = []
    for row in rows:
        item = dict(row)
        item["status_label"] = item["status"].replace("_", " ").title()
        item["status_class"] = item["status"].replace("_", "-")
        items.append(item)
    return items


def get_cached_vin_data(vin: str):
    cutoff = utc_now() - timedelta(hours=current_app.config["CACHE_TTL_HOURS"])
    conn = get_db_connection()
    row = conn.execute("SELECT payload, updated_at FROM vin_cache WHERE vin = ?", (vin,)).fetchone()

    if not row:
        conn.close()
        return None

    updated_at = parse_datetime(row["updated_at"])
    if updated_at and updated_at < cutoff:
        conn.execute("DELETE FROM vin_cache WHERE vin = ?", (vin,))
        conn.commit()
        conn.close()
        return None

    payload = json.loads(row["payload"])
    conn.close()
    return payload


def cache_vin_data(vin: str, payload) -> None:
    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO vin_cache (vin, payload, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(vin) DO UPDATE SET
            payload = excluded.payload,
            updated_at = excluded.updated_at
        """,
        (vin, json.dumps(payload), utc_now_iso()),
    )
    conn.commit()
    conn.close()


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in current_app.config["ALLOWED_EXTENSIONS"]


def get_vin_data(vin: str):
    cached = get_cached_vin_data(vin)
    if cached:
        return cached

    try:
        response = current_app.extensions["vin_decoder_http_session"].get(
            f"{current_app.config['NHTSA_API_BASE']}{vin}?format=json",
            timeout=current_app.config["REQUEST_TIMEOUT_SECONDS"],
        )
        response.raise_for_status()
        results = response.json().get("Results", [])
        decoded_lookup = {}
        for item in results:
            variable = item.get("Variable")
            if variable:
                decoded_lookup[variable] = item.get("Value")

        def pick(variable_name):
            value = decoded_lookup.get(variable_name)
            if value is None:
                return "Not Found"
            if isinstance(value, str) and not value.strip():
                return "Not Found"
            return value

        payload = {out_key: pick(var_name) for out_key, var_name in FLEET_FIELD_MAP.items()}
        cache_vin_data(vin, payload)
        return payload
    except (requests.RequestException, ValueError):
        return {key: "Lookup Error" for key in FLEET_FIELD_MAP.keys()}


def find_vin_column(df: pd.DataFrame):
    for column in df.columns:
        if df[column].astype(str).str.match(VIN_REGEX).any():
            return column
    return None


def get_mpg(make, model, year):
    return {"MPG City": "No Data", "MPG Highway": "No Data", "MPG Combined": "No Data"}


def run_cleanup_if_due(force: bool = False) -> None:
    global LAST_CLEANUP_AT

    with CLEANUP_LOCK:
        now = datetime.now().timestamp()
        if not force and now - LAST_CLEANUP_AT < 300:
            return
        LAST_CLEANUP_AT = now

    with current_app.app_context():
        job_cutoff = utc_now() - timedelta(hours=current_app.config["CLEANUP_TTL_HOURS"])
        cache_cutoff = utc_now() - timedelta(hours=current_app.config["CACHE_TTL_HOURS"])
        cutoff_iso = job_cutoff.strftime("%Y-%m-%d %H:%M:%S")
        cache_cutoff_iso = cache_cutoff.strftime("%Y-%m-%d %H:%M:%S")

        conn = get_db_connection()
        stale_jobs = conn.execute(
            """
            SELECT job_id, stored_upload_name, output_file
            FROM jobs
            WHERE updated_at < ?
              AND (completed = 1 OR error = 1)
            """,
            (cutoff_iso,),
        ).fetchall()

        for row in stale_jobs:
            for file_name in (row["stored_upload_name"], row["output_file"]):
                if file_name:
                    path = Path(current_app.config["UPLOAD_DIR"]) / file_name
                    path.unlink(missing_ok=True)

        if stale_jobs:
            conn.executemany("DELETE FROM jobs WHERE job_id = ?", [(row["job_id"],) for row in stale_jobs])

        conn.execute("DELETE FROM vin_cache WHERE updated_at < ?", (cache_cutoff_iso,))
        conn.commit()
        conn.close()

        if stale_jobs:
            log_event("cleanup.completed", removed_jobs=len(stale_jobs))


def process_vins_in_background(app: Flask, job_id: str, vin_series, batch_size: int = 100) -> None:
    with app.app_context():
        try:
            update_job_record(
                job_id,
                status="processing",
                progress="Starting decode...",
                current=0,
                total=len(vin_series),
                completed=False,
                error=False,
            )

            vin_details_list = []
            total = len(vin_series)

            for index, vin in enumerate(vin_series, start=1):
                update_job_record(
                    job_id,
                    progress=f"Processing VIN {index}/{total}",
                    current=index - 1,
                    total=total,
                )
                vin_data = get_vin_data(vin)
                mpg_data = get_mpg(vin_data["Make"], vin_data["Model"], vin_data["Model Year"])
                vin_data.update(mpg_data)
                vin_data["VIN"] = vin
                vin_details_list.append(vin_data)

            results_df = pd.DataFrame(vin_details_list).fillna("Not Found")
            output_file = f"decoded_{job_id}.xlsx"
            result_path = Path(current_app.config["UPLOAD_DIR"]) / output_file
            results_df.to_excel(result_path, index=False)

            update_job_record(
                job_id,
                status="completed",
                progress="Completed",
                current=total,
                total=total,
                completed=True,
                error=False,
                output_file=output_file,
                completed_at=utc_now_iso(),
            )
            log_event("job.completed", job_id=job_id, total=total, output_file=output_file)
        except Exception as exc:
            LOGGER.exception("job failed", exc_info=exc)
            update_job_record(
                job_id,
                status="failed",
                progress="Processing failed. Please try again.",
                completed=True,
                error=True,
                completed_at=utc_now_iso(),
            )
            log_event("job.failed", job_id=job_id, error=str(exc))


def render_index(error=None):
    return render_template(
        "index.html",
        error=error,
        template_filename=Path(current_app.config["TEMPLATE_DOWNLOAD_FILE"]).name,
        recent_jobs=list_recent_jobs(current_app.config["MAX_RECENT_JOBS"]),
    )


def create_app(config_class=None, overrides=None):
    config_class = config_class or get_config_class()

    app = Flask(
        __name__,
        template_folder=str(config_class.TEMPLATE_DIR),
        static_folder=str(config_class.STATIC_DIR),
    )
    app.config.from_object(config_class)

    if overrides:
        app.config.update(overrides)

    app.secret_key = os.urandom(24)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)
    app.config["ALLOWED_EXTENSIONS"] = {"xlsx", "xls", "csv"}
    app.config["NHTSA_API_BASE"] = "https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/"
    app.config["MAX_CONTENT_LENGTH"] = app.config["MAX_CONTENT_LENGTH"]

    ensure_directories(app)
    setup_logging(app)
    init_db(app)
    app.extensions["vin_decoder_http_session"] = build_requests_session()

    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=[app.config["DEFAULT_RATE_LIMIT"]],
        storage_uri=app.config["RATE_LIMIT_STORAGE_URI"],
    )

    @app.route("/", methods=["GET", "POST"])
    @limiter.limit(app.config["DEFAULT_RATE_LIMIT"])
    def index():
        run_cleanup_if_due()

        if request.method == "POST":
            uploaded_file = request.files.get("file")
            if not uploaded_file or not uploaded_file.filename:
                return render_index(error="Please choose a CSV or Excel file before submitting.")

            if not allowed_file(uploaded_file.filename):
                return render_index(error="Unsupported file type. Please upload a CSV, XLS, or XLSX file.")

            job_id = uuid.uuid4().hex
            original_name = secure_filename(uploaded_file.filename)
            stored_upload_name = f"source_{job_id}_{original_name}"
            upload_path = Path(app.config["UPLOAD_DIR"]) / stored_upload_name
            uploaded_file.save(upload_path)

            try:
                if upload_path.suffix.lower() in (".xlsx", ".xls"):
                    df = pd.read_excel(upload_path)
                else:
                    df = pd.read_csv(upload_path)
            except Exception:
                upload_path.unlink(missing_ok=True)
                log_event("upload.read_failed", filename=original_name)
                return render_index(error="We couldn't read that file. Please verify the file isn't corrupted and try again.")

            vin_column = find_vin_column(df)
            if not vin_column:
                upload_path.unlink(missing_ok=True)
                return render_index(error="No VIN column found. Make sure one column contains 17-character VIN values.")

            vin_series = df[vin_column].dropna().astype(str).str.upper().unique()
            if len(vin_series) == 0:
                upload_path.unlink(missing_ok=True)
                return render_index(error="No valid VIN values were found in the uploaded file.")

            create_job_record(job_id, original_name, stored_upload_name, len(vin_series))
            log_event("job.created", job_id=job_id, source_filename=original_name, total=len(vin_series))

            thread = threading.Thread(
                target=process_vins_in_background,
                args=(app, job_id, vin_series),
                daemon=True,
            )
            thread.start()
            return redirect(url_for("job_status_page", job_id=job_id))

        return render_index()

    @app.route("/jobs/<job_id>")
    def job_status_page(job_id: str):
        row = get_job_record(job_id)
        if not row:
            abort(404)
        return render_template(
            "status.html",
            job_id=job_id,
            poll_interval_ms=app.config["JOB_POLL_INTERVAL_MS"],
        )

    @app.route("/status")
    def status():
        return jsonify(serialize_job(get_latest_job_record()))

    @app.route("/status/<job_id>")
    def status_for_job(job_id: str):
        row = get_job_record(job_id)
        if not row:
            payload = default_status_payload()
            payload.update({"error": True, "progress": "Job not found."})
            return jsonify(payload), 404
        return jsonify(serialize_job(row))

    @app.route("/download/<job_id>")
    def download_job(job_id: str):
        row = get_job_record(job_id)
        if not row or not row["output_file"]:
            abort(404)

        return send_from_directory(
            app.config["UPLOAD_DIR"],
            row["output_file"],
            as_attachment=True,
            download_name=f"decoded_{job_id}.xlsx",
        )

    @app.route("/download-template")
    def download_template():
        return send_file(
            app.config["TEMPLATE_DOWNLOAD_FILE"],
            as_attachment=True,
            download_name=Path(app.config["TEMPLATE_DOWNLOAD_FILE"]).name,
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
