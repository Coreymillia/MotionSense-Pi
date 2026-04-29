from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import threading
import tempfile
from time import monotonic
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import urlopen


@dataclass(frozen=True)
class SnapshotDetails:
    exists: bool
    path: str
    modified_at: str | None
    size_bytes: int | None


@dataclass(frozen=True)
class CameraSource:
    source_id: str
    label: str
    kind: str
    available: bool
    backend: str
    command: str | None = None
    device: str | None = None
    base_url: str | None = None


@dataclass(frozen=True)
class ResolutionOption:
    width: int
    height: int
    label: str


class CameraService:
    def __init__(
        self,
        snapshot_path: Path,
        width: int = 1280,
        height: int = 720,
        timeout_seconds: int = 15,
    ) -> None:
        self.snapshot_path = snapshot_path
        self.width = width
        self.height = height
        self.timeout_seconds = timeout_seconds
        self.rpicam_executable = shutil.which("rpicam-still")
        self.v4l2ctl_executable = shutil.which("v4l2-ctl")
        self._lock = threading.Lock()
        self._config_path = snapshot_path.parent / "camera_config.json"
        self._selected_source_id: str | None = None
        self._selected_source_name: str | None = None
        self._network_camera_url: str | None = None
        self._burst_count = 1
        self._resolution_options: tuple[ResolutionOption, ...] | None = None
        self._source_cache_ttl_seconds = 5.0
        self._source_cache_at = 0.0
        self._source_cache: tuple[CameraSource, ...] | None = None
        self._load_config()

    def _load_config(self) -> None:
        if not self._config_path.exists():
            return

        try:
            config = json.loads(self._config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        selected_source_id = config.get("selected_source_id")
        if isinstance(selected_source_id, str) and selected_source_id:
            self._selected_source_id = selected_source_id

        selected_source_name = config.get("selected_source_name")
        if isinstance(selected_source_name, str) and selected_source_name:
            self._selected_source_name = selected_source_name

        self._network_camera_url = self._normalize_camera_url(
            config.get("network_camera_url")
        )

        try:
            self._burst_count = self._normalize_burst_count(config.get("burst_count", 1))
        except RuntimeError:
            self._burst_count = 1

        try:
            self.width, self.height = self._normalize_resolution(
                config.get("width", self.width),
                config.get("height", self.height),
                options=self.resolution_options(),
            )
        except RuntimeError:
            self.width, self.height = 1280, 720

    def _save_config(self) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "selected_source_id": self._selected_source_id,
            "selected_source_name": self._selected_source_name,
            "network_camera_url": self._network_camera_url,
            "burst_count": self._burst_count,
            "width": self.width,
            "height": self.height,
        }
        self._config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def _normalize_camera_url(value: object) -> str | None:
        if not isinstance(value, str):
            return None

        normalized = value.strip()
        if not normalized:
            return None
        if "://" not in normalized:
            normalized = f"http://{normalized}"
        normalized = normalized.rstrip("/")

        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError("Camera URL must be a valid http:// or https:// address.")
        return normalized

    def network_camera_url(self) -> str | None:
        return self._network_camera_url

    @staticmethod
    def _normalize_burst_count(value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise RuntimeError("Burst count must be an integer between 1 and 5.")
        if value < 1 or value > 5:
            raise RuntimeError("Burst count must be between 1 and 5.")
        return value

    def burst_count(self) -> int:
        return self._burst_count

    def set_burst_count(self, value: int) -> None:
        self._burst_count = self._normalize_burst_count(value)
        self._save_config()

    @staticmethod
    def _resolution_key(width: int, height: int) -> tuple[int, int]:
        return (width, height)

    @staticmethod
    def _option_label(width: int, height: int, max_resolution: tuple[int, int]) -> str:
        label = f"{width} x {height}"
        if (width, height) == max_resolution:
            return f"{label} (Max)"
        return label

    def _default_resolution_pairs(self) -> list[tuple[int, int]]:
        return [
            (640, 480),
            (1280, 720),
            (1640, 1232),
            (1920, 1080),
            (3280, 2464),
        ]

    def _probe_resolution_pairs(self) -> list[tuple[int, int]]:
        if self.rpicam_executable is None:
            return []

        try:
            output = subprocess.run(
                [self.rpicam_executable, "--list-cameras"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout
        except (subprocess.SubprocessError, OSError):
            return []

        matches = re.findall(r"(\d+)x(\d+)", output)
        if not matches:
            return []

        resolutions = {
            self._resolution_key(int(width), int(height))
            for width, height in matches
        }
        return sorted(resolutions, key=lambda item: (item[0] * item[1], item[0], item[1]))

    def resolution_options(self) -> list[ResolutionOption]:
        if self._resolution_options is not None:
            return list(self._resolution_options)

        pairs = set(self._default_resolution_pairs())
        pairs.update(self._probe_resolution_pairs())
        pairs.add(self._resolution_key(self.width, self.height))

        sorted_pairs = sorted(pairs, key=lambda item: (item[0] * item[1], item[0], item[1]))
        max_resolution = max(sorted_pairs, key=lambda item: item[0] * item[1])
        self._resolution_options = tuple(
            ResolutionOption(
                width=width,
                height=height,
                label=self._option_label(width, height, max_resolution),
            )
            for width, height in sorted_pairs
        )
        return list(self._resolution_options)

    @classmethod
    def _normalize_resolution(
        cls,
        width: object,
        height: object,
        options: list[ResolutionOption],
    ) -> tuple[int, int]:
        if (
            isinstance(width, bool)
            or not isinstance(width, int)
            or isinstance(height, bool)
            or not isinstance(height, int)
        ):
            raise RuntimeError("Resolution must match a supported width and height.")

        requested = cls._resolution_key(width, height)
        valid_options = {cls._resolution_key(option.width, option.height) for option in options}
        if requested not in valid_options:
            raise RuntimeError("Resolution must be one of the supported camera modes.")
        return requested

    def set_resolution(self, width: int, height: int) -> None:
        self.width, self.height = self._normalize_resolution(
            width,
            height,
            options=self.resolution_options(),
        )
        self._save_config()

    def set_network_camera_url(self, value: str) -> None:
        normalized = self._normalize_camera_url(value)
        self._network_camera_url = normalized
        if normalized is None and self._selected_source_id == "esp32-cam":
            self._selected_source_id = None
            self._selected_source_name = None
        self._invalidate_source_cache()
        self._save_config()

    def _network_endpoint(self, path: str) -> str:
        if self._network_camera_url is None:
            raise RuntimeError("ESP32-CAM URL is not configured.")
        return f"{self._network_camera_url}{path}"

    def _probe_pi_source(self) -> CameraSource | None:
        if self.rpicam_executable is None:
            return None

        return CameraSource(
            source_id="pi-camera",
            label="Pi Camera",
            kind="pi",
            available=True,
            backend="libcamera",
            command=self.rpicam_executable,
        )

    def _probe_usb_sources(self) -> list[CameraSource]:
        if self.v4l2ctl_executable is None:
            return []

        sources: list[CameraSource] = []
        for video_device in sorted(Path("/dev").glob("video*")):
            name_path = Path("/sys/class/video4linux") / video_device.name / "name"
            try:
                device_name = name_path.read_text(encoding="utf-8").strip()
            except OSError:
                continue

            lowered_name = device_name.lower()
            if any(
                token in lowered_name
                for token in ("bcm2835", "unicam", "codec", "isp", "metadata")
            ):
                continue

            try:
                formats = subprocess.run(
                    [self.v4l2ctl_executable, "-d", str(video_device), "--list-formats-ext"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=5,
                ).stdout
            except (subprocess.SubprocessError, OSError):
                continue

            if "MJPG" not in formats:
                continue

            sources.append(
                CameraSource(
                    source_id=f"usb-{video_device.name}",
                    label=f"USB Camera ({video_device.name})",
                    kind="usb",
                    available=True,
                    backend="v4l2",
                    command=self.v4l2ctl_executable,
                    device=str(video_device),
                )
            )

        return sources

    def _probe_network_source(self) -> CameraSource | None:
        if self._network_camera_url is None:
            return None

        available = False
        try:
            with urlopen(self._network_endpoint("/status"), timeout=2) as response:
                if response.status == 200:
                    json.loads(response.read().decode("utf-8"))
                    available = True
        except (RuntimeError, OSError, ValueError, HTTPError, URLError):
            available = False

        return CameraSource(
            source_id="esp32-cam",
            label="ESP32-CAM",
            kind="network",
            available=available,
            backend="http",
            base_url=self._network_camera_url,
        )

    def _invalidate_source_cache(self) -> None:
        self._source_cache = None
        self._source_cache_at = 0.0

    def _available_sources(self, refresh: bool = False) -> list[CameraSource]:
        if (
            not refresh
            and self._source_cache is not None
            and (monotonic() - self._source_cache_at) < self._source_cache_ttl_seconds
        ):
            return list(self._source_cache)

        sources: list[CameraSource] = []
        pi_source = self._probe_pi_source()
        if pi_source is not None:
            sources.append(pi_source)
        sources.extend(self._probe_usb_sources())
        network_source = self._probe_network_source()
        if network_source is not None:
            sources.append(network_source)
        self._source_cache = tuple(sources)
        self._source_cache_at = monotonic()
        return sources

    def _sources_by_id(self, refresh: bool = False) -> dict[str, CameraSource]:
        return {source.source_id: source for source in self._available_sources(refresh=refresh)}

    def _ensure_selection(self, sources_by_id: dict[str, CameraSource]) -> None:
        if (
            self._selected_source_id is not None
            and self._selected_source_id in sources_by_id
        ):
            self._selected_source_name = sources_by_id[self._selected_source_id].label
            return

        if self._selected_source_id is not None:
            return

        if "pi-camera" in sources_by_id:
            self._selected_source_id = "pi-camera"
            self._selected_source_name = sources_by_id["pi-camera"].label
            return

        if sources_by_id:
            first_source = next(iter(sources_by_id.values()))
            self._selected_source_id = first_source.source_id
            self._selected_source_name = first_source.label

    def selected_source_id(self, refresh: bool = False) -> str | None:
        sources_by_id = self._sources_by_id(refresh=refresh)
        self._ensure_selection(sources_by_id)
        return self._selected_source_id

    def selected_source_name(self, refresh: bool = False) -> str | None:
        sources_by_id = self._sources_by_id(refresh=refresh)
        self._ensure_selection(sources_by_id)
        if self._selected_source_id in sources_by_id:
            return sources_by_id[self._selected_source_id].label
        return self._selected_source_name

    def list_sources(self, refresh: bool = False) -> list[dict[str, Any]]:
        sources_by_id = self._sources_by_id(refresh=refresh)
        self._ensure_selection(sources_by_id)

        payload = []
        for source in sources_by_id.values():
            payload.append(
                {
                    **asdict(source),
                    "selected": source.source_id == self._selected_source_id,
                }
            )

        if (
            self._selected_source_id is not None
            and self._selected_source_id not in sources_by_id
        ):
            payload.insert(
                0,
                {
                    "source_id": self._selected_source_id,
                    "label": self._selected_source_name or self._selected_source_id,
                    "kind": "missing",
                    "available": False,
                    "backend": "unavailable",
                    "command": None,
                    "device": None,
                    "base_url": None,
                    "selected": True,
                },
            )

        return payload

    def set_active_source(self, source_id: str) -> None:
        sources_by_id = self._sources_by_id(refresh=True)
        if source_id not in sources_by_id:
            raise RuntimeError(f"Camera source '{source_id}' is not available.")

        selected_source = sources_by_id[source_id]
        self._selected_source_id = selected_source.source_id
        self._selected_source_name = selected_source.label
        self._save_config()

    def active_source(self, refresh: bool = False) -> CameraSource | None:
        sources_by_id = self._sources_by_id(refresh=refresh)
        self._ensure_selection(sources_by_id)
        if self._selected_source_id is None:
            return None
        return sources_by_id.get(self._selected_source_id)

    def active_capture_target(self) -> str | None:
        source = self.active_source()
        if source is None:
            return None
        return source.base_url or source.device or source.command

    def is_available(self, refresh: bool = False) -> bool:
        source = self.active_source(refresh=refresh)
        return source is not None and source.available

    def resolution_payload(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "options": [asdict(option) for option in self.resolution_options()],
        }

    def latest_snapshot_path(self) -> Path | None:
        if self.snapshot_path.exists():
            return self.snapshot_path
        return None

    def details_for_path(self, path: Path) -> SnapshotDetails:
        if not path.exists():
            return SnapshotDetails(
                exists=False,
                path=str(path),
                modified_at=None,
                size_bytes=None,
            )

        stat_result = path.stat()
        modified_at = datetime.fromtimestamp(
            stat_result.st_mtime, tz=timezone.utc
        ).isoformat()

        return SnapshotDetails(
            exists=True,
            path=str(path),
            modified_at=modified_at,
            size_bytes=stat_result.st_size,
        )

    def snapshot_details(self) -> SnapshotDetails:
        return self.details_for_path(self.snapshot_path)

    def _capture_pi_image(
        self,
        output_path: Path,
        width: int,
        height: int,
        quality: int,
    ) -> None:
        if self.rpicam_executable is None:
            raise RuntimeError("rpicam-still is not installed on this device.")

        command = [
            self.rpicam_executable,
            "--output",
            str(output_path),
            "--nopreview",
            "--immediate",
            "--encoding",
            "jpg",
            "--width",
            str(width),
            "--height",
            str(height),
            "--quality",
            str(quality),
        ]

        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )

    def _capture_usb_image(
        self,
        device: str,
        output_path: Path,
        width: int,
        height: int,
    ) -> None:
        if self.v4l2ctl_executable is None:
            raise RuntimeError("v4l2-ctl is not installed on this device.")

        with tempfile.NamedTemporaryFile(
            suffix=".mjpg",
            delete=False,
            dir=output_path.parent,
        ) as temp_file:
            temp_path = Path(temp_file.name)

        command = [
            self.v4l2ctl_executable,
            "-d",
            device,
            f"--set-fmt-video=width={width},height={height},pixelformat=MJPG",
            "--stream-mmap=3",
            "--stream-skip=4",
            "--stream-count=5",
            f"--stream-to={temp_path}",
        ]
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            output_path.write_bytes(self._extract_last_jpeg_frame(temp_path.read_bytes()))
        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _extract_last_jpeg_frame(data: bytes) -> bytes:
        start_marker = b"\xff\xd8"
        end_marker = b"\xff\xd9"
        starts = [
            index
            for index in range(len(data) - 1)
            if data[index : index + 2] == start_marker
        ]
        ends = [
            index + 2
            for index in range(len(data) - 1)
            if data[index : index + 2] == end_marker
        ]
        for start in reversed(starts):
            for end in reversed(ends):
                if end > start:
                    return data[start:end]
        raise RuntimeError("USB camera did not return a complete JPEG frame.")

    def _capture_network_image(self, output_path: Path) -> None:
        request_url = self._network_endpoint("/latest.jpg")
        with urlopen(request_url, timeout=self.timeout_seconds) as response:
            if response.status != 200:
                raise RuntimeError("ESP32-CAM snapshot request failed.")
            output_path.write_bytes(response.read())

    def capture_image(
        self,
        output_path: Path,
        width: int,
        height: int,
        quality: int = 90,
    ) -> SnapshotDetails:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        source = self.active_source(refresh=True)
        if source is None:
            selected_name = self.selected_source_name(refresh=True) or "camera"
            raise RuntimeError(f"Selected camera source '{selected_name}' is unavailable.")

        try:
            with self._lock:
                if source.kind == "pi":
                    self._capture_pi_image(output_path, width, height, quality)
                elif source.kind == "usb" and source.device is not None:
                    self._capture_usb_image(source.device, output_path, width, height)
                elif source.kind == "network":
                    self._capture_network_image(output_path)
                else:
                    raise RuntimeError(f"Unsupported camera source '{source.label}'.")
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Snapshot capture timed out.") from exc
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() if exc.stderr else "unknown camera error"
            raise RuntimeError(f"Snapshot capture failed: {stderr}") from exc
        except (HTTPError, URLError, OSError) as exc:
            raise RuntimeError(f"Snapshot capture failed: {exc}") from exc

        return self.details_for_path(output_path)

    def capture_snapshot(self) -> SnapshotDetails:
        return self.capture_image(
            output_path=self.snapshot_path,
            width=self.width,
            height=self.height,
        )

    def capture_snapshot_burst(self, count: int | None = None) -> list[SnapshotDetails]:
        total_count = self._burst_count if count is None else self._normalize_burst_count(count)
        return [self.capture_snapshot() for _ in range(total_count)]

    def capture_probe(
        self,
        output_path: Path,
        width: int = 320,
        height: int = 240,
        quality: int = 35,
    ) -> SnapshotDetails:
        return self.capture_image(
            output_path=output_path,
            width=width,
            height=height,
            quality=quality,
        )
