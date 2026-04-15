from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import threading
from typing import Any


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
        self._selected_source_id: str | None = None
        self._selected_source_name: str | None = None

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

    def _available_sources(self) -> list[CameraSource]:
        sources: list[CameraSource] = []
        pi_source = self._probe_pi_source()
        if pi_source is not None:
            sources.append(pi_source)
        sources.extend(self._probe_usb_sources())
        return sources

    def _sources_by_id(self) -> dict[str, CameraSource]:
        return {source.source_id: source for source in self._available_sources()}

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

    def selected_source_id(self) -> str | None:
        sources_by_id = self._sources_by_id()
        self._ensure_selection(sources_by_id)
        return self._selected_source_id

    def selected_source_name(self) -> str | None:
        sources_by_id = self._sources_by_id()
        self._ensure_selection(sources_by_id)
        if self._selected_source_id in sources_by_id:
            return sources_by_id[self._selected_source_id].label
        return self._selected_source_name

    def list_sources(self) -> list[dict[str, Any]]:
        sources_by_id = self._sources_by_id()
        self._ensure_selection(sources_by_id)

        payload = [
            {
                "source_id": source.source_id,
                "label": source.label,
                "kind": source.kind,
                "available": source.available,
                "backend": source.backend,
                "device": source.device,
                "selected": source.source_id == self._selected_source_id,
            }
            for source in sources_by_id.values()
        ]

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
                    "device": None,
                    "selected": True,
                },
            )

        return payload

    def set_active_source(self, source_id: str) -> None:
        sources_by_id = self._sources_by_id()
        if source_id not in sources_by_id:
            raise RuntimeError(f"Camera source '{source_id}' is not available.")

        selected_source = sources_by_id[source_id]
        self._selected_source_id = selected_source.source_id
        self._selected_source_name = selected_source.label

    def active_source(self) -> CameraSource | None:
        sources_by_id = self._sources_by_id()
        self._ensure_selection(sources_by_id)
        if self._selected_source_id is None:
            return None
        return sources_by_id.get(self._selected_source_id)

    def active_capture_target(self) -> str | None:
        source = self.active_source()
        if source is None:
            return None
        return source.device or source.command

    def is_available(self) -> bool:
        return self.active_source() is not None

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

        command = [
            self.v4l2ctl_executable,
            "-d",
            device,
            f"--set-fmt-video=width={width},height={height},pixelformat=MJPG",
            "--stream-mmap=3",
            "--stream-count=1",
            f"--stream-to={output_path}",
        ]

        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )

    def capture_image(
        self,
        output_path: Path,
        width: int,
        height: int,
        quality: int = 90,
    ) -> SnapshotDetails:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        source = self.active_source()
        if source is None:
            selected_name = self.selected_source_name() or "camera"
            raise RuntimeError(f"Selected camera source '{selected_name}' is unavailable.")

        try:
            with self._lock:
                if source.kind == "pi":
                    self._capture_pi_image(output_path, width, height, quality)
                elif source.kind == "usb" and source.device is not None:
                    self._capture_usb_image(source.device, output_path, width, height)
                else:
                    raise RuntimeError(f"Unsupported camera source '{source.label}'.")
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Snapshot capture timed out.") from exc
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() if exc.stderr else "unknown camera error"
            raise RuntimeError(f"Snapshot capture failed: {stderr}") from exc

        return self.details_for_path(output_path)

    def capture_snapshot(self) -> SnapshotDetails:
        return self.capture_image(
            output_path=self.snapshot_path,
            width=self.width,
            height=self.height,
        )

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
