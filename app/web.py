from __future__ import annotations

from pathlib import Path
import subprocess

from flask import Flask, abort, jsonify, render_template, request, send_file

from app.camera import CameraService
from app.monitor import MonitorService
from app.motion import MotionDetector
from app.sensehat import SenseHatService


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
    )
    monitor = MonitorService(
        camera=camera,
        sense_hat=sense_hat,
        motion_detector=motion_detector,
    )
    if start_detector:
        motion_detector.start()

    @app.get("/")
    def index() -> str:
        return render_template("index.html", status=monitor.status_payload())

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

    @app.get("/snapshot.jpg")
    def snapshot_image():
        snapshot_file = camera.latest_snapshot_path()
        if snapshot_file is None:
            abort(404)
        return send_file(snapshot_file, mimetype="image/jpeg", max_age=0)

    @app.get("/events/<path:filename>")
    def event_image(filename: str):
        event_file = motion_detector.resolve_event_path(filename)
        if event_file is None:
            abort(404)
        return send_file(event_file, mimetype="image/jpeg", max_age=0)

    return app
