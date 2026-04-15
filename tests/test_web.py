import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image

from app.camera import CameraService
from app.camera import SnapshotDetails
from app.web import create_app


class WebTests(unittest.TestCase):
    def test_status_endpoint_returns_dashboard_payload(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        response = client.get("/api/status")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("camera", payload)
        self.assertIn("sense_hat", payload)
        self.assertIn("snapshot", payload)
        self.assertIn("motion", payload)
        self.assertIn("motion_events", payload)
        self.assertIn("network_camera_url", payload["camera"])

    def test_network_camera_endpoint_accepts_url(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        response = client.post("/api/camera/network", json={"url": "http://esp32-cam.local"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])

    def test_snapshot_endpoint_can_return_scaled_preview(self):
        with TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "latest.jpg"
            image = Image.new("RGB", (1280, 720), color="navy")
            image.save(snapshot_path, format="JPEG", quality=90)

            app = create_app(start_detector=False)

            with patch.object(CameraService, "latest_snapshot_path", return_value=snapshot_path):
                client = app.test_client()
                response = client.get("/snapshot.jpg?max_w=304&max_h=172&quality=60")

            self.assertEqual(response.status_code, 200)
            with Image.open(BytesIO(response.data)) as preview:
                self.assertLessEqual(preview.width, 304)
                self.assertLessEqual(preview.height, 172)

    def test_snapshot_endpoint_can_capture_live_image(self):
        with TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "latest.jpg"
            image = Image.new("RGB", (640, 480), color="green")
            image.save(snapshot_path, format="JPEG", quality=85)

            app = create_app(start_detector=False)

            with patch.object(
                CameraService,
                "capture_snapshot",
                return_value=SnapshotDetails(
                    exists=True,
                    path=str(snapshot_path),
                    modified_at="2026-04-15T22:30:00+00:00",
                    size_bytes=snapshot_path.stat().st_size,
                ),
            ) as capture_snapshot:
                client = app.test_client()
                response = client.get("/snapshot.jpg?live=1&max_w=304&max_h=172&quality=60")

            self.assertEqual(response.status_code, 200)
            capture_snapshot.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
