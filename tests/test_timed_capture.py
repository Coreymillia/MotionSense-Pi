from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

from app.camera import SnapshotDetails
from app.timed_capture import TimedCaptureService


class FakeSenseHat:
    def __init__(self) -> None:
        self.statuses: list[str] = []

    def show_status(self, status: str) -> None:
        self.statuses.append(status)


class FakeEvent:
    def __init__(self, detected_at: str, source: str) -> None:
        self.detected_at = detected_at
        self.source = source


class FakeCamera:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.snapshot_path = root / "latest.jpg"
        self._probe_colors = ["black", "white"]

    def is_available(self) -> bool:
        return True

    def capture_probe(
        self,
        output_path: Path,
        width: int = 320,
        height: int = 240,
        quality: int = 35,
    ) -> SnapshotDetails:
        color = self._probe_colors.pop(0) if self._probe_colors else "white"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (width, height), color=color).save(output_path, format="JPEG")
        stat_result = output_path.stat()
        return SnapshotDetails(
            exists=True,
            path=str(output_path),
            modified_at=datetime.fromtimestamp(
                stat_result.st_mtime, tz=timezone.utc
            ).isoformat(),
            size_bytes=stat_result.st_size,
        )


class FakeMotionDetector:
    def __init__(self, root: Path) -> None:
        self.camera = FakeCamera(root)
        self.event_dir = root / "events"
        self.event_dir.mkdir(parents=True, exist_ok=True)
        self.poll_interval_seconds = 0.01
        self.motion_threshold = 5.0
        self.recorded_sources: list[str] = []
        self.armed = False
        self._motion_markers = [
            (0, None),
            (1, "2026-05-02T02:00:05+00:00"),
        ]
        self.last_score = 22.0

    def record_external_capture(self, source: str = "timer") -> list[FakeEvent]:
        self.recorded_sources.append(source)
        return [FakeEvent("2026-05-02T02:00:00+00:00", source)]

    def motion_marker(self) -> tuple[int, str | None]:
        if len(self._motion_markers) > 1:
            return self._motion_markers.pop(0)
        return self._motion_markers[0]

    def status_payload(self) -> dict[str, object]:
        epoch, detected_at = self._motion_markers[0]
        return {
            "armed": self.armed,
            "running": self.armed,
            "poll_interval_seconds": self.poll_interval_seconds,
            "cooldown_seconds": 10.0,
            "motion_threshold": self.motion_threshold,
            "last_score": self.last_score,
            "last_probe_at": None,
            "last_motion_at": detected_at,
            "last_error": None,
            "event_count": epoch,
        }


class TimedCaptureServiceTests(unittest.TestCase):
    def test_combo_settings_persist(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "timer_config.json"
            motion_detector = FakeMotionDetector(root)
            service = TimedCaptureService(
                motion_detector=motion_detector,
                sense_hat=FakeSenseHat(),
                config_path=config_path,
            )

            service.set_mode("combo")
            service.set_interval_seconds(7)
            service.set_duration_seconds(60)

            reloaded = TimedCaptureService(
                motion_detector=FakeMotionDetector(root),
                sense_hat=FakeSenseHat(),
                config_path=config_path,
            )
            payload = reloaded.status_payload()
            self.assertEqual(payload["mode"], "combo")
            self.assertEqual(payload["interval_seconds"], 7)
            self.assertEqual(payload["duration_seconds"], 60)

    def test_combo_mode_rejects_interval_below_minimum(self):
        with TemporaryDirectory() as temp_dir:
            service = TimedCaptureService(
                motion_detector=FakeMotionDetector(Path(temp_dir)),
                sense_hat=FakeSenseHat(),
            )

            with self.assertRaises(RuntimeError):
                service.start(interval_seconds=6, mode="combo", duration_seconds=60)

    def test_wait_for_motion_trigger_detects_motion(self):
        with TemporaryDirectory() as temp_dir:
            service = TimedCaptureService(
                motion_detector=FakeMotionDetector(Path(temp_dir)),
                sense_hat=FakeSenseHat(),
            )

            triggered = service._wait_for_motion_trigger()

            self.assertTrue(triggered)
            payload = service.status_payload()
            self.assertFalse(payload["waiting_for_motion"])
            self.assertIsNotNone(payload["last_motion_at"])
            self.assertGreaterEqual(payload["last_motion_score"], 5.0)

    def test_wait_for_motion_trigger_uses_armed_motion_detector(self):
        with TemporaryDirectory() as temp_dir:
            motion_detector = FakeMotionDetector(Path(temp_dir))
            motion_detector.armed = True
            service = TimedCaptureService(
                motion_detector=motion_detector,
                sense_hat=FakeSenseHat(),
            )

            triggered = service._wait_for_motion_trigger()

            self.assertTrue(triggered)
            payload = service.status_payload()
            self.assertEqual(payload["last_motion_at"], "2026-05-02T02:00:05+00:00")
            self.assertEqual(payload["last_motion_score"], 22.0)

    def test_combo_mode_captures_after_trigger(self):
        with TemporaryDirectory() as temp_dir:
            motion_detector = FakeMotionDetector(Path(temp_dir))
            service = TimedCaptureService(
                motion_detector=motion_detector,
                sense_hat=FakeSenseHat(),
                interval_seconds=7,
                duration_seconds=7,
            )

            with patch.object(service, "_wait_for_motion_trigger", return_value=True), patch(
                "app.timed_capture.time.monotonic",
                side_effect=[0.0, 0.0, 0.0, 7.1],
            ):
                service._run_combo_mode()

            self.assertEqual(motion_detector.recorded_sources, ["combo"])
            self.assertEqual(service.status_payload()["capture_count"], 1)


if __name__ == "__main__":
    unittest.main()
