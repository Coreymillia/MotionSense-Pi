from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from PIL import Image

from app.camera import SnapshotDetails
from app.stormwatch import StormwatchDetector


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
        self._burst_count = 1

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

    def capture_probe(
        self,
        output_path: Path,
        width: int = 320,
        height: int = 240,
        quality: int = 35,
    ):
        color = "black" if not output_path.exists() else "white"
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


class StormwatchDetectorTests(unittest.TestCase):
    def test_stormwatch_records_event_with_stormwatch_source(self):
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            detector = StormwatchDetector(
                camera=FakeCamera(temp_path / "latest.jpg"),
                sense_hat=FakeSenseHat(),
                event_dir=temp_path / "events",
                cooldown_seconds=1,
                poll_interval_seconds=1,
                score_trigger=1.0,
                hot_pixel_threshold=1,
                buffer_size=1,
                post_capture_frames=0,
            )

            black_probe = temp_path / "black.jpg"
            white_probe = temp_path / "white.jpg"
            Image.new("RGB", (64, 48), color="black").save(black_probe, format="JPEG")
            Image.new("RGB", (64, 48), color="white").save(white_probe, format="JPEG")

            self.assertEqual(detector._capture_lightning_score(black_probe), 0.0)
            score = detector._capture_lightning_score(white_probe)
            self.assertGreater(score, 1.0)

            detector._record_event(score, time.monotonic())

            events = detector.archived_events_payload()
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["source"], "stormwatch")
            self.assertEqual(detector.status_payload()["score_trigger"], 1.0)
            self.assertEqual(detector.status_payload()["buffer_size"], 1)

    def test_stormwatch_settings_persist(self):
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = temp_path / "stormwatch_config.json"
            detector = StormwatchDetector(
                camera=FakeCamera(temp_path / "latest.jpg"),
                sense_hat=FakeSenseHat(),
                event_dir=temp_path / "events",
                config_path=config_path,
            )

            detector.set_score_trigger(8.5)
            detector.set_buffer_size(9)
            detector.set_hot_pixel_threshold(42)
            detector.set_post_capture_frames(3)

            reloaded = StormwatchDetector(
                camera=FakeCamera(temp_path / "latest.jpg"),
                sense_hat=FakeSenseHat(),
                event_dir=temp_path / "events",
                config_path=config_path,
            )

            self.assertEqual(reloaded.motion_threshold, 8.5)
            self.assertEqual(reloaded.status_payload()["buffer_size"], 9)
            self.assertEqual(reloaded.status_payload()["hot_pixel_threshold"], 42)
            self.assertEqual(reloaded.status_payload()["post_capture_frames"], 3)


if __name__ == "__main__":
    unittest.main()
