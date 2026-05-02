from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any

from PIL import Image, ImageChops, ImageStat

from app.motion import MotionDetector
from app.sensehat import SenseHatService


class TimedCaptureService:
    TIMER_MODE = "timer"
    COMBO_MODE = "combo"

    def __init__(
        self,
        motion_detector: MotionDetector,
        sense_hat: SenseHatService,
        config_path: Path | None = None,
        interval_seconds: int = 60,
        mode: str = TIMER_MODE,
        duration_seconds: int = 60,
    ) -> None:
        self.motion_detector = motion_detector
        self.sense_hat = sense_hat
        self.config_path = config_path
        self.interval_seconds = interval_seconds
        self.mode = mode
        self.duration_seconds = duration_seconds

        self._lock = Lock()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._armed = False
        self._last_capture_at: str | None = None
        self._last_motion_at: str | None = None
        self._last_error: str | None = None
        self._capture_count = 0
        self._waiting_for_motion = False
        self._last_motion_score: float | None = None
        self._probe_path = (
            (config_path.parent if config_path is not None else motion_detector.event_dir.parent)
            / "_auto_capture_probe.jpg"
        )
        self._previous_probe_frame: Image.Image | None = None
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

    @classmethod
    def _normalize_mode(cls, value: object) -> str:
        if not isinstance(value, str):
            raise RuntimeError("Auto capture mode must be timer or combo.")
        normalized = value.strip().lower()
        if normalized not in {cls.TIMER_MODE, cls.COMBO_MODE}:
            raise RuntimeError("Auto capture mode must be timer or combo.")
        return normalized

    @staticmethod
    def _normalize_duration(value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RuntimeError(
                "Auto capture duration must be a whole number of seconds between 1 and 86400."
            )
        normalized = float(value)
        if not normalized.is_integer():
            raise RuntimeError(
                "Auto capture duration must be a whole number of seconds between 1 and 86400."
            )
        seconds = int(normalized)
        if seconds < 1 or seconds > 86400:
            raise RuntimeError("Auto capture duration must be between 1 second and 24 hours.")
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
        try:
            self.mode = self._normalize_mode(config.get("mode", self.mode))
        except RuntimeError:
            self.mode = self.TIMER_MODE
        try:
            self.duration_seconds = self._normalize_duration(
                config.get("duration_seconds", self.duration_seconds)
            )
        except RuntimeError:
            self.duration_seconds = 60

    def _save_config(self) -> None:
        if self.config_path is None:
            return
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "interval_seconds": self.interval_seconds,
            "mode": self.mode,
            "duration_seconds": self.duration_seconds,
        }
        self.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def set_interval_seconds(self, value: int) -> None:
        normalized = self._normalize_interval(value)
        with self._lock:
            self.interval_seconds = normalized
        self._save_config()

    def set_mode(self, value: str) -> None:
        normalized = self._normalize_mode(value)
        with self._lock:
            self.mode = normalized
        self._save_config()

    def set_duration_seconds(self, value: int) -> None:
        normalized = self._normalize_duration(value)
        with self._lock:
            self.duration_seconds = normalized
        self._save_config()

    @classmethod
    def _validate_mode_settings(cls, mode: str, interval_seconds: int) -> None:
        if mode == cls.COMBO_MODE and interval_seconds < 7:
            raise RuntimeError("Motion + Timer interval must be at least 7 seconds.")

    def start(
        self,
        interval_seconds: int | None = None,
        mode: str | None = None,
        duration_seconds: int | None = None,
    ) -> None:
        next_interval = (
            self._normalize_interval(interval_seconds)
            if interval_seconds is not None
            else self.interval_seconds
        )
        next_mode = self._normalize_mode(mode) if mode is not None else self.mode
        next_duration = (
            self._normalize_duration(duration_seconds)
            if duration_seconds is not None
            else self.duration_seconds
        )
        self._validate_mode_settings(next_mode, next_interval)

        with self._lock:
            self.interval_seconds = next_interval
            self.mode = next_mode
            self.duration_seconds = next_duration
        self._save_config()

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
            self._waiting_for_motion = False
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)
        self._previous_probe_frame = None
        self.sense_hat.show_status("idle")

    def status_payload(self) -> dict[str, Any]:
        with self._lock:
            running = self._thread is not None and self._thread.is_alive()
            return {
                "armed": self._armed,
                "running": running,
                "mode": self.mode,
                "interval_seconds": self.interval_seconds,
                "duration_seconds": self.duration_seconds,
                "last_capture_at": self._last_capture_at,
                "last_motion_at": self._last_motion_at,
                "waiting_for_motion": self._waiting_for_motion,
                "last_motion_score": self._last_motion_score,
                "last_error": self._last_error,
                "capture_count": self._capture_count,
            }

    def _capture_once(self, source: str) -> None:
        events = self.motion_detector.record_external_capture(source=source)
        last_capture_at = events[-1].detected_at if events else None
        with self._lock:
            self._last_capture_at = last_capture_at
            self._capture_count += len(events)
            self._last_error = None

    def _measure_probe_motion(self) -> tuple[float, str | None]:
        if not self.motion_detector.camera.is_available():
            raise RuntimeError("Camera command is unavailable.")

        probe_details = self.motion_detector.camera.capture_probe(self._probe_path)
        with Image.open(self._probe_path) as image:
            current_frame = image.convert("L").resize((64, 48)).copy()

        if self._previous_probe_frame is None:
            self._previous_probe_frame = current_frame
            score = 0.0
        else:
            difference = ImageChops.difference(self._previous_probe_frame, current_frame)
            score = float(ImageStat.Stat(difference).mean[0])
            self._previous_probe_frame = current_frame

        with self._lock:
            self._last_motion_score = round(score, 2)
            self._last_error = None

        return score, probe_details.modified_at

    def _wait_for_detector_motion_trigger(self) -> bool:
        with self._lock:
            self._waiting_for_motion = True

        baseline_epoch, _ = self.motion_detector.motion_marker()

        while not self._stop_event.is_set():
            current_epoch, detected_at = self.motion_detector.motion_marker()
            if current_epoch != baseline_epoch and detected_at is not None:
                motion_status = self.motion_detector.status_payload()
                with self._lock:
                    self._waiting_for_motion = False
                    self._last_motion_at = detected_at
                    self._last_motion_score = motion_status.get("last_score")
                    self._last_error = None
                return True

            wait_time = max(self.motion_detector.poll_interval_seconds / 2, 0.2)
            if self._stop_event.wait(wait_time):
                break

        with self._lock:
            self._waiting_for_motion = False
        return False

    def _wait_for_local_motion_trigger(self) -> bool:
        with self._lock:
            self._waiting_for_motion = True

        while not self._stop_event.is_set():
            loop_started = time.monotonic()
            try:
                score, detected_at = self._measure_probe_motion()
                if score >= self.motion_detector.motion_threshold:
                    with self._lock:
                        self._waiting_for_motion = False
                        self._last_motion_at = detected_at
                    return True
            except RuntimeError as exc:
                with self._lock:
                    self._last_error = str(exc)
                self.sense_hat.show_status("camera-error")

            elapsed = time.monotonic() - loop_started
            wait_time = max(self.motion_detector.poll_interval_seconds - elapsed, 0.2)
            if self._stop_event.wait(wait_time):
                break

        with self._lock:
            self._waiting_for_motion = False
        return False

    def _wait_for_motion_trigger(self) -> bool:
        motion_status = self.motion_detector.status_payload()
        if motion_status.get("armed"):
            return self._wait_for_detector_motion_trigger()
        return self._wait_for_local_motion_trigger()

    def _run_timer_mode(self) -> None:
        loop_started = time.monotonic()
        try:
            self._capture_once(source="timer")
        except RuntimeError as exc:
            with self._lock:
                self._last_error = str(exc)
            self.sense_hat.show_status("camera-error")

        elapsed = time.monotonic() - loop_started
        wait_time = max(self.interval_seconds - elapsed, 0.0)
        self._stop_event.wait(wait_time)

    def _run_combo_mode(self) -> None:
        if not self._wait_for_motion_trigger():
            return

        window_started = time.monotonic()
        next_capture_at = window_started
        while not self._stop_event.is_set() and time.monotonic() - window_started < self.duration_seconds:
            now = time.monotonic()
            wait_until_capture = max(next_capture_at - now, 0.0)
            if wait_until_capture > 0 and self._stop_event.wait(wait_until_capture):
                return

            try:
                self._capture_once(source="combo")
            except RuntimeError as exc:
                with self._lock:
                    self._last_error = str(exc)
                self.sense_hat.show_status("camera-error")
                return

            next_capture_at += self.interval_seconds

        self._previous_probe_frame = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            mode = self.mode
            if mode == self.COMBO_MODE:
                self._run_combo_mode()
            else:
                self._run_timer_mode()

        self._previous_probe_frame = None
