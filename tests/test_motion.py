from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from PIL import Image

from app.camera import SnapshotDetails
from app.motion import MotionDetector


class FakeSenseHat:
    def __init__(self) -> None:
        self.statuses: list[str] = []

    def show_status(self, status: str) -> None:
        self.statuses.append(status)


class FakeCamera:
    def __init__(self, snapshot_path: Path) -> None:
        self.snapshot_path = snapshot_path
        self.width = 1280
        self.height = 720
        self.executable = "fake-rpicam-still"
        self._probe_colors = ["black", "white", "white"]

    def is_available(self) -> bool:
        return True

    def details_for_path(self, path: Path) -> SnapshotDetails:
        stat_result = path.stat()
        return SnapshotDetails(
            exists=True,
            path=str(path),
            modified_at=datetime.fromtimestamp(
                stat_result.st_mtime, tz=timezone.utc
            ).isoformat(),
            size_bytes=stat_result.st_size,
        )

    def capture_probe(self, output_path: Path, width: int = 320, height: int = 240, quality: int = 35):
        color = self._probe_colors.pop(0) if self._probe_colors else "white"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (width, height), color=color).save(output_path, format="JPEG")
        return self.details_for_path(output_path)

    def capture_snapshot(self) -> SnapshotDetails:
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (self.width, self.height), color="white").save(
            self.snapshot_path, format="JPEG"
        )
        return self.details_for_path(self.snapshot_path)


class MotionDetectorTests(unittest.TestCase):
    def test_motion_detector_records_event(self):
        with TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "latest.jpg"
            detector = MotionDetector(
                camera=FakeCamera(snapshot_path),
                sense_hat=FakeSenseHat(),
                event_dir=Path(temp_dir) / "events",
                poll_interval_seconds=0.1,
                cooldown_seconds=0.1,
                motion_threshold=5.0,
                max_events=4,
            )

            detector.start()
            deadline = time.time() + 2
            while time.time() < deadline:
                if detector.events_payload():
                    break
                time.sleep(0.05)
            detector.stop()

            events = detector.events_payload()
            self.assertEqual(len(events), 1)
            self.assertGreater(events[0]["score"], 5.0)


if __name__ == "__main__":
    unittest.main()
