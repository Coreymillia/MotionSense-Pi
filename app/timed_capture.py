from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any

from app.motion import MotionDetector
from app.sensehat import SenseHatService


class TimedCaptureService:
    def __init__(
        self,
        motion_detector: MotionDetector,
        sense_hat: SenseHatService,
        config_path: Path | None = None,
        interval_seconds: int = 60,
    ) -> None:
        self.motion_detector = motion_detector
        self.sense_hat = sense_hat
        self.config_path = config_path
        self.interval_seconds = interval_seconds

        self._lock = Lock()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._armed = False
        self._last_capture_at: str | None = None
        self._last_error: str | None = None
        self._capture_count = 0
        self._load_config()

    @staticmethod
    def _normalize_interval(value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RuntimeError(
                "Timer interval must be a whole number of seconds between 1 and 86400."
            )
        normalized = float(value)
        if not normalized.is_integer():
            raise RuntimeError(
                "Timer interval must be a whole number of seconds between 1 and 86400."
            )
        seconds = int(normalized)
        if seconds < 1 or seconds > 86400:
            raise RuntimeError("Timer interval must be between 1 second and 24 hours.")
        return seconds

    def _load_config(self) -> None:
        if self.config_path is None or not self.config_path.exists():
            return

        try:
            config = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        try:
            self.interval_seconds = self._normalize_interval(
                config.get("interval_seconds", self.interval_seconds)
            )
        except RuntimeError:
            return

    def _save_config(self) -> None:
        if self.config_path is None:
            return
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"interval_seconds": self.interval_seconds}
        self.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def set_interval_seconds(self, value: int) -> None:
        normalized = self._normalize_interval(value)
        with self._lock:
            self.interval_seconds = normalized
        self._save_config()

    def start(self, interval_seconds: int | None = None) -> None:
        if interval_seconds is not None:
            self.set_interval_seconds(interval_seconds)

        with self._lock:
            if self._armed and self._thread is not None and self._thread.is_alive():
                return
            self._armed = True
            self._stop_event.clear()
            self._thread = Thread(
                target=self._run,
                name="motionsense-timed-capture",
                daemon=True,
            )
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
                "interval_seconds": self.interval_seconds,
                "last_capture_at": self._last_capture_at,
                "last_error": self._last_error,
                "capture_count": self._capture_count,
            }

    def _run(self) -> None:
        while not self._stop_event.is_set():
            loop_started = time.monotonic()
            try:
                events = self.motion_detector.record_external_capture(source="timer")
                last_capture_at = events[-1].detected_at if events else None
                with self._lock:
                    self._last_capture_at = last_capture_at
                    self._capture_count += len(events)
                    self._last_error = None
            except RuntimeError as exc:
                with self._lock:
                    self._last_error = str(exc)
                self.sense_hat.show_status("camera-error")

            elapsed = time.monotonic() - loop_started
            wait_time = max(self.interval_seconds - elapsed, 0.0)
            if self._stop_event.wait(wait_time):
                break

