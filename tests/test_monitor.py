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
    def __init__(self) -> None:
        self.poll_interval_seconds = 3.0

    def status_payload(self):
        return {
            "armed": True,
            "running": True,
            "event_count": 1,
            "poll_interval_seconds": self.poll_interval_seconds,
            "cooldown_seconds": 10.0,
            "motion_threshold": 18.0,
            "last_score": None,
            "last_probe_at": None,
            "last_motion_at": None,
            "last_error": None,
        }

    def events_payload(self):
        return [{"event_id": "evt-1", "score": 42.0}]

    def archived_events_payload(self, limit=None):
        return [{"event_id": "evt-archive", "score": None, "limit": limit}]

    def set_poll_interval_seconds(self, value: float) -> None:
        self.poll_interval_seconds = value


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
            self.assertEqual(payload["camera"]["burst_count"], 1)
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
        camera.capture_snapshot_burst = Mock(return_value=[camera.capture_snapshot.return_value])
        camera.snapshot_details = Mock(return_value=camera.capture_snapshot.return_value)
        camera.active_source = Mock(return_value=None)
        camera.is_available = Mock(return_value=True)
        camera.selected_source_id = Mock(return_value="usb-video1")
        camera.selected_source_name = Mock(return_value="USB Camera (video1)")
        camera.network_camera_url = Mock(return_value=None)
        camera.burst_count = Mock(return_value=1)
        camera.set_burst_count = Mock()
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

    def test_update_capture_settings_updates_motion_and_camera(self):
        camera = Mock()
        camera.set_burst_count = Mock()
        camera.burst_count = Mock(return_value=3)
        camera.snapshot_details = Mock(
            return_value=SnapshotDetails(
                exists=False,
                path="/tmp/latest.jpg",
                modified_at=None,
                size_bytes=None,
            )
        )
        camera.active_source = Mock(return_value=None)
        camera.is_available = Mock(return_value=True)
        camera.selected_source_id = Mock(return_value="pi-camera")
        camera.selected_source_name = Mock(return_value="Pi Camera")
        camera.network_camera_url = Mock(return_value=None)
        camera.active_capture_target = Mock(return_value="/usr/bin/rpicam-still")
        camera.list_sources = Mock(return_value=[])
        camera.width = 1280
        camera.height = 720

        motion_detector = FakeMotionDetector()
        monitor = MonitorService(
            camera=camera,
            sense_hat=FakeSenseHat(),
            motion_detector=motion_detector,
        )

        payload = monitor.update_capture_settings(poll_interval_seconds=5.0, burst_count=3)

        camera.set_burst_count.assert_called_once_with(3)
        self.assertEqual(payload["camera"]["burst_count"], 3)
        self.assertEqual(payload["motion"]["poll_interval_seconds"], 5.0)

    def test_archived_events_payload_passes_through_to_motion_detector(self):
        with TemporaryDirectory() as temp_dir:
            camera = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")
            monitor = MonitorService(
                camera=camera,
                sense_hat=FakeSenseHat(),
                motion_detector=FakeMotionDetector(),
            )

            payload = monitor.archived_events_payload(limit=25)

            self.assertEqual(payload[0]["event_id"], "evt-archive")
            self.assertEqual(payload[0]["limit"], 25)


if __name__ == "__main__":
    unittest.main()
