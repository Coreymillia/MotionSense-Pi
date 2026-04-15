from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.camera import CameraService
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


if __name__ == "__main__":
    unittest.main()
