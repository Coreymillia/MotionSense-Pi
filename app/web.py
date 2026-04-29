from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import re
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile

from flask import Flask, abort, jsonify, render_template, request, send_file
from PIL import Image

from app.camera import CameraService
from app.monitor import MonitorService
from app.motion import MotionDetector
from app.sensehat import SenseHatService
from app.timed_capture import TimedCaptureService


def create_app(start_detector: bool = True) -> Flask:
    app = Flask(__name__)

    data_dir = Path(__file__).resolve().parent.parent / "data"
    snapshot_path = data_dir / "latest.jpg"
    event_dir = data_dir / "events"

    camera = CameraService(snapshot_path=snapshot_path)
    sense_hat = SenseHatService()
    sense_hat.show_status("idle")
    motion_detector = MotionDetector(
        camera=camera,
        sense_hat=sense_hat,
        event_dir=event_dir,
        config_path=data_dir / "motion_config.json",
    )
    timed_capture = TimedCaptureService(
        motion_detector=motion_detector,
        sense_hat=sense_hat,
        config_path=data_dir / "timer_config.json",
    )
    monitor = MonitorService(
        camera=camera,
        sense_hat=sense_hat,
        motion_detector=motion_detector,
        timed_capture=timed_capture,
    )
    if start_detector:
        motion_detector.start()

    def send_jpeg(path: Path):
        max_w = request.args.get("max_w", type=int)
        max_h = request.args.get("max_h", type=int)
        quality = request.args.get("quality", type=int)
        if max_w is None and max_h is None:
            return send_file(path, mimetype="image/jpeg", max_age=0)

        width = min(max(max_w or 304, 1), 1024)
        height = min(max(max_h or 172, 1), 1024)
        jpeg_quality = min(max(quality or 70, 30), 90)

        with Image.open(path) as image:
            preview = image.convert("RGB")
            preview.thumbnail((width, height), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            preview.save(buffer, format="JPEG", quality=jpeg_quality, optimize=True)
            buffer.seek(0)

        return send_file(buffer, mimetype="image/jpeg", max_age=0, download_name=path.name)

    @app.get("/")
    def index() -> str:
        return render_template("index.html", status=monitor.status_payload())

    @app.get("/archive")
    def archive() -> str:
        return render_template(
            "archive.html",
            events=monitor.archived_events_payload(),
            event_dir=str(event_dir),
        )

    def payload_filenames() -> list[str] | tuple[dict[str, object], int]:
        payload = request.get_json(silent=True) or {}
        filenames = payload.get("filenames")
        if not isinstance(filenames, list) or not filenames:
            return {"ok": False, "error": "filenames must be a non-empty list."}, 400

        normalized_filenames: list[str] = []
        for filename in filenames:
            if not isinstance(filename, str) or not filename:
                return {"ok": False, "error": "Each filename must be a non-empty string."}, 400
            normalized_filenames.append(filename)
        return normalized_filenames

    @app.get("/api/status")
    def api_status():
        return jsonify(monitor.status_payload())

    @app.post("/api/capture")
    def api_capture():
        try:
            payload = monitor.capture_snapshot()
            return jsonify(payload)
        except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
            sense_hat.show_status("camera-error")
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.post("/api/motion/start")
    def api_motion_start():
        try:
            return jsonify({"ok": True, "status": monitor.start_motion_detection()})
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.post("/api/motion/stop")
    def api_motion_stop():
        try:
            return jsonify({"ok": True, "status": monitor.stop_motion_detection()})
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.post("/api/timer/start")
    def api_timer_start():
        payload = request.get_json(silent=True) or {}
        interval_seconds = payload.get("interval_seconds")
        if isinstance(interval_seconds, bool) or not isinstance(interval_seconds, (int, float)):
            return jsonify({"ok": False, "error": "interval_seconds must be a number."}), 400

        try:
            return jsonify(
                {
                    "ok": True,
                    "status": monitor.start_timed_capture(int(interval_seconds)),
                }
            )
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.post("/api/timer/stop")
    def api_timer_stop():
        try:
            return jsonify({"ok": True, "status": monitor.stop_timed_capture()})
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.post("/api/camera/source")
    def api_camera_source():
        payload = request.get_json(silent=True) or {}
        source_id = payload.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            return jsonify({"ok": False, "error": "source_id is required."}), 400

        try:
            return jsonify({"ok": True, "status": monitor.set_camera_source(source_id)})
        except RuntimeError as exc:
            sense_hat.show_status("camera-error")
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.post("/api/camera/network")
    def api_camera_network():
        payload = request.get_json(silent=True) or {}
        camera_url = payload.get("url", "")
        if not isinstance(camera_url, str):
            return jsonify({"ok": False, "error": "url must be a string."}), 400

        try:
            return jsonify({"ok": True, "status": monitor.set_network_camera_url(camera_url)})
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.post("/api/camera/rotate")
    def api_camera_rotate():
        try:
            return jsonify({"ok": True, "status": monitor.set_camera_rotation_clockwise()})
        except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
            sense_hat.show_status("camera-error")
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.post("/api/settings")
    def api_settings():
        payload = request.get_json(silent=True) or {}
        has_poll_interval = "poll_interval_seconds" in payload
        has_burst_count = "burst_count" in payload
        has_resolution = "resolution" in payload
        has_lighting_mode = "lighting_mode" in payload
        has_cooldown = "cooldown_seconds" in payload
        has_threshold = "motion_threshold" in payload
        if (
            not has_poll_interval
            and not has_burst_count
            and not has_resolution
            and not has_lighting_mode
            and not has_cooldown
            and not has_threshold
        ):
            return jsonify({"ok": False, "error": "At least one setting is required."}), 400

        poll_interval = payload.get("poll_interval_seconds") if has_poll_interval else None
        burst_count = payload.get("burst_count") if has_burst_count else None
        resolution = payload.get("resolution") if has_resolution else None
        lighting_mode = payload.get("lighting_mode") if has_lighting_mode else None
        cooldown = payload.get("cooldown_seconds") if has_cooldown else None
        threshold = payload.get("motion_threshold") if has_threshold else None

        if has_poll_interval and (
            isinstance(poll_interval, bool) or not isinstance(poll_interval, (int, float))
        ):
            return jsonify(
                {"ok": False, "error": "poll_interval_seconds must be a number."}
            ), 400
        if has_burst_count and (
            isinstance(burst_count, bool) or not isinstance(burst_count, int)
        ):
            return jsonify({"ok": False, "error": "burst_count must be an integer."}), 400
        if has_cooldown and (
            isinstance(cooldown, bool) or not isinstance(cooldown, (int, float))
        ):
            return jsonify({"ok": False, "error": "cooldown_seconds must be a number."}), 400
        if has_threshold and (
            isinstance(threshold, bool) or not isinstance(threshold, (int, float))
        ):
            return jsonify({"ok": False, "error": "motion_threshold must be a number."}), 400
        if has_resolution and not isinstance(resolution, str):
            return jsonify({"ok": False, "error": "resolution must be a string like 1280x720."}), 400
        if has_lighting_mode and not isinstance(lighting_mode, str):
            return jsonify({"ok": False, "error": "lighting_mode must be a preset name."}), 400

        resolution_pair: tuple[int, int] | None = None
        if has_resolution:
            match = re.fullmatch(r"\s*(\d+)x(\d+)\s*", resolution or "")
            if match is None:
                return jsonify({"ok": False, "error": "resolution must look like 1280x720."}), 400
            resolution_pair = (int(match.group(1)), int(match.group(2)))

        try:
            return jsonify(
                {
                    "ok": True,
                    "status": monitor.update_capture_settings(
                        poll_interval_seconds=float(poll_interval)
                        if has_poll_interval
                        else None,
                        burst_count=burst_count if has_burst_count else None,
                        resolution=resolution_pair,
                        lighting_mode=lighting_mode.strip() if has_lighting_mode else None,
                        cooldown_seconds=float(cooldown) if has_cooldown else None,
                        motion_threshold=float(threshold) if has_threshold else None,
                    ),
                }
            )
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.post("/api/events/delete")
    def api_events_delete():
        filenames = payload_filenames()
        if isinstance(filenames, tuple):
            return jsonify(filenames[0]), filenames[1]

        try:
            payload = monitor.delete_events(filenames)
            return jsonify({"ok": True, **payload})
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.post("/api/events/download")
    def api_events_download():
        filenames = payload_filenames()
        if isinstance(filenames, tuple):
            return jsonify(filenames[0]), filenames[1]

        try:
            event_paths = monitor.selected_event_paths(filenames)
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        archive_name = datetime.now(tz=timezone.utc).strftime("motionsense-events-%Y%m%dT%H%M%SZ.zip")
        archive_buffer = BytesIO()
        with ZipFile(archive_buffer, mode="w", compression=ZIP_DEFLATED) as archive:
            for event_path in event_paths:
                archive.write(event_path, arcname=event_path.name)
        archive_buffer.seek(0)
        return send_file(
            archive_buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=archive_name,
            max_age=0,
        )

    @app.get("/api/events")
    def api_events():
        return jsonify({"ok": True, "events": monitor.archived_events_payload()})

    @app.get("/snapshot.jpg")
    def snapshot_image():
        live = request.args.get("live", type=int) == 1
        if live:
            try:
                snapshot_file = Path(camera.capture_snapshot().path)
            except RuntimeError as exc:
                sense_hat.show_status("camera-error")
                return str(exc), 500
        else:
            snapshot_file = camera.latest_snapshot_path()
        if snapshot_file is None:
            abort(404)
        return send_jpeg(snapshot_file)

    @app.get("/events/<path:filename>")
    def event_image(filename: str):
        event_file = motion_detector.resolve_event_path(filename)
        if event_file is None:
            abort(404)
        return send_jpeg(event_file)

    return app
