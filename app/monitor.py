from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import socket

from app.camera import CameraService, SnapshotDetails
from app.motion import MotionDetector
from app.sensehat import SenseHatService
from app.timed_capture import TimedCaptureService


class MonitorService:
    def __init__(
        self,
        camera: CameraService,
        sense_hat: SenseHatService,
        motion_detector: MotionDetector | None = None,
        timed_capture: TimedCaptureService | None = None,
    ) -> None:
        self.camera = camera
        self.sense_hat = sense_hat
        self.motion_detector = motion_detector
        self.timed_capture = timed_capture

    def _snapshot_payload(self, snapshot: SnapshotDetails) -> dict[str, object]:
        return {
            "exists": snapshot.exists,
            "path": snapshot.path,
            "modified_at": snapshot.modified_at,
            "size_bytes": snapshot.size_bytes,
            "url": "/snapshot.jpg" if snapshot.exists else None,
        }

    def status_payload(self) -> dict[str, object]:
        snapshot = self.camera.snapshot_details()
        active_source = self.camera.active_source()

        return {
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "host": socket.gethostname(),
            "camera": {
                "available": self.camera.is_available(),
                "active_source_id": self.camera.selected_source_id(),
                "active_source_name": self.camera.selected_source_name(),
                "backend": active_source.backend if active_source is not None else None,
                "network_camera_url": self.camera.network_camera_url(),
                "burst_count": self.camera.burst_count(),
                "target": self.camera.active_capture_target(),
                "sources": self.camera.list_sources(),
                "resolution": self.camera.resolution_payload(),
            },
            "snapshot": self._snapshot_payload(snapshot),
            "sense_hat": self.sense_hat.read(),
            "timer": (
                self.timed_capture.status_payload()
                if self.timed_capture is not None
                else None
            ),
            "motion": (
                self.motion_detector.status_payload()
                if self.motion_detector is not None
                else None
            ),
            "motion_events": (
                self.motion_detector.events_payload()
                if self.motion_detector is not None
                else []
            ),
        }

    def capture_snapshot(self) -> dict[str, object]:
        snapshots = self.camera.capture_snapshot_burst()
        snapshot = snapshots[-1]
        self.sense_hat.show_status("capture-ok")

        return {
            "ok": True,
            "captured_count": len(snapshots),
            "snapshot": self._snapshot_payload(snapshot),
            "status": self.status_payload(),
        }

    def archived_events_payload(self, limit: int | None = None) -> list[dict[str, object]]:
        if self.motion_detector is None:
            return []
        return self.motion_detector.archived_events_payload(limit=limit)

    def start_motion_detection(self) -> dict[str, object]:
        if self.motion_detector is None:
            raise RuntimeError("Motion detection is not configured.")
        self.motion_detector.start()
        return self.status_payload()

    def stop_motion_detection(self) -> dict[str, object]:
        if self.motion_detector is None:
            raise RuntimeError("Motion detection is not configured.")
        self.motion_detector.stop()
        return self.status_payload()

    def set_camera_source(self, source_id: str) -> dict[str, object]:
        self.camera.set_active_source(source_id)
        snapshot = self.camera.capture_snapshot()
        self.sense_hat.show_status("capture-ok")
        payload = self.status_payload()
        payload["snapshot"] = self._snapshot_payload(snapshot)
        return payload

    def set_network_camera_url(self, url: str) -> dict[str, object]:
        self.camera.set_network_camera_url(url)
        self.sense_hat.show_status("idle")
        return self.status_payload()

    def update_capture_settings(
        self,
        poll_interval_seconds: float | None = None,
        burst_count: int | None = None,
        resolution: tuple[int, int] | None = None,
        cooldown_seconds: float | None = None,
        motion_threshold: float | None = None,
    ) -> dict[str, object]:
        if (
            poll_interval_seconds is None
            and burst_count is None
            and resolution is None
            and cooldown_seconds is None
            and motion_threshold is None
        ):
            raise RuntimeError("At least one setting is required.")

        if (
            poll_interval_seconds is not None
            or cooldown_seconds is not None
            or motion_threshold is not None
        ):
            if self.motion_detector is None:
                raise RuntimeError("Motion detection is not configured.")
            if poll_interval_seconds is not None:
                self.motion_detector.set_poll_interval_seconds(poll_interval_seconds)
            if cooldown_seconds is not None:
                self.motion_detector.set_cooldown_seconds(cooldown_seconds)
            if motion_threshold is not None:
                self.motion_detector.set_motion_threshold(motion_threshold)

        if burst_count is not None:
            self.camera.set_burst_count(burst_count)

        if resolution is not None:
            self.camera.set_resolution(*resolution)

        return self.status_payload()

    def start_timed_capture(self, interval_seconds: int) -> dict[str, object]:
        if self.timed_capture is None:
            raise RuntimeError("Timed capture is not configured.")
        self.timed_capture.start(interval_seconds=interval_seconds)
        return self.status_payload()

    def stop_timed_capture(self) -> dict[str, object]:
        if self.timed_capture is None:
            raise RuntimeError("Timed capture is not configured.")
        self.timed_capture.stop()
        return self.status_payload()

    def delete_events(self, filenames: list[str]) -> dict[str, object]:
        if self.motion_detector is None:
            raise RuntimeError("Motion detection is not configured.")

        deleted_filenames = self.motion_detector.delete_events(filenames)
        return {
            "deleted_count": len(deleted_filenames),
            "deleted_filenames": deleted_filenames,
            "events": self.archived_events_payload(),
            "status": self.status_payload(),
        }

    def selected_event_paths(self, filenames: list[str]) -> list[Path]:
        if self.motion_detector is None:
            raise RuntimeError("Motion detection is not configured.")
        return self.motion_detector.selected_event_paths(filenames)
