from __future__ import annotations

from importlib import import_module
from threading import Event, Lock, Thread
import time
from typing import Any


class SenseHatService:
    STATUS_COLORS = {
        "camera-error": (110, 0, 0),
        "sensor-error": (90, 55, 0),
    }

    def __init__(self) -> None:
        self._sense: Any | None = None
        self._reason: str | None = None
        self._display_lock = Lock()
        self._display_mode = "idle"
        self._flash_until = 0.0
        self._display_stop = Event()
        self._display_thread: Thread | None = None
        self._initialize()

    def _initialize(self) -> None:
        try:
            sense_hat_module = import_module("sense_hat")
        except ModuleNotFoundError:
            self._reason = "sense_hat package is not installed."
            return

        sense_hat_class = getattr(sense_hat_module, "SenseHat", None)
        if sense_hat_class is None:
            self._reason = "sense_hat package is missing the SenseHat class."
            return

        try:
            self._sense = sense_hat_class()
            self._sense.low_light = True
            self._start_display_thread()
        except (RuntimeError, OSError, ValueError) as exc:
            self._reason = f"Sense HAT is unavailable: {exc}"

    def _start_display_thread(self) -> None:
        if self._sense is None or (
            self._display_thread is not None and self._display_thread.is_alive()
        ):
            return

        self._display_thread = Thread(
            target=self._display_loop,
            name="motionsense-sensehat",
            daemon=True,
        )
        self._display_thread.start()

    @staticmethod
    def _c_to_f(temperature_c: float) -> float:
        return (temperature_c * 9 / 5) + 32

    @staticmethod
    def _mbar_to_inhg(pressure_mbar: float) -> float:
        return pressure_mbar * 0.0295299830714

    def _display_loop(self) -> None:
        step = 0
        while not self._display_stop.is_set():
            if self._sense is None:
                return

            with self._display_lock:
                mode = self._display_mode
                flash_until = self._flash_until

            try:
                if flash_until > time.monotonic():
                    color = (0, 0, 120) if int(time.monotonic() * 8) % 2 == 0 else (0, 0, 0)
                    self._sense.clear(color)
                    time.sleep(0.15)
                    continue

                if mode in self.STATUS_COLORS:
                    self._sense.clear(self.STATUS_COLORS[mode])
                    time.sleep(0.25)
                    continue

                self._sense.set_pixels(self._idle_pixels(step))
                step = (step + 1) % 8
                time.sleep(0.25)
            except (RuntimeError, OSError, ValueError) as exc:
                self._reason = f"Sense HAT LED matrix update failed: {exc}"
                return

    @staticmethod
    def _idle_pixels(step: int) -> list[tuple[int, int, int]]:
        pixels = [(0, 0, 0)] * 64
        trail = [36, 18, 8]
        for offset, blue_level in enumerate(trail):
            column = (step - offset) % 8
            for row in range(8):
                pixels[(row * 8) + column] = (0, 0, blue_level)
        return pixels

    def read(self) -> dict[str, Any]:
        if self._sense is None:
            return {
                "available": False,
                "reason": self._reason or "Sense HAT has not been initialized.",
            }

        try:
            orientation = self._sense.get_orientation()
            temperature_c = float(self._sense.get_temperature())
            pressure_mbar = float(self._sense.get_pressure())
            return {
                "available": True,
                "temperature_f": round(self._c_to_f(temperature_c), 1),
                "humidity_pct": round(float(self._sense.get_humidity()), 1),
                "pressure_inhg": round(self._mbar_to_inhg(pressure_mbar), 2),
                "orientation": {
                    "pitch": round(float(orientation["pitch"]), 1),
                    "roll": round(float(orientation["roll"]), 1),
                    "yaw": round(float(orientation["yaw"]), 1),
                },
            }
        except (RuntimeError, OSError, ValueError, KeyError) as exc:
            self.show_status("sensor-error")
            return {
                "available": False,
                "reason": f"Failed to read Sense HAT data: {exc}",
            }

    def show_status(self, status: str) -> None:
        if self._sense is None:
            return

        with self._display_lock:
            if status == "capture-ok":
                self._display_mode = "idle"
                self._flash_until = time.monotonic() + 1.2
                return

            self._display_mode = status
            self._flash_until = 0.0
