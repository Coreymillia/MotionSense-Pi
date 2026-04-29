import unittest
from zipfile import ZipFile
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
        self.assertIn("timer", payload)
        self.assertIn("motion_events", payload)
        self.assertIn("network_camera_url", payload["camera"])
        self.assertIn("burst_count", payload["camera"])
        self.assertIn("rotation_degrees", payload["camera"])
        self.assertIn("lighting", payload["camera"])
        self.assertIn("options", payload["camera"]["resolution"])

    def test_network_camera_endpoint_accepts_url(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        response = client.post("/api/camera/network", json={"url": "http://esp32-cam.local"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])

    def test_settings_endpoint_updates_poll_interval_and_burst_count(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        response = client.post(
            "/api/settings",
            json={
                "poll_interval_seconds": 5.5,
                "cooldown_seconds": 15,
                "motion_threshold": 12.5,
                "burst_count": 3,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"]["motion"]["poll_interval_seconds"], 5.5)
        self.assertEqual(payload["status"]["motion"]["cooldown_seconds"], 15.0)
        self.assertEqual(payload["status"]["motion"]["motion_threshold"], 12.5)
        self.assertEqual(payload["status"]["camera"]["burst_count"], 3)

    def test_settings_endpoint_updates_resolution(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        response = client.post(
            "/api/settings",
            json={"resolution": "3280x2464"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"]["camera"]["resolution"]["width"], 3280)
        self.assertEqual(payload["status"]["camera"]["resolution"]["height"], 2464)

    def test_settings_endpoint_updates_lighting_mode(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        response = client.post(
            "/api/settings",
            json={"lighting_mode": "fluorescent"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"]["camera"]["lighting"]["mode"], "fluorescent")

    def test_rotate_camera_endpoint_updates_snapshot(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        with patch(
            "app.monitor.MonitorService.set_camera_rotation_clockwise",
            return_value={
                "camera": {"rotation_degrees": 90},
                "snapshot": {"exists": True, "url": "/snapshot.jpg"},
            },
        ):
            response = client.post("/api/camera/rotate")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"]["camera"]["rotation_degrees"], 90)

    def test_timer_start_endpoint_updates_interval(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        response = client.post("/api/timer/start", json={"interval_seconds": 120})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"]["timer"]["interval_seconds"], 120)
        self.assertTrue(payload["status"]["timer"]["armed"])

        stop_response = client.post("/api/timer/stop")
        self.assertEqual(stop_response.status_code, 200)
        self.assertFalse(stop_response.get_json()["status"]["timer"]["armed"])

    def test_delete_events_endpoint_returns_updated_payload(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        with patch(
            "app.monitor.MonitorService.delete_events",
            return_value={
                "deleted_count": 1,
                "deleted_filenames": ["20260416T201700000000Z.jpg"],
                "events": [],
                "status": {"motion_events": []},
            },
        ):
            response = client.post(
                "/api/events/delete",
                json={"filenames": ["20260416T201700000000Z.jpg"]},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["deleted_count"], 1)

    def test_events_endpoint_returns_archived_events(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        with patch(
            "app.monitor.MonitorService.archived_events_payload",
            return_value=[{"event_id": "evt-1", "snapshot_url": "/events/evt-1.jpg"}],
        ):
            response = client.get("/api/events")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["events"][0]["event_id"], "evt-1")

    def test_events_download_endpoint_returns_zip_bundle(self):
        with TemporaryDirectory() as temp_dir:
            event_path = Path(temp_dir) / "20260416T201700000000Z.jpg"
            Image.new("RGB", (320, 240), color="purple").save(event_path, format="JPEG")

            app = create_app(start_detector=False)
            client = app.test_client()

            with patch("app.monitor.MonitorService.selected_event_paths", return_value=[event_path]):
                response = client.post(
                    "/api/events/download",
                    json={"filenames": [event_path.name]},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/zip")
        with ZipFile(BytesIO(response.data)) as archive:
            self.assertEqual(archive.namelist(), [event_path.name])

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

    def test_archive_page_renders_saved_event_downloads(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        archived_events = [
            {
                "event_id": "20260416T201700000000Z",
                "detected_at": "2026-04-16T20:17:00+00:00",
                "score": None,
                "snapshot_path": "/opt/motionsense-pi/data/events/20260416T201700000000Z.jpg",
                "snapshot_url": "/events/20260416T201700000000Z.jpg",
                "size_bytes": 1024,
            }
        ]

        with patch("app.monitor.MonitorService.archived_events_payload", return_value=archived_events):
            response = client.get("/archive")

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("Event Archive", page)
        self.assertIn("Download Selected", page)
        self.assertIn("Delete Selected", page)


if __name__ == "__main__":
    unittest.main()
