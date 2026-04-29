from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Event, Lock, Thread
import shutil
import time
from typing import Any

from PIL import Image, ImageChops, ImageStat

from app.camera import CameraService
from app.sensehat import SenseHatService


@dataclass(frozen=True)
class MotionEventRecord:
    event_id: str
    detected_at: str
    source: str
    score: float | None
    snapshot_path: str
    snapshot_url: str
    size_bytes: int | None


class MotionDetector:
    def __init__(
        self,
        camera: CameraService,
        sense_hat: SenseHatService,
        event_dir: Path,
        config_path: Path | None = None,
        poll_interval_seconds: float = 3.0,
        cooldown_seconds: float = 10.0,
        motion_threshold: float = 18.0,
        max_events: int = 12,
    ) -> None:
        self.camera = camera
        self.sense_hat = sense_hat
        self.event_dir = event_dir
        self.config_path = config_path
        self.poll_interval_seconds = poll_interval_seconds
        self.cooldown_seconds = cooldown_seconds
        self.motion_threshold = motion_threshold
        self.max_events = max_events

        self.event_dir.mkdir(parents=True, exist_ok=True)

        self._events: deque[MotionEventRecord] = deque(maxlen=max_events)
        self._lock = Lock()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._armed = False
        self._previous_frame: Image.Image | None = None
        self._last_probe_at: str | None = None
        self._last_motion_at: str | None = None
        self._last_error: str | None = None
        self._last_score: float | None = None
        self._last_capture_monotonic = 0.0
        self._probe_path = self.event_dir / "_probe.jpg"
        self._load_config()

    @staticmethod
    def _normalize_poll_interval(value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RuntimeError("Poll interval must be a number between 0.5 and 30 seconds.")
        normalized = float(value)
        if normalized < 0.5 or normalized > 30.0:
            raise RuntimeError("Poll interval must be between 0.5 and 30 seconds.")
        return normalized

    @staticmethod
    def _normalize_cooldown_seconds(value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RuntimeError("Cooldown must be a number between 1 and 300 seconds.")
        normalized = float(value)
        if normalized < 1.0 or normalized > 300.0:
            raise RuntimeError("Cooldown must be between 1 and 300 seconds.")
        return normalized

    @staticmethod
    def _normalize_motion_threshold(value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RuntimeError("Threshold must be a number between 1 and 255.")
        normalized = float(value)
        if normalized < 1.0 or normalized > 255.0:
            raise RuntimeError("Threshold must be between 1 and 255.")
        return normalized

    def _load_config(self) -> None:
        if self.config_path is None or not self.config_path.exists():
            return

        try:
            config = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        try:
            self.poll_interval_seconds = self._normalize_poll_interval(
                config.get("poll_interval_seconds", self.poll_interval_seconds)
            )
        except RuntimeError:
            return
        try:
            self.cooldown_seconds = self._normalize_cooldown_seconds(
                config.get("cooldown_seconds", self.cooldown_seconds)
            )
            self.motion_threshold = self._normalize_motion_threshold(
                config.get("motion_threshold", self.motion_threshold)
            )
        except RuntimeError:
            return

    def _save_config(self) -> None:
        if self.config_path is None:
            return
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "poll_interval_seconds": self.poll_interval_seconds,
            "cooldown_seconds": self.cooldown_seconds,
            "motion_threshold": self.motion_threshold,
        }
        self.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def set_poll_interval_seconds(self, value: float) -> None:
        normalized = self._normalize_poll_interval(value)
        with self._lock:
            self.poll_interval_seconds = normalized
        self._save_config()

    def set_cooldown_seconds(self, value: float) -> None:
        normalized = self._normalize_cooldown_seconds(value)
        with self._lock:
            self.cooldown_seconds = normalized
        self._save_config()

    def set_motion_threshold(self, value: float) -> None:
        normalized = self._normalize_motion_threshold(value)
        with self._lock:
            self.motion_threshold = normalized
        self._save_config()

    def start(self) -> None:
        with self._lock:
            if self._armed and self._thread is not None and self._thread.is_alive():
                return
            self._armed = True
            self._stop_event.clear()
            self._thread = Thread(target=self._run, name="motionsense-motion", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        thread: Thread | None
        with self._lock:
            self._armed = False
            self._stop_event.set()
            thread = self._thread
            self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)
        self.sense_hat.show_status("idle")

    def status_payload(self) -> dict[str, Any]:
        with self._lock:
            running = self._thread is not None and self._thread.is_alive()
            return {
                "armed": self._armed,
                "running": running,
                "poll_interval_seconds": self.poll_interval_seconds,
                "cooldown_seconds": self.cooldown_seconds,
                "motion_threshold": self.motion_threshold,
                "last_score": self._last_score,
                "last_probe_at": self._last_probe_at,
                "last_motion_at": self._last_motion_at,
                "last_error": self._last_error,
                "event_count": len(self._events),
            }

    def events_payload(self) -> list[dict[str, Any]]:
        with self._lock:
            return [asdict(event) for event in reversed(self._events)]

    def archived_events_payload(self, limit: int | None = None) -> list[dict[str, Any]]:
        event_paths = sorted(
            (
                path
                for path in self.event_dir.glob("*.jpg")
                if path.is_file() and path.name != self._probe_path.name
            ),
            reverse=True,
        )
        if limit is not None:
            event_paths = event_paths[: max(limit, 0)]
        return [asdict(self._event_record_for_path(path)) for path in event_paths]

    def selected_event_paths(self, filenames: list[str]) -> list[Path]:
        if not filenames:
            raise RuntimeError("Select at least one event image.")

        selected_paths: list[Path] = []
        seen_names: set[str] = set()
        for filename in filenames:
            if not isinstance(filename, str) or not filename:
                raise RuntimeError("Each selected event image must have a valid filename.")
            if filename in seen_names:
                continue
            event_path = self.resolve_event_path(filename)
            if event_path is None:
                raise RuntimeError(f"Event image '{filename}' was not found.")
            seen_names.add(filename)
            selected_paths.append(event_path)
        return selected_paths

    def delete_events(self, filenames: list[str]) -> list[str]:
        event_paths = self.selected_event_paths(filenames)
        deleted_filenames: list[str] = []
        for event_path in event_paths:
            event_path.unlink()
            self._metadata_path_for_event(event_path).unlink(missing_ok=True)
            deleted_filenames.append(event_path.name)

        deleted_names = set(deleted_filenames)
        with self._lock:
            self._events = deque(
                (
                    event
                    for event in self._events
                    if Path(event.snapshot_path).name not in deleted_names
                ),
                maxlen=self.max_events,
            )
        return deleted_filenames

    def resolve_event_path(self, filename: str) -> Path | None:
        candidate = (self.event_dir / filename).resolve()
        try:
            candidate.relative_to(self.event_dir.resolve())
        except ValueError:
            return None
        if not candidate.exists() or not candidate.is_file():
            return None
        return candidate

    def _metadata_path_for_event(self, path: Path) -> Path:
        return path.with_suffix(".json")

    def _write_event_metadata(
        self,
        path: Path,
        detected_at: str | None,
        source: str,
        score: float | None,
    ) -> None:
        payload = {
            "detected_at": detected_at,
            "source": source,
            "score": round(score, 2) if score is not None else None,
        }
        self._metadata_path_for_event(path).write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

    def _load_event_metadata(self, path: Path) -> dict[str, Any]:
        metadata_path = self._metadata_path_for_event(path)
        if not metadata_path.exists():
            return {}
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return metadata if isinstance(metadata, dict) else {}

    def _detected_at_for_path(self, path: Path) -> str:
        try:
            detected_at = datetime.strptime(path.stem, "%Y%m%dT%H%M%S%fZ").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            detected_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        return detected_at.isoformat()

    def _event_record_for_path(
        self,
        path: Path,
        score: float | None = None,
        source: str = "motion",
    ) -> MotionEventRecord:
        metadata = self._load_event_metadata(path)
        detected_at = metadata.get("detected_at")
        if not isinstance(detected_at, str) or not detected_at:
            detected_at = self._detected_at_for_path(path)

        metadata_source = metadata.get("source")
        if isinstance(metadata_source, str) and metadata_source:
            source = metadata_source

        metadata_score = metadata.get("score")
        if isinstance(metadata_score, (int, float)) and not isinstance(metadata_score, bool):
            score = float(metadata_score)

        return MotionEventRecord(
            event_id=path.stem,
            detected_at=detected_at,
            source=source,
            score=round(score, 2) if score is not None else None,
            snapshot_path=str(path),
            snapshot_url=f"/events/{path.name}",
            size_bytes=path.stat().st_size,
        )

    def _capture_event_snapshots(
        self,
        count: int,
        score: float | None = None,
        source: str = "motion",
    ) -> tuple[list[MotionEventRecord], str | None]:
        events: list[MotionEventRecord] = []
        detected_at: str | None = None
        for _ in range(max(count, 1)):
            snapshot = self.camera.capture_snapshot()
            detected_at = snapshot.modified_at or datetime.now(tz=timezone.utc).isoformat()
            event_id = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            event_path = self.event_dir / f"{event_id}.jpg"
            shutil.copy2(self.camera.snapshot_path, event_path)
            self._write_event_metadata(event_path, detected_at, source, score)
            event_details = self.camera.details_for_path(event_path)

            event = self._event_record_for_path(event_path, score=score, source=source)
            events.append(
                MotionEventRecord(
                    event_id=event.event_id,
                    detected_at=detected_at,
                    source=event.source,
                    score=event.score,
                    snapshot_path=event_details.path,
                    snapshot_url=event.snapshot_url,
                    size_bytes=event_details.size_bytes,
                )
            )
        return events, detected_at

    def record_external_capture(self, source: str = "timer") -> list[MotionEventRecord]:
        if not self.camera.is_available():
            raise RuntimeError("Camera command is unavailable.")

        events, _ = self._capture_event_snapshots(count=1, score=None, source=source)
        with self._lock:
            for event in events:
                self._events.append(event)
            self._last_error = None

        self.sense_hat.show_status("capture-ok")
        return events

    def _run(self) -> None:
        while not self._stop_event.is_set():
            loop_started = time.monotonic()
            try:
                if not self.camera.is_available():
                    raise RuntimeError("Camera command is unavailable.")

                probe_details = self.camera.capture_probe(self._probe_path)
                score = self._measure_motion(self._probe_path)
                restore_idle = False

                with self._lock:
                    restore_idle = self._last_error is not None
                    self._last_probe_at = probe_details.modified_at
                    self._last_score = round(score, 2)
                    self._last_error = None

                if restore_idle:
                    self.sense_hat.show_status("idle")

                if (
                    score >= self.motion_threshold
                    and loop_started - self._last_capture_monotonic >= self.cooldown_seconds
                ):
                    self._record_event(score, loop_started)
            except RuntimeError as exc:
                with self._lock:
                    self._last_error = str(exc)
                self.sense_hat.show_status("camera-error")

            elapsed = time.monotonic() - loop_started
            wait_time = max(self.poll_interval_seconds - elapsed, 0.2)
            self._stop_event.wait(wait_time)

        self._previous_frame = None

    def _measure_motion(self, probe_path: Path) -> float:
        with Image.open(probe_path) as image:
            current_frame = image.convert("L").resize((64, 48)).copy()

        if self._previous_frame is None:
            self._previous_frame = current_frame
            return 0.0

        difference = ImageChops.difference(self._previous_frame, current_frame)
        score = float(ImageStat.Stat(difference).mean[0])
        self._previous_frame = current_frame
        return score

    def _record_event(self, score: float, capture_started: float) -> None:
        events, detected_at = self._capture_event_snapshots(
            count=self.camera.burst_count(),
            score=score,
            source="motion",
        )

        with self._lock:
            for event in events:
                self._events.append(event)
            self._last_motion_at = detected_at
            self._last_capture_monotonic = capture_started
            self._last_error = None

        self.sense_hat.show_status("capture-ok")
