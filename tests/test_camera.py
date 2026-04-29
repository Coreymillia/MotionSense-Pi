from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError

from app.camera import CameraService, CameraSource


class CameraServiceTests(unittest.TestCase):
    def test_prefers_pi_camera_and_allows_switching_to_usb(self):
        with TemporaryDirectory() as temp_dir:
            service = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")
            pi_source = CameraSource(
                source_id="pi-camera",
                label="Pi Camera",
                kind="pi",
                available=True,
                backend="libcamera",
                command="/usr/bin/rpicam-still",
            )
            usb_source = CameraSource(
                source_id="usb-video1",
                label="USB Camera (video1)",
                kind="usb",
                available=True,
                backend="v4l2",
                command="/usr/bin/v4l2-ctl",
                device="/dev/video1",
            )

            with patch.object(service, "_probe_pi_source", return_value=pi_source), patch.object(
                service, "_probe_usb_sources", return_value=[usb_source]
            ):
                self.assertEqual(service.selected_source_id(), "pi-camera")

                service.set_active_source("usb-video1")

                payload = service.list_sources()
                selected = next(item for item in payload if item["selected"])
                self.assertEqual(selected["source_id"], "usb-video1")
                self.assertEqual(service.active_capture_target(), "/dev/video1")

    def test_reports_missing_selected_source(self):
        with TemporaryDirectory() as temp_dir:
            service = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")
            service._selected_source_id = "usb-video1"
            service._selected_source_name = "USB Camera (video1)"

            with patch.object(service, "_probe_pi_source", return_value=None), patch.object(
                service, "_probe_usb_sources", return_value=[]
            ):
                payload = service.list_sources()

                self.assertFalse(payload[0]["available"])
                self.assertTrue(payload[0]["selected"])

    def test_adds_configured_network_source(self):
        with TemporaryDirectory() as temp_dir:
            service = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")
            service.set_network_camera_url("esp32-cam.local")

            with patch.object(service, "_probe_pi_source", return_value=None), patch.object(
                service, "_probe_usb_sources", return_value=[]
            ), patch("app.camera.urlopen", side_effect=URLError("offline")):
                payload = service.list_sources()

            self.assertEqual(payload[0]["source_id"], "esp32-cam")
            self.assertEqual(payload[0]["base_url"], "http://esp32-cam.local")

    def test_caches_source_probe_results_within_status_window(self):
        with TemporaryDirectory() as temp_dir:
            service = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")
            pi_source = CameraSource(
                source_id="pi-camera",
                label="Pi Camera",
                kind="pi",
                available=True,
                backend="libcamera",
                command="/usr/bin/rpicam-still",
            )

            with patch.object(service, "_probe_pi_source", return_value=pi_source) as probe_pi, patch.object(
                service, "_probe_usb_sources", return_value=[]
            ) as probe_usb, patch.object(service, "_probe_network_source", return_value=None) as probe_network:
                service.selected_source_id()
                service.selected_source_name()
                service.list_sources()
                service.is_available()

            self.assertEqual(probe_pi.call_count, 1)
            self.assertEqual(probe_usb.call_count, 1)
            self.assertEqual(probe_network.call_count, 1)

    def test_usb_capture_path_writes_output(self):
        with TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "frame.jpg"
            service = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")
            usb_source = CameraSource(
                source_id="usb-video1",
                label="USB Camera (video1)",
                kind="usb",
                available=True,
                backend="v4l2",
                command="/usr/bin/v4l2-ctl",
                device="/dev/video1",
            )

            with patch.object(service, "active_source", return_value=usb_source), patch.object(
                service, "_capture_usb_image", side_effect=lambda device, path, width, height: path.write_bytes(b"jpg")
            ):
                details = service.capture_image(output_path=output_path, width=640, height=480)

            self.assertTrue(details.exists)
            self.assertEqual(details.path, str(output_path))

    def test_network_capture_writes_output(self):
        with TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "frame.jpg"
            service = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")
            network_source = CameraSource(
                source_id="esp32-cam",
                label="ESP32-CAM",
                kind="network",
                available=True,
                backend="http",
                base_url="http://esp32-cam.local",
            )
            service._network_camera_url = "http://esp32-cam.local"

            with patch.object(service, "active_source", return_value=network_source), patch.object(
                service, "_capture_network_image", side_effect=lambda path: path.write_bytes(b"jpg")
            ):
                details = service.capture_image(output_path=output_path, width=640, height=480)

            self.assertTrue(details.exists)
            self.assertEqual(details.path, str(output_path))

    def test_extract_last_jpeg_frame_returns_last_frame(self):
        first = b"\xff\xd8first-frame\xff\xd9"
        second = b"\xff\xd8second-frame\xff\xd9"

        extracted = CameraService._extract_last_jpeg_frame(first + second)

        self.assertEqual(extracted, second)

    def test_burst_count_persists_in_camera_config(self):
        with TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "latest.jpg"
            service = CameraService(snapshot_path=snapshot_path)

            service.set_burst_count(4)

            reloaded = CameraService(snapshot_path=snapshot_path)
            self.assertEqual(reloaded.burst_count(), 4)

    def test_capture_snapshot_burst_repeats_requested_count(self):
        with TemporaryDirectory() as temp_dir:
            service = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")

            with patch.object(service, "capture_snapshot", return_value=service.snapshot_details()) as capture:
                snapshots = service.capture_snapshot_burst(count=3)

            self.assertEqual(len(snapshots), 3)
            self.assertEqual(capture.call_count, 3)

    def test_resolution_persists_in_camera_config(self):
        with TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "latest.jpg"
            service = CameraService(snapshot_path=snapshot_path)
            service._resolution_options = (
                Mock(width=640, height=480, label="640 x 480"),
                Mock(width=1280, height=720, label="1280 x 720"),
                Mock(width=3280, height=2464, label="3280 x 2464 (Max)"),
            )

            service.set_resolution(3280, 2464)

            reloaded = CameraService(snapshot_path=snapshot_path)
            reloaded._resolution_options = service._resolution_options
            reloaded._load_config()
            self.assertEqual((reloaded.width, reloaded.height), (3280, 2464))

    def test_resolution_options_include_current_resolution(self):
        with TemporaryDirectory() as temp_dir:
            service = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")
            service.width = 2000
            service.height = 1500

            with patch.object(service, "_probe_resolution_pairs", return_value=[(640, 480), (3280, 2464)]):
                options = service.resolution_options()

            self.assertIn((2000, 1500), {(option.width, option.height) for option in options})


if __name__ == "__main__":
    unittest.main()
