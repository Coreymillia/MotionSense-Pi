from __future__ import annotations

from collections import deque
import json
from pathlib import Path
from typing import Any
import time

from PIL import Image, ImageChops

from app.camera import CameraService
from app.motion import MotionDetector, MotionEventRecord
from app.sensehat import SenseHatService


class StormwatchDetector(MotionDetector):
    def __init__(
        self,
        camera: CameraService,
        sense_hat: SenseHatService,
        event_dir: Path,
        gallery_dir: Path | None = None,
        config_path: Path | None = None,
        poll_interval_seconds: float = 1.0,
        cooldown_seconds: float = 10.0,
        score_trigger: float = 12.0,
        hot_pixel_threshold: int = 60,
        buffer_size: int = 15,
        post_capture_frames: int = 5,
        max_events: int = 12,
        min_free_space_bytes: int = 5 * 1024 * 1024 * 1024,
    ) -> None:
        self._stormwatch_buffer_size = self._normalize_buffer_size(buffer_size)
        self._stormwatch_hot_pixel_threshold = self._normalize_hot_pixel_threshold(
            hot_pixel_threshold
        )
        self._stormwatch_post_capture_frames = self._normalize_post_capture_frames(
            post_capture_frames
        )
        self._stormwatch_frame_buffer: deque[Image.Image] = deque(
            maxlen=self._stormwatch_buffer_size
        )
        super().__init__(
            camera=camera,
            sense_hat=sense_hat,
            event_dir=event_dir,
            gallery_dir=gallery_dir,
            config_path=config_path,
            poll_interval_seconds=poll_interval_seconds,
            cooldown_seconds=cooldown_seconds,
            motion_threshold=score_trigger,
            max_events=max_events,
            min_free_space_bytes=min_free_space_bytes,
        )
        probe_base = (
            config_path.parent if config_path is not None else event_dir.parent
        )
        self._probe_path = probe_base / "_stormwatch_probe.jpg"

    @staticmethod
    def _normalize_buffer_size(value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise RuntimeError("Stormwatch buffer size must be an integer between 1 and 120.")
        if value < 1 or value > 120:
            raise RuntimeError("Stormwatch buffer size must be between 1 and 120.")
        return value

    @staticmethod
    def _normalize_hot_pixel_threshold(value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise RuntimeError(
                "Stormwatch hot pixel threshold must be an integer between 1 and 255."
            )
        if value < 1 or value > 255:
            raise RuntimeError(
                "Stormwatch hot pixel threshold must be between 1 and 255."
            )
        return value

    @staticmethod
    def _normalize_post_capture_frames(value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise RuntimeError(
                "Stormwatch post-capture frames must be an integer between 0 and 20."
            )
        if value < 0 or value > 20:
            raise RuntimeError(
                "Stormwatch post-capture frames must be between 0 and 20."
            )
        return value

    def _load_config(self) -> None:
        super()._load_config()
        if self.config_path is None or not self.config_path.exists():
            return

        try:
            config = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        try:
            self._stormwatch_buffer_size = self._normalize_buffer_size(
                config.get("buffer_size", self._stormwatch_buffer_size)
            )
            self._stormwatch_hot_pixel_threshold = self._normalize_hot_pixel_threshold(
                config.get("hot_pixel_threshold", self._stormwatch_hot_pixel_threshold)
            )
            self._stormwatch_post_capture_frames = self._normalize_post_capture_frames(
                config.get("post_capture_frames", self._stormwatch_post_capture_frames)
            )
        except RuntimeError:
            return

        self._stormwatch_frame_buffer = deque(maxlen=self._stormwatch_buffer_size)

    def _save_config(self) -> None:
        if self.config_path is None:
            return
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "mode": "stormwatch",
            "poll_interval_seconds": self.poll_interval_seconds,
            "cooldown_seconds": self.cooldown_seconds,
            "score_trigger": self.motion_threshold,
            "motion_threshold": self.motion_threshold,
            "buffer_size": self._stormwatch_buffer_size,
            "hot_pixel_threshold": self._stormwatch_hot_pixel_threshold,
            "post_capture_frames": self._stormwatch_post_capture_frames,
        }
        self.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def set_score_trigger(self, value: float) -> None:
        normalized = self._normalize_motion_threshold(value)
        with self._lock:
            self.motion_threshold = normalized
        self._save_config()

    def set_buffer_size(self, value: int) -> None:
        normalized = self._normalize_buffer_size(value)
        with self._lock:
            self._stormwatch_buffer_size = normalized
            self._stormwatch_frame_buffer = deque(maxlen=normalized)
            self._previous_frame = None
        self._save_config()

    def set_hot_pixel_threshold(self, value: int) -> None:
        normalized = self._normalize_hot_pixel_threshold(value)
        with self._lock:
            self._stormwatch_hot_pixel_threshold = normalized
        self._save_config()

    def set_post_capture_frames(self, value: int) -> None:
        normalized = self._normalize_post_capture_frames(value)
        with self._lock:
            self._stormwatch_post_capture_frames = normalized
        self._save_config()

    def start(
        self,
        interval_seconds: int | None = None,
        mode: str | None = None,
        duration_seconds: int | None = None,
    ) -> None:
        with self._lock:
            already_running = self._armed and self._thread is not None and self._thread.is_alive()
            if not already_running:
                self._stormwatch_frame_buffer = deque(maxlen=self._stormwatch_buffer_size)
                self._previous_frame = None
        super().start(interval_seconds=interval_seconds, mode=mode, duration_seconds=duration_seconds)

    def stop(self) -> None:
        super().stop()
        with self._lock:
            self._stormwatch_frame_buffer = deque(maxlen=self._stormwatch_buffer_size)
            self._previous_frame = None

    def status_payload(self) -> dict[str, Any]:
        payload = super().status_payload()
        payload.update(
            {
                "mode": "stormwatch",
                "score_trigger": self.motion_threshold,
                "hot_pixel_threshold": self._stormwatch_hot_pixel_threshold,
                "buffer_size": self._stormwatch_buffer_size,
                "post_capture_frames": self._stormwatch_post_capture_frames,
                "last_lightning_at": payload["last_motion_at"],
            }
        )
        return payload

    def record_external_capture(self, source: str = "stormwatch") -> list[MotionEventRecord]:
        if not self.camera.is_available():
            raise RuntimeError("Camera command is unavailable.")

        events, _ = self._capture_event_snapshots(count=1, score=None, source=source)
        with self._lock:
            for event in events:
                self._events.append(event)
            self._last_error = None

        self.sense_hat.show_status("capture-ok")
        return events

    def _capture_lightning_score(self, probe_path: Path) -> float:
        with Image.open(probe_path) as image:
            current_frame = image.convert("L").resize((64, 48)).copy()

        with self._lock:
            self._stormwatch_frame_buffer.append(current_frame)
            if len(self._stormwatch_frame_buffer) < self._stormwatch_buffer_size:
                self._previous_frame = current_frame
                return 0.0

            previous_frame = self._previous_frame
            self._previous_frame = current_frame

        if previous_frame is None:
            return 0.0

        difference = ImageChops.difference(previous_frame, current_frame)
        diff_values = list(difference.getdata())
        if not diff_values:
            return 0.0

        hot_pixels = sum(
            1 for value in diff_values if value > self._stormwatch_hot_pixel_threshold
        )
        hot_ratio = hot_pixels / len(diff_values)
        sorted_values = sorted(diff_values)
        peak_index = min(int((len(sorted_values) - 1) * 0.99), len(sorted_values) - 1)
        peak = float(sorted_values[peak_index])
        return hot_ratio * 100 + peak * 0.5

    def _record_event(self, score: float, capture_started: float) -> None:
        events, detected_at = self._capture_event_snapshots(
            count=self.camera.burst_count() + self._stormwatch_post_capture_frames,
            score=score,
            source="stormwatch",
        )

        with self._lock:
            for event in events:
                self._events.append(event)
            self._last_motion_at = detected_at
            self._last_capture_monotonic = capture_started
            self._last_error = None
            self._motion_epoch += 1

        self.sense_hat.show_status("capture-ok")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            loop_started = time.monotonic()
            try:
                if not self.camera.is_available():
                    raise RuntimeError("Camera command is unavailable.")

                probe_details = self.camera.capture_probe(self._probe_path)
                score = self._capture_lightning_score(self._probe_path)
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

        with self._lock:
            self._stormwatch_frame_buffer = deque(maxlen=self._stormwatch_buffer_size)
            self._previous_frame = None
