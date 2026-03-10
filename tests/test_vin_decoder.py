import io
import os
import sys
import tempfile
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import TestingConfig
from vin_decoder import create_app


class VinDecoderTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.upload_dir = os.path.join(self.temp_dir.name, "uploads")
        self.data_dir = os.path.join(self.temp_dir.name, "data")
        self.log_dir = os.path.join(self.temp_dir.name, "logs")
        os.makedirs(self.upload_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)

        self.db_path = os.path.join(self.data_dir, "test.sqlite3")
        self.app = create_app(
            config_class=TestingConfig,
            overrides={
                "TESTING": True,
                "UPLOAD_DIR": self.upload_dir,
                "DATA_DIR": self.data_dir,
                "LOG_DIR": self.log_dir,
                "DB_PATH": self.db_path,
                "MAX_RECENT_JOBS": 5,
            },
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_download_template_route(self):
        response = self.client.get("/download-template")
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_status_fallback_shape(self):
        response = self.client.get("/status")
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertIn("progress", payload)
        self.assertIn("error", payload)
        self.assertIn("completed", payload)

    @mock.patch("vin_decoder.threading.Thread")
    def test_upload_creates_job_and_redirects(self, thread_cls):
        thread_cls.return_value.start.return_value = None

        csv_bytes = io.BytesIO(b"VIN,Label\n1HGCM82633A004352,Example\n")
        response = self.client.post(
            "/",
            data={"file": (csv_bytes, "sample.csv")},
            content_type="multipart/form-data",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/jobs/", response.headers["Location"])

    def test_invalid_download_job_returns_404(self):
        response = self.client.get("/download/not-a-real-job")
        self.assertEqual(response.status_code, 404)

    def test_status_for_unknown_job_returns_404(self):
        response = self.client.get("/status/does-not-exist")
        self.assertEqual(response.status_code, 404)
        payload = response.get_json()
        self.assertTrue(payload["error"])


if __name__ == "__main__":
    unittest.main()
