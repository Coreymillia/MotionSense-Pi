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
        self.cooldown_seconds = 10.0
        self.motion_threshold = 18.0

    def status_payload(self):
        return {
            "armed": True,
            "running": True,
            "event_count": 1,
            "poll_interval_seconds": self.poll_interval_seconds,
            "cooldown_seconds": self.cooldown_seconds,
            "motion_threshold": self.motion_threshold,
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

    def set_cooldown_seconds(self, value: float) -> None:
        self.cooldown_seconds = value

    def set_motion_threshold(self, value: float) -> None:
        self.motion_threshold = value


class FakeTimedCapture:
    def __init__(self) -> None:
        self.interval_seconds = 60
        self.armed = False

    def status_payload(self):
        return {
            "armed": self.armed,
            "running": self.armed,
            "interval_seconds": self.interval_seconds,
            "last_capture_at": None,
            "last_error": None,
            "capture_count": 0,
        }

    def start(self, interval_seconds: int | None = None) -> None:
        if interval_seconds is not None:
            self.interval_seconds = interval_seconds
        self.armed = True

    def stop(self) -> None:
        self.armed = False


class MonitorServiceTests(unittest.TestCase):
    def test_status_payload_reports_missing_snapshot(self):
        with TemporaryDirectory() as temp_dir:
            camera = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")
            monitor = MonitorService(
                camera=camera,
                sense_hat=FakeSenseHat(),
                motion_detector=FakeMotionDetector(),
                timed_capture=FakeTimedCapture(),
            )

            payload = monitor.status_payload()

            self.assertIn("camera", payload)
            self.assertFalse(payload["snapshot"]["exists"])
            self.assertTrue(payload["sense_hat"]["available"])
            self.assertTrue(payload["motion"]["armed"])
            self.assertFalse(payload["timer"]["armed"])
            self.assertEqual(payload["camera"]["burst_count"], 1)
            self.assertEqual(payload["camera"]["rotation_degrees"], 0)
            self.assertEqual(payload["camera"]["lighting"]["mode"], "auto")
            self.assertIn("options", payload["camera"]["resolution"])
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
        camera.rotation_degrees = Mock(return_value=0)
        camera.lighting_payload = Mock(
            return_value={"mode": "auto", "supported": True, "options": []}
        )
        camera.rotate_clockwise = Mock(return_value=90)
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
            timed_capture=FakeTimedCapture(),
        )

        payload = monitor.set_camera_source("usb-video1")

        camera.set_active_source.assert_called_once_with("usb-video1")
        camera.capture_snapshot.assert_called_once_with()
        self.assertTrue(payload["snapshot"]["exists"])
        self.assertEqual(payload["snapshot"]["modified_at"], "2026-04-15T21:26:38+00:00")
        self.assertEqual(sense_hat.statuses[-1], "capture-ok")

    def test_set_camera_rotation_refreshes_snapshot(self):
        camera = Mock()
        camera.rotate_clockwise = Mock(return_value=90)
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
        camera.selected_source_id = Mock(return_value="pi-camera")
        camera.selected_source_name = Mock(return_value="Pi Camera")
        camera.network_camera_url = Mock(return_value=None)
        camera.burst_count = Mock(return_value=1)
        camera.rotation_degrees = Mock(return_value=90)
        camera.lighting_payload = Mock(
            return_value={"mode": "auto", "supported": True, "options": []}
        )
        camera.active_capture_target = Mock(return_value="/usr/bin/rpicam-still")
        camera.list_sources = Mock(return_value=[])
        camera.resolution_payload = Mock(
            return_value={
                "width": 1280,
                "height": 720,
                "options": [{"width": 1280, "height": 720, "label": "1280 x 720"}],
            }
        )
        camera.width = 1280
        camera.height = 720

        sense_hat = FakeSenseHat()
        monitor = MonitorService(
            camera=camera,
            sense_hat=sense_hat,
            motion_detector=FakeMotionDetector(),
            timed_capture=FakeTimedCapture(),
        )

        payload = monitor.set_camera_rotation_clockwise()

        camera.rotate_clockwise.assert_called_once_with()
        camera.capture_snapshot.assert_called_once_with()
        self.assertEqual(payload["camera"]["rotation_degrees"], 90)
        self.assertEqual(sense_hat.statuses[-1], "capture-ok")

    def test_update_capture_settings_updates_motion_and_camera(self):
        camera = Mock()
        camera.set_burst_count = Mock()
        camera.burst_count = Mock(return_value=3)
        camera.rotation_degrees = Mock(return_value=0)
        camera.lighting_payload = Mock(
            return_value={"mode": "auto", "supported": True, "options": []}
        )
        camera.set_lighting_mode = Mock()
        camera.set_resolution = Mock()
        camera.resolution_payload = Mock(
            return_value={
                "width": 1280,
                "height": 720,
                "options": [{"width": 1280, "height": 720, "label": "1280 x 720"}],
            }
        )
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
            timed_capture=FakeTimedCapture(),
        )

        payload = monitor.update_capture_settings(poll_interval_seconds=5.0, burst_count=3)

        camera.set_burst_count.assert_called_once_with(3)
        self.assertEqual(payload["camera"]["burst_count"], 3)
        self.assertEqual(payload["motion"]["poll_interval_seconds"], 5.0)

    def test_update_capture_settings_updates_motion_controls(self):
        camera = Mock()
        camera.set_burst_count = Mock()
        camera.set_resolution = Mock()
        camera.burst_count = Mock(return_value=1)
        camera.rotation_degrees = Mock(return_value=0)
        camera.lighting_payload = Mock(
            return_value={"mode": "auto", "supported": True, "options": []}
        )
        camera.set_lighting_mode = Mock()
        camera.resolution_payload = Mock(
            return_value={
                "width": 1280,
                "height": 720,
                "options": [{"width": 1280, "height": 720, "label": "1280 x 720"}],
            }
        )
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
            timed_capture=FakeTimedCapture(),
        )

        payload = monitor.update_capture_settings(
            poll_interval_seconds=2.0,
            cooldown_seconds=15.0,
            motion_threshold=12.5,
        )

        self.assertEqual(payload["motion"]["poll_interval_seconds"], 2.0)
        self.assertEqual(payload["motion"]["cooldown_seconds"], 15.0)
        self.assertEqual(payload["motion"]["motion_threshold"], 12.5)

    def test_update_capture_settings_updates_resolution(self):
        camera = Mock()
        camera.set_burst_count = Mock()
        camera.set_resolution = Mock()
        camera.burst_count = Mock(return_value=1)
        camera.rotation_degrees = Mock(return_value=0)
        camera.lighting_payload = Mock(
            return_value={"mode": "auto", "supported": True, "options": []}
        )
        camera.set_lighting_mode = Mock()
        camera.resolution_payload = Mock(
            return_value={
                "width": 3280,
                "height": 2464,
                "options": [{"width": 3280, "height": 2464, "label": "3280 x 2464 (Max)"}],
            }
        )
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
        camera.width = 3280
        camera.height = 2464

        monitor = MonitorService(
            camera=camera,
            sense_hat=FakeSenseHat(),
            motion_detector=FakeMotionDetector(),
            timed_capture=FakeTimedCapture(),
        )

        payload = monitor.update_capture_settings(resolution=(3280, 2464))

        camera.set_resolution.assert_called_once_with(3280, 2464)
        self.assertEqual(payload["camera"]["resolution"]["width"], 3280)

    def test_update_capture_settings_updates_lighting_mode(self):
        camera = Mock()
        camera.set_burst_count = Mock()
        camera.set_resolution = Mock()
        camera.set_lighting_mode = Mock()
        camera.burst_count = Mock(return_value=1)
        camera.rotation_degrees = Mock(return_value=0)
        camera.lighting_payload = Mock(
            return_value={"mode": "fluorescent", "supported": True, "options": []}
        )
        camera.resolution_payload = Mock(
            return_value={
                "width": 1280,
                "height": 720,
                "options": [{"width": 1280, "height": 720, "label": "1280 x 720"}],
            }
        )
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

        monitor = MonitorService(
            camera=camera,
            sense_hat=FakeSenseHat(),
            motion_detector=FakeMotionDetector(),
            timed_capture=FakeTimedCapture(),
        )

        payload = monitor.update_capture_settings(lighting_mode="fluorescent")

        camera.set_lighting_mode.assert_called_once_with("fluorescent")
        self.assertEqual(payload["camera"]["lighting"]["mode"], "fluorescent")

    def test_archived_events_payload_passes_through_to_motion_detector(self):
        with TemporaryDirectory() as temp_dir:
            camera = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")
            monitor = MonitorService(
                camera=camera,
                sense_hat=FakeSenseHat(),
                motion_detector=FakeMotionDetector(),
                timed_capture=FakeTimedCapture(),
            )

            payload = monitor.archived_events_payload(limit=25)

            self.assertEqual(payload[0]["event_id"], "evt-archive")
            self.assertEqual(payload[0]["limit"], 25)

    def test_start_and_stop_timed_capture_updates_status(self):
        camera = Mock()
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
        camera.burst_count = Mock(return_value=1)
        camera.rotation_degrees = Mock(return_value=0)
        camera.lighting_payload = Mock(
            return_value={"mode": "auto", "supported": True, "options": []}
        )
        camera.active_capture_target = Mock(return_value="/usr/bin/rpicam-still")
        camera.list_sources = Mock(return_value=[])
        camera.width = 1280
        camera.height = 720

        timed_capture = FakeTimedCapture()
        monitor = MonitorService(
            camera=camera,
            sense_hat=FakeSenseHat(),
            motion_detector=FakeMotionDetector(),
            timed_capture=timed_capture,
        )

        started = monitor.start_timed_capture(120)
        self.assertTrue(started["timer"]["armed"])
        self.assertEqual(started["timer"]["interval_seconds"], 120)

        stopped = monitor.stop_timed_capture()
        self.assertFalse(stopped["timer"]["armed"])


if __name__ == "__main__":
    unittest.main()
