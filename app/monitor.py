from __future__ import annotations

from datetime import datetime, timezone
import socket

from app.camera import CameraService, SnapshotDetails
from app.motion import MotionDetector
from app.sensehat import SenseHatService


class MonitorService:
    def __init__(
        self,
        camera: CameraService,
        sense_hat: SenseHatService,
        motion_detector: MotionDetector | None = None,
    ) -> None:
        self.camera = camera
        self.sense_hat = sense_hat
        self.motion_detector = motion_detector

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
                "target": self.camera.active_capture_target(),
                "sources": self.camera.list_sources(),
                "resolution": {
                    "width": self.camera.width,
                    "height": self.camera.height,
                },
            },
            "snapshot": self._snapshot_payload(snapshot),
            "sense_hat": self.sense_hat.read(),
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
        snapshot = self.camera.capture_snapshot()
        self.sense_hat.show_status("capture-ok")

        return {
            "ok": True,
            "snapshot": self._snapshot_payload(snapshot),
            "status": self.status_payload(),
        }

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
        self.sense_hat.show_status("idle")
        return self.status_payload()
