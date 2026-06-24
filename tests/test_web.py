import unittest
from zipfile import ZipFile
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image

from app.camera import CameraService
from app.camera import SnapshotDetails
from app.web import create_app


class WebTests(unittest.TestCase):
    def test_status_endpoint_returns_dashboard_payload(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        response = client.get("/api/status")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("camera", payload)
        self.assertIn("sense_hat", payload)
        self.assertIn("snapshot", payload)
        self.assertIn("motion", payload)
        self.assertIn("stormwatch", payload)
        self.assertIn("timer", payload)
        self.assertIn("motion_events", payload)
        self.assertIn("network_camera_url", payload["camera"])
        self.assertIn("burst_count", payload["camera"])
        self.assertIn("rotation_degrees", payload["camera"])
        self.assertIn("camera_index", payload["camera"])
        self.assertIn("sensor_name", payload["camera"])
        self.assertIn("sensor_model", payload["camera"])
        self.assertIn("lighting", payload["camera"])
        self.assertIn("tuning", payload["camera"])
        self.assertIn("focus", payload["camera"])
        self.assertIn("options", payload["camera"]["resolution"])
        self.assertIn("white_balance_options", payload["camera"]["tuning"])

    def test_network_camera_endpoint_accepts_url(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        response = client.post("/api/camera/network", json={"url": "http://esp32-cam.local"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])

    def test_settings_endpoint_updates_poll_interval_and_burst_count(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        response = client.post(
            "/api/settings",
            json={
                "poll_interval_seconds": 5.5,
                "cooldown_seconds": 15,
                "motion_threshold": 12.5,
                "burst_count": 3,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"]["motion"]["poll_interval_seconds"], 5.5)
        self.assertEqual(payload["status"]["motion"]["cooldown_seconds"], 15.0)
        self.assertEqual(payload["status"]["motion"]["motion_threshold"], 12.5)
        self.assertEqual(payload["status"]["camera"]["burst_count"], 3)

    def test_settings_endpoint_updates_resolution(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        response = client.post(
            "/api/settings",
            json={"resolution": "3280x2464"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"]["camera"]["resolution"]["width"], 3280)
        self.assertEqual(payload["status"]["camera"]["resolution"]["height"], 2464)

    def test_settings_endpoint_updates_lighting_mode(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        response = client.post(
            "/api/settings",
            json={"lighting_mode": "fluorescent"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"]["camera"]["lighting"]["mode"], "fluorescent")

    def test_settings_endpoint_updates_direct_camera_tuning(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        response = client.post(
            "/api/settings",
            json={
                "white_balance_mode": "cloudy",
                "brightness": -0.2,
                "contrast": 1.3,
                "saturation": 0.9,
                "sharpness": 1.6,
                "denoise_mode": "off",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"]["camera"]["tuning"]["white_balance_mode"], "cloudy")
        self.assertEqual(payload["status"]["camera"]["tuning"]["brightness"], -0.2)
        self.assertEqual(payload["status"]["camera"]["tuning"]["contrast"], 1.3)
        self.assertEqual(payload["status"]["camera"]["tuning"]["saturation"], 0.9)
        self.assertEqual(payload["status"]["camera"]["tuning"]["sharpness"], 1.6)
        self.assertEqual(payload["status"]["camera"]["tuning"]["denoise_mode"], "off")

    def test_settings_endpoint_updates_camera_focus(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        response = client.post(
            "/api/settings",
            json={
                "autofocus_mode": "manual",
                "autofocus_range": "macro",
                "lens_position": 2.5,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"]["camera"]["focus"]["mode"], "manual")
        self.assertEqual(payload["status"]["camera"]["focus"]["range"], "macro")
        self.assertEqual(payload["status"]["camera"]["focus"]["lens_position"], 2.5)

    def test_rotate_camera_endpoint_updates_snapshot(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        with patch(
            "app.monitor.MonitorService.set_camera_rotation_clockwise",
            return_value={
                "camera": {"rotation_degrees": 90},
                "snapshot": {"exists": True, "url": "/snapshot.jpg"},
            },
        ):
            response = client.post("/api/camera/rotate")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"]["camera"]["rotation_degrees"], 90)

    def test_timer_start_endpoint_updates_interval(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        response = client.post("/api/timer/start", json={"interval_seconds": 120})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"]["timer"]["interval_seconds"], 120)
        self.assertTrue(payload["status"]["timer"]["armed"])
        self.assertEqual(payload["status"]["timer"]["mode"], "timer")

        stop_response = client.post("/api/timer/stop")
        self.assertEqual(stop_response.status_code, 200)
        self.assertFalse(stop_response.get_json()["status"]["timer"]["armed"])

    def test_combo_timer_start_endpoint_updates_mode_and_duration(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        response = client.post(
            "/api/timer/start",
            json={"interval_seconds": 7, "duration_seconds": 60, "mode": "combo"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"]["timer"]["interval_seconds"], 7)
        self.assertEqual(payload["status"]["timer"]["duration_seconds"], 60)
        self.assertEqual(payload["status"]["timer"]["mode"], "combo")

    def test_stormwatch_start_and_stop_endpoints(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        with patch(
            "app.monitor.MonitorService.start_stormwatch_detection",
            return_value={"stormwatch": {"armed": True}},
        ):
            response = client.post("/api/stormwatch/start")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])

        with patch(
            "app.monitor.MonitorService.stop_stormwatch_detection",
            return_value={"stormwatch": {"armed": False}},
        ):
            response = client.post("/api/stormwatch/stop")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])

    def test_stormwatch_archive_page_renders_saved_event_downloads(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        with patch(
            "app.monitor.MonitorService.stormwatch_archived_events_payload",
            return_value=[
                {
                    "event_id": "20260416T201700000000Z",
                    "detected_at": "2026-04-16T20:17:00+00:00",
                    "score": None,
                    "snapshot_path": "/opt/motionsense-pi/data/stormwatch/events/20260416T201700000000Z.jpg",
                    "snapshot_url": "/events/20260416T201700000000Z.jpg",
                    "size_bytes": 1024,
                }
            ],
        ), patch(
            "app.monitor.MonitorService.stormwatch_archived_event_day_groups",
            return_value=[
                {
                    "day_key": "2026-04-16",
                    "label": "Thursday, April 16, 2026",
                    "event_count": 1,
                }
            ],
        ):
            response = client.get("/stormwatch")

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("Stormwatch Archive", page)
        self.assertIn("Stormwatch Gallery", page)
        self.assertIn("Move Selected to Stormwatch Gallery", page)

    def test_stormwatch_gallery_page_renders_saved_gallery_downloads(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        with patch(
            "app.monitor.MonitorService.stormwatch_gallery_payload",
            return_value=[
                {
                    "event_id": "20260416T201700000000Z",
                    "detected_at": "2026-04-16T20:17:00+00:00",
                    "score": None,
                    "snapshot_path": "/opt/motionsense-pi/data/stormwatch/gallery/20260416T201700000000Z.jpg",
                    "snapshot_url": "/gallery-images/20260416T201700000000Z.jpg",
                    "size_bytes": 1024,
                }
            ],
        ):
            response = client.get("/stormwatch/gallery")

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("Stormwatch Gallery", page)
        self.assertIn("Stormwatch Archive", page)
        self.assertIn("Start Slideshow", page)

    def test_settings_endpoint_updates_stormwatch_settings(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        response = client.post(
            "/api/settings",
            json={
                "stormwatch_poll_interval_seconds": 1.5,
                "stormwatch_cooldown_seconds": 12,
                "stormwatch_score_trigger": 15.5,
                "stormwatch_hot_pixel_threshold": 55,
                "stormwatch_buffer_size": 18,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"]["stormwatch"]["poll_interval_seconds"], 1.5)
        self.assertEqual(payload["status"]["stormwatch"]["cooldown_seconds"], 12.0)
        self.assertEqual(payload["status"]["stormwatch"]["score_trigger"], 15.5)
        self.assertEqual(payload["status"]["stormwatch"]["hot_pixel_threshold"], 55)
        self.assertEqual(payload["status"]["stormwatch"]["buffer_size"], 18)

    def test_stormwatch_events_endpoint_returns_archived_events_for_selected_day(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        with patch(
            "app.monitor.MonitorService.stormwatch_archived_event_day_groups",
            return_value=[
                {
                    "day_key": "2026-04-17",
                    "label": "Friday, April 17, 2026",
                    "event_count": 2,
                }
            ],
        ), patch(
            "app.monitor.MonitorService.stormwatch_archived_events_payload",
            return_value=[
                {
                    "event_id": "20260417T201700000000Z",
                    "detected_at": "2026-04-17T20:17:00+00:00",
                    "snapshot_url": "/events/20260417T201700000000Z.jpg",
                }
            ],
        ) as archived_events_payload:
            response = client.get("/api/stormwatch/events?day=2026-04-17")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["events"][0]["event_id"], "20260417T201700000000Z")
        self.assertEqual(payload["selected_day_key"], "2026-04-17")
        archived_events_payload.assert_called_once_with(day_key="2026-04-17")

    def test_stormwatch_gallery_endpoint_returns_gallery_items(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        with patch(
            "app.monitor.MonitorService.stormwatch_gallery_payload",
            return_value=[{"event_id": "stormwatch-gallery-1", "snapshot_url": "/gallery-images/stormwatch-gallery-1.jpg"}],
        ):
            response = client.get("/api/stormwatch/gallery")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["events"][0]["event_id"], "stormwatch-gallery-1")

    def test_delete_events_endpoint_returns_updated_payload(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        with patch(
            "app.monitor.MonitorService.delete_events",
            return_value={
                "deleted_count": 1,
                "deleted_filenames": ["20260416T201700000000Z.jpg"],
                "events": [],
                "status": {"motion_events": []},
            },
        ), patch(
            "app.monitor.MonitorService.archived_event_day_groups",
            return_value=[],
        ), patch(
            "app.monitor.MonitorService.archived_events_payload",
            return_value=[],
        ):
            response = client.post(
                "/api/events/delete",
                json={"filenames": ["20260416T201700000000Z.jpg"], "day_key": "2026-04-16"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["deleted_count"], 1)

    def test_move_events_to_gallery_endpoint_returns_updated_payload(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        with patch(
            "app.monitor.MonitorService.move_events_to_gallery",
            return_value={
                "moved_count": 1,
                "moved_filenames": ["20260416T201700000000Z.jpg"],
                "events": [],
                "gallery": [{"event_id": "20260416T201700000000Z"}],
                "status": {"motion_events": []},
            },
        ), patch(
            "app.monitor.MonitorService.archived_event_day_groups",
            return_value=[],
        ), patch(
            "app.monitor.MonitorService.archived_events_payload",
            return_value=[],
        ):
            response = client.post(
                "/api/events/move-to-gallery",
                json={"filenames": ["20260416T201700000000Z.jpg"], "day_key": "2026-04-16"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["moved_count"], 1)

    def test_events_endpoint_returns_archived_events_for_selected_day(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        with patch(
            "app.monitor.MonitorService.archived_event_day_groups",
            return_value=[
                {
                    "day_key": "2026-04-17",
                    "label": "Friday, April 17, 2026",
                    "event_count": 2,
                },
                {
                    "day_key": "2026-04-16",
                    "label": "Thursday, April 16, 2026",
                    "event_count": 1,
                },
            ],
        ), patch(
            "app.monitor.MonitorService.archived_events_payload",
            return_value=[
                {
                    "event_id": "20260416T201700000000Z",
                    "detected_at": "2026-04-16T20:17:00+00:00",
                    "snapshot_url": "/events/20260416T201700000000Z.jpg",
                }
            ],
        ) as archived_events_payload:
            response = client.get("/api/events?day=2026-04-16")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["events"][0]["event_id"], "20260416T201700000000Z")
        self.assertEqual(payload["selected_day_key"], "2026-04-16")
        self.assertEqual(payload["day_groups"][0]["day_key"], "2026-04-17")
        self.assertEqual(payload["day_groups"][1]["event_count"], 1)
        archived_events_payload.assert_called_once_with(day_key="2026-04-16")

    def test_gallery_endpoint_returns_gallery_items(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        with patch(
            "app.monitor.MonitorService.gallery_payload",
            return_value=[{"event_id": "gallery-1", "snapshot_url": "/gallery-images/gallery-1.jpg"}],
        ):
            response = client.get("/api/gallery")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["events"][0]["event_id"], "gallery-1")

    def test_events_download_endpoint_returns_zip_bundle(self):
        with TemporaryDirectory() as temp_dir:
            event_path = Path(temp_dir) / "20260416T201700000000Z.jpg"
            Image.new("RGB", (320, 240), color="purple").save(event_path, format="JPEG")

            app = create_app(start_detector=False)
            client = app.test_client()

            with patch("app.monitor.MonitorService.selected_event_paths", return_value=[event_path]):
                response = client.post(
                    "/api/events/download",
                    json={"filenames": [event_path.name]},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/zip")
        with ZipFile(BytesIO(response.data)) as archive:
            self.assertEqual(archive.namelist(), [event_path.name])

    def test_gallery_download_endpoint_returns_zip_bundle(self):
        with TemporaryDirectory() as temp_dir:
            gallery_path = Path(temp_dir) / "20260416T201700000000Z.jpg"
            Image.new("RGB", (320, 240), color="orange").save(gallery_path, format="JPEG")

            app = create_app(start_detector=False)
            client = app.test_client()

            with patch("app.monitor.MonitorService.selected_gallery_paths", return_value=[gallery_path]):
                response = client.post(
                    "/api/gallery/download",
                    json={"filenames": [gallery_path.name]},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/zip")
        with ZipFile(BytesIO(response.data)) as archive:
            self.assertEqual(archive.namelist(), [gallery_path.name])

    def test_snapshot_endpoint_can_return_scaled_preview(self):
        with TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "latest.jpg"
            image = Image.new("RGB", (1280, 720), color="navy")
            image.save(snapshot_path, format="JPEG", quality=90)

            app = create_app(start_detector=False)

            with patch.object(CameraService, "latest_snapshot_path", return_value=snapshot_path):
                client = app.test_client()
                response = client.get("/snapshot.jpg?max_w=304&max_h=172&quality=60")

            self.assertEqual(response.status_code, 200)
            with Image.open(BytesIO(response.data)) as preview:
                self.assertLessEqual(preview.width, 304)
                self.assertLessEqual(preview.height, 172)

    def test_snapshot_endpoint_can_capture_live_image(self):
        with TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "latest.jpg"
            image = Image.new("RGB", (640, 480), color="green")
            image.save(snapshot_path, format="JPEG", quality=85)

            app = create_app(start_detector=False)

            with patch.object(
                CameraService,
                "capture_snapshot",
                return_value=SnapshotDetails(
                    exists=True,
                    path=str(snapshot_path),
                    modified_at="2026-04-15T22:30:00+00:00",
                    size_bytes=snapshot_path.stat().st_size,
                ),
            ) as capture_snapshot:
                client = app.test_client()
                response = client.get("/snapshot.jpg?live=1&max_w=304&max_h=172&quality=60")

            self.assertEqual(response.status_code, 200)
            capture_snapshot.assert_called_once_with()

    def test_snapshot_endpoint_preview_uses_focus_preview_resolution(self):
        with TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "latest.jpg"
            image = Image.new("RGB", (640, 480), color="teal")
            image.save(snapshot_path, format="JPEG", quality=85)

            app = create_app(start_detector=False)

            with patch.object(CameraService, "focus_preview_resolution", return_value=(640, 480)), patch.object(
                CameraService,
                "capture_image",
                return_value=SnapshotDetails(
                    exists=True,
                    path=str(snapshot_path),
                    modified_at="2026-04-15T22:30:00+00:00",
                    size_bytes=snapshot_path.stat().st_size,
                ),
            ) as capture_image:
                client = app.test_client()
                response = client.get("/snapshot.jpg?live=1&preview=1&max_w=304&max_h=172&quality=60")

            self.assertEqual(response.status_code, 200)
            capture_image.assert_called_once_with(
                output_path=Path(app.root_path).parent / "data" / "latest.jpg",
                width=640,
                height=480,
                quality=60,
            )

    def test_archive_page_renders_saved_event_downloads(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        archived_events = [
            {
                "event_id": "20260416T201700000000Z",
                "detected_at": "2026-04-16T20:17:00+00:00",
                "score": None,
                "snapshot_path": "/opt/motionsense-pi/data/events/20260416T201700000000Z.jpg",
                "snapshot_url": "/events/20260416T201700000000Z.jpg",
                "size_bytes": 1024,
            }
        ]

        with patch(
            "app.monitor.MonitorService.archived_events_payload",
            return_value=archived_events,
        ), patch(
            "app.monitor.MonitorService.archived_event_day_groups",
            return_value=[
                {
                    "day_key": "2026-04-16",
                    "label": "Thursday, April 16, 2026",
                    "event_count": 1,
                }
            ],
        ):
            response = client.get("/archive")

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("Event Archive", page)
        self.assertIn("Gallery", page)
        self.assertIn("Move Selected to Gallery", page)
        self.assertIn("Download Selected", page)
        self.assertIn("Delete Selected", page)
        self.assertIn("Archive Day", page)
        self.assertIn("Select to Move", page)
        self.assertIn("Selected for Move", page)

    def test_index_page_renders_focus_preview_controls(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("Start Focus Preview", page)
        self.assertIn("Focus preview grabs fresh snapshots", page)
        self.assertIn("Pi Camera Focus", page)

    def test_gallery_page_renders_saved_gallery_downloads(self):
        app = create_app(start_detector=False)
        client = app.test_client()

        gallery_events = [
            {
                "event_id": "20260416T201700000000Z",
                "detected_at": "2026-04-16T20:17:00+00:00",
                "score": None,
                "snapshot_path": "/opt/motionsense-pi/data/gallery/20260416T201700000000Z.jpg",
                "snapshot_url": "/gallery-images/20260416T201700000000Z.jpg",
                "size_bytes": 1024,
            }
        ]

        with patch("app.monitor.MonitorService.gallery_payload", return_value=gallery_events):
            response = client.get("/gallery")

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("Gallery", page)
        self.assertIn("Browse Archive", page)
        self.assertIn("Start Slideshow", page)
        self.assertIn("Download Selected", page)


if __name__ == "__main__":
    unittest.main()
