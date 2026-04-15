from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from app.camera import CameraService
from app.camera import SnapshotDetails
from app.monitor import MonitorService


class FakeSenseHat:
    def __init__(self) -> None:
        self.statuses: list[str] = []

    def read(self):
        return {
            "available": True,
            "temperature_f": 70.2,
            "humidity_pct": 48.5,
            "pressure_inhg": 29.81,
            "orientation": {"pitch": 1.0, "roll": 2.0, "yaw": 3.0},
        }

    def show_status(self, status: str) -> None:
        self.statuses.append(status)


class FakeMotionDetector:
    def status_payload(self):
        return {"armed": True, "running": True, "event_count": 1}

    def events_payload(self):
        return [{"event_id": "evt-1", "score": 42.0}]


class MonitorServiceTests(unittest.TestCase):
    def test_status_payload_reports_missing_snapshot(self):
        with TemporaryDirectory() as temp_dir:
            camera = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")
            monitor = MonitorService(
                camera=camera,
                sense_hat=FakeSenseHat(),
                motion_detector=FakeMotionDetector(),
            )

            payload = monitor.status_payload()

            self.assertIn("camera", payload)
            self.assertFalse(payload["snapshot"]["exists"])
            self.assertTrue(payload["sense_hat"]["available"])
            self.assertTrue(payload["motion"]["armed"])
            self.assertEqual(len(payload["motion_events"]), 1)

    def test_set_camera_source_refreshes_snapshot(self):
        camera = Mock()
        camera.set_active_source = Mock()
        camera.capture_snapshot = Mock(
            return_value=SnapshotDetails(
                exists=True,
                path="/tmp/latest.jpg",
                modified_at="2026-04-15T21:26:38+00:00",
                size_bytes=28960,
            )
        )
        camera.snapshot_details = Mock(return_value=camera.capture_snapshot.return_value)
        camera.active_source = Mock(return_value=None)
        camera.is_available = Mock(return_value=True)
        camera.selected_source_id = Mock(return_value="usb-video1")
        camera.selected_source_name = Mock(return_value="USB Camera (video1)")
        camera.network_camera_url = Mock(return_value=None)
        camera.active_capture_target = Mock(return_value="/dev/video1")
        camera.list_sources = Mock(return_value=[])
        camera.width = 1280
        camera.height = 720

        sense_hat = FakeSenseHat()
        monitor = MonitorService(
            camera=camera,
            sense_hat=sense_hat,
            motion_detector=FakeMotionDetector(),
        )

        payload = monitor.set_camera_source("usb-video1")

        camera.set_active_source.assert_called_once_with("usb-video1")
        camera.capture_snapshot.assert_called_once_with()
        self.assertTrue(payload["snapshot"]["exists"])
        self.assertEqual(payload["snapshot"]["modified_at"], "2026-04-15T21:26:38+00:00")
        self.assertEqual(sense_hat.statuses[-1], "capture-ok")


if __name__ == "__main__":
    unittest.main()
