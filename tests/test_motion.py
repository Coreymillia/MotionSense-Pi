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
        self._burst_count = 1
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

    def burst_count(self) -> int:
        return self._burst_count


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

    def test_archived_events_payload_lists_saved_images(self):
        with TemporaryDirectory() as temp_dir:
            event_dir = Path(temp_dir) / "events"
            event_dir.mkdir(parents=True, exist_ok=True)
            detector = MotionDetector(
                camera=FakeCamera(Path(temp_dir) / "latest.jpg"),
                sense_hat=FakeSenseHat(),
                event_dir=event_dir,
            )

            Image.new("RGB", (320, 240), color="red").save(
                event_dir / "20260416T201500000000Z.jpg", format="JPEG"
            )
            Image.new("RGB", (320, 240), color="blue").save(
                event_dir / "20260416T201700000000Z.jpg", format="JPEG"
            )
            Image.new("RGB", (320, 240), color="green").save(
                event_dir / "_probe.jpg", format="JPEG"
            )

            events = detector.archived_events_payload()

            self.assertEqual(
                [event["event_id"] for event in events],
                ["20260416T201700000000Z", "20260416T201500000000Z"],
            )
            self.assertEqual(events[0]["snapshot_url"], "/events/20260416T201700000000Z.jpg")
            self.assertEqual(events[0]["source"], "motion")
            self.assertIsNone(events[0]["score"])

    def test_record_event_captures_burst_count_images(self):
        with TemporaryDirectory() as temp_dir:
            camera = FakeCamera(Path(temp_dir) / "latest.jpg")
            camera._burst_count = 3
            detector = MotionDetector(
                camera=camera,
                sense_hat=FakeSenseHat(),
                event_dir=Path(temp_dir) / "events",
            )

            detector._record_event(score=22.0, capture_started=time.monotonic())

            events = detector.archived_events_payload()
            self.assertEqual(len(events), 3)

    def test_record_external_capture_saves_timer_event(self):
        with TemporaryDirectory() as temp_dir:
            detector = MotionDetector(
                camera=FakeCamera(Path(temp_dir) / "latest.jpg"),
                sense_hat=FakeSenseHat(),
                event_dir=Path(temp_dir) / "events",
            )

            events = detector.record_external_capture(source="timer")

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].source, "timer")
            archived = detector.archived_events_payload()
            self.assertEqual(archived[0]["source"], "timer")

    def test_poll_interval_setting_persists(self):
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "motion_config.json"
            detector = MotionDetector(
                camera=FakeCamera(Path(temp_dir) / "latest.jpg"),
                sense_hat=FakeSenseHat(),
                event_dir=Path(temp_dir) / "events",
                config_path=config_path,
            )

            detector.set_poll_interval_seconds(6.5)

            reloaded = MotionDetector(
                camera=FakeCamera(Path(temp_dir) / "latest.jpg"),
                sense_hat=FakeSenseHat(),
                event_dir=Path(temp_dir) / "events",
                config_path=config_path,
            )
            self.assertEqual(reloaded.poll_interval_seconds, 6.5)

    def test_delete_events_removes_selected_files(self):
        with TemporaryDirectory() as temp_dir:
            event_dir = Path(temp_dir) / "events"
            event_dir.mkdir(parents=True, exist_ok=True)
            first_event = event_dir / "20260416T201500000000Z.jpg"
            second_event = event_dir / "20260416T201700000000Z.jpg"
            Image.new("RGB", (320, 240), color="red").save(first_event, format="JPEG")
            Image.new("RGB", (320, 240), color="blue").save(second_event, format="JPEG")

            detector = MotionDetector(
                camera=FakeCamera(Path(temp_dir) / "latest.jpg"),
                sense_hat=FakeSenseHat(),
                event_dir=event_dir,
            )

            deleted = detector.delete_events([second_event.name])

            self.assertEqual(deleted, [second_event.name])
            self.assertFalse(second_event.exists())
            self.assertTrue(first_event.exists())


if __name__ == "__main__":
    unittest.main()
