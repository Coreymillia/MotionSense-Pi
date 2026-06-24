from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError

from PIL import Image

from app.camera import CameraService, CameraSource, PiCameraInfo


class CameraServiceTests(unittest.TestCase):
    def test_prefers_pi_camera_and_allows_switching_to_usb(self):
        with TemporaryDirectory() as temp_dir:
            service = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")
            pi_source = CameraSource(
                source_id="pi-camera-0",
                label="Pi Camera 1 (Camera Module v2)",
                kind="pi",
                available=True,
                backend="libcamera",
                command="/usr/bin/rpicam-still",
                camera_index=0,
                sensor_name="imx219",
                model_name="Camera Module v2",
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

            with patch.object(service, "_probe_pi_sources", return_value=[pi_source]), patch.object(
                service, "_probe_usb_sources", return_value=[usb_source]
            ):
                self.assertEqual(service.selected_source_id(), "pi-camera-0")

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

            with patch.object(service, "_probe_pi_sources", return_value=[]), patch.object(
                service, "_probe_usb_sources", return_value=[]
            ):
                payload = service.list_sources()

                self.assertFalse(payload[0]["available"])
                self.assertTrue(payload[0]["selected"])

    def test_adds_configured_network_source(self):
        with TemporaryDirectory() as temp_dir:
            service = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")
            service.set_network_camera_url("esp32-cam.local")

            with patch.object(service, "_probe_pi_sources", return_value=[]), patch.object(
                service, "_probe_usb_sources", return_value=[]
            ), patch("app.camera.urlopen", side_effect=URLError("offline")):
                payload = service.list_sources()

            self.assertEqual(payload[0]["source_id"], "esp32-cam")
            self.assertEqual(payload[0]["base_url"], "http://esp32-cam.local")

    def test_caches_source_probe_results_within_status_window(self):
        with TemporaryDirectory() as temp_dir:
            service = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")
            pi_source = CameraSource(
                source_id="pi-camera-0",
                label="Pi Camera 1 (Camera Module v2)",
                kind="pi",
                available=True,
                backend="libcamera",
                command="/usr/bin/rpicam-still",
                camera_index=0,
                sensor_name="imx219",
                model_name="Camera Module v2",
            )

            with patch.object(service, "_probe_pi_sources", return_value=[pi_source]) as probe_pi, patch.object(
                service, "_probe_usb_sources", return_value=[]
            ) as probe_usb, patch.object(service, "_probe_network_source", return_value=None) as probe_network:
                service.selected_source_id()
                service.selected_source_name()
                service.list_sources()
                service.is_available()

            self.assertEqual(probe_pi.call_count, 1)
            self.assertEqual(probe_usb.call_count, 1)
            self.assertEqual(probe_network.call_count, 1)

    def test_parse_pi_camera_listing_extracts_multiple_cameras(self):
        parsed = CameraService._parse_pi_camera_listing(
            "\n".join(
                [
                    "Available cameras",
                    "0 : ov5647 [Arducam OV5647]",
                    "    /base/soc/i2c0mux/i2c@1/ov5647@36",
                    "    Modes: 640x480 1280x720 2592x1944",
                    "1 : imx708",
                    "    /base/soc/i2c0mux/i2c@0/imx708@1a",
                    "    Model: Camera Module 3",
                    "    Mode 0: 2304x1296",
                    "    Mode 1: 4608x2592",
                ]
            )
        )

        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0].sensor_name, "ov5647")
        self.assertEqual(parsed[0].model_name, "Arducam OV5647")
        self.assertIn((2592, 1944), parsed[0].resolutions)
        self.assertEqual(parsed[1].camera_index, 1)
        self.assertEqual(parsed[1].model_name, "Camera Module 3")
        self.assertIn((4608, 2592), parsed[1].resolutions)

    def test_lists_each_detected_pi_camera_as_a_selectable_source(self):
        with TemporaryDirectory() as temp_dir:
            service = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")

            with patch.object(
                service,
                "_probe_pi_camera_infos",
                return_value=[
                    PiCameraInfo(
                        camera_index=0,
                        sensor_name="ov5647",
                        model_name="Arducam OV5647",
                        device_path="/base/ov5647@36",
                        resolutions=((640, 480), (2592, 1944)),
                    ),
                    PiCameraInfo(
                        camera_index=1,
                        sensor_name="imx708",
                        model_name="Camera Module 3",
                        device_path="/base/imx708@1a",
                        resolutions=((2304, 1296), (4608, 2592)),
                    ),
                ],
            ), patch.object(service, "_probe_usb_sources", return_value=[]):
                payload = service.list_sources(refresh=True)

            self.assertEqual(
                [item["source_id"] for item in payload],
                ["pi-camera-0", "pi-camera-1"],
            )
            self.assertEqual(payload[0]["model_name"], "Arducam OV5647")
            self.assertEqual(payload[1]["camera_index"], 1)

    def test_switching_pi_sources_uses_supported_resolution_for_selected_camera(self):
        with TemporaryDirectory() as temp_dir:
            service = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")
            service.width = 3280
            service.height = 2464

            with patch.object(
                service,
                "_probe_pi_camera_infos",
                return_value=[
                    PiCameraInfo(
                        camera_index=0,
                        sensor_name="ov5647",
                        model_name="Arducam OV5647",
                        device_path="/base/ov5647@36",
                        resolutions=((1280, 720), (2592, 1944)),
                    ),
                    PiCameraInfo(
                        camera_index=1,
                        sensor_name="imx708",
                        model_name="Camera Module 3",
                        device_path="/base/imx708@1a",
                        resolutions=((2304, 1296), (4608, 2592)),
                    ),
                ],
            ), patch.object(service, "_probe_usb_sources", return_value=[]):
                service.set_active_source("pi-camera-1")

            self.assertEqual((service.width, service.height), (2304, 1296))

    def test_pi_capture_command_selects_specific_camera_index(self):
        with TemporaryDirectory() as temp_dir:
            service = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")
            service.rpicam_executable = "/usr/bin/rpicam-still"

            with patch("app.camera.subprocess.run") as run:
                service._capture_pi_image(
                    Path(temp_dir) / "frame.jpg",
                    width=640,
                    height=480,
                    quality=90,
                    camera_index=1,
                )

            command = run.call_args.args[0]
            self.assertEqual(command[command.index("--camera") + 1], "1")

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

            with patch.object(service, "active_source", return_value=None):
                options = service.resolution_options()

            self.assertIn((2000, 1500), {(option.width, option.height) for option in options})

    def test_rotation_persists_in_camera_config(self):
        with TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "latest.jpg"
            service = CameraService(snapshot_path=snapshot_path)

            service.rotate_clockwise()
            service.rotate_clockwise()

            reloaded = CameraService(snapshot_path=snapshot_path)
            self.assertEqual(reloaded.rotation_degrees(), 180)

    def test_focus_preview_resolution_prefers_best_mode_under_720p(self):
        with TemporaryDirectory() as temp_dir:
            service = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")
            service._resolution_options = (
                Mock(width=640, height=480, label="640 x 480"),
                Mock(width=1280, height=720, label="1280 x 720"),
                Mock(width=1640, height=1232, label="1640 x 1232"),
            )
            service._resolution_options_cache_key = None

            self.assertEqual(service.focus_preview_resolution(), (1280, 720))

    def test_lighting_mode_persists_in_camera_config(self):
        with TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "latest.jpg"
            service = CameraService(snapshot_path=snapshot_path)

            service.set_lighting_mode("fluorescent")

            reloaded = CameraService(snapshot_path=snapshot_path)
            self.assertEqual(reloaded.lighting_mode(), "fluorescent")

    def test_direct_tuning_persists_in_camera_config(self):
        with TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "latest.jpg"
            service = CameraService(snapshot_path=snapshot_path)

            service.set_white_balance_mode("cloudy")
            service.set_brightness(-0.2)
            service.set_contrast(1.3)
            service.set_saturation(0.85)
            service.set_sharpness(1.6)
            service.set_denoise_mode("off")

            reloaded = CameraService(snapshot_path=snapshot_path)
            payload = reloaded.tuning_payload()
            self.assertEqual(payload["white_balance_mode"], "cloudy")
            self.assertEqual(payload["brightness"], -0.2)
            self.assertEqual(payload["contrast"], 1.3)
            self.assertEqual(payload["saturation"], 0.85)
            self.assertEqual(payload["sharpness"], 1.6)
            self.assertEqual(payload["denoise_mode"], "off")

    def test_pi_capture_command_uses_selected_lighting_profile(self):
        with TemporaryDirectory() as temp_dir:
            service = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")
            service.rpicam_executable = "/usr/bin/rpicam-still"
            service.set_lighting_mode("low-light")

            with patch("app.camera.subprocess.run") as run:
                service._capture_pi_image(Path(temp_dir) / "frame.jpg", width=640, height=480, quality=90)

            command = run.call_args.args[0]
            self.assertIn("--awb", command)
            self.assertIn("auto", command)
            self.assertIn("--metering", command)
            self.assertIn("average", command)
            self.assertIn("--denoise", command)
            self.assertIn("cdn_hq", command)

    def test_pi_capture_command_uses_direct_tuning_values(self):
        with TemporaryDirectory() as temp_dir:
            service = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")
            service.rpicam_executable = "/usr/bin/rpicam-still"
            service.set_lighting_mode("daylight")
            service.set_white_balance_mode("cloudy")
            service.set_brightness(-0.2)
            service.set_contrast(1.3)
            service.set_saturation(0.9)
            service.set_sharpness(1.6)
            service.set_denoise_mode("off")

            with patch("app.camera.subprocess.run") as run:
                service._capture_pi_image(Path(temp_dir) / "frame.jpg", width=640, height=480, quality=90)

            command = run.call_args.args[0]
            self.assertEqual(command[command.index("--awb") + 1], "cloudy")
            self.assertEqual(command[command.index("--brightness") + 1], "-0.2")
            self.assertEqual(command[command.index("--contrast") + 1], "1.3")
            self.assertEqual(command[command.index("--saturation") + 1], "0.9")
            self.assertEqual(command[command.index("--sharpness") + 1], "1.6")
            self.assertEqual(command[command.index("--denoise") + 1], "off")

    def test_capture_image_applies_configured_rotation(self):
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
            service.set_rotation_degrees(90)

            def write_test_image(device, path, width, height):
                Image.new("RGB", (width, height), color="orange").save(path, format="JPEG")

            with patch.object(service, "active_source", return_value=usb_source), patch.object(
                service, "_capture_usb_image", side_effect=write_test_image
            ):
                service.capture_image(output_path=output_path, width=640, height=480)

            with Image.open(output_path) as saved_image:
                self.assertEqual((saved_image.width, saved_image.height), (480, 640))

    def test_lighting_payload_reports_pi_support(self):
        with TemporaryDirectory() as temp_dir:
            service = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")
            pi_source = CameraSource(
                source_id="pi-camera-0",
                label="Pi Camera 1 (Camera Module v2)",
                kind="pi",
                available=True,
                backend="libcamera",
                command="/usr/bin/rpicam-still",
                camera_index=0,
                sensor_name="imx219",
                model_name="Camera Module v2",
            )

            with patch.object(service, "active_source", return_value=pi_source):
                payload = service.lighting_payload()

            self.assertTrue(payload["supported"])
            self.assertEqual(payload["mode"], "auto")
            self.assertGreaterEqual(len(payload["options"]), 4)

    def test_focus_payload_reports_imx708_support(self):
        with TemporaryDirectory() as temp_dir:
            service = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")
            pi_source = CameraSource(
                source_id="pi-camera-0",
                label="Pi Camera 1 (Camera Module 3)",
                kind="pi",
                available=True,
                backend="libcamera",
                command="/usr/bin/rpicam-still",
                camera_index=0,
                sensor_name="imx708",
                model_name="Camera Module 3",
            )

            with patch.object(service, "active_source", return_value=pi_source):
                payload = service.focus_payload()

            self.assertTrue(payload["supported"])
            self.assertEqual(payload["mode"], "on-capture")
            self.assertEqual(payload["range"], "normal")
            self.assertEqual(payload["lens_position"], 1.0)

    def test_focus_settings_persist_in_camera_config(self):
        with TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "latest.jpg"
            service = CameraService(snapshot_path=snapshot_path)

            service.set_autofocus_mode("manual")
            service.set_autofocus_range("macro")
            service.set_lens_position(2.5)

            reloaded = CameraService(snapshot_path=snapshot_path)
            payload = reloaded.focus_payload()
            self.assertEqual(payload["mode"], "manual")
            self.assertEqual(payload["range"], "macro")
            self.assertEqual(payload["lens_position"], 2.5)

    def test_pi_capture_command_uses_autofocus_settings_for_imx708(self):
        with TemporaryDirectory() as temp_dir:
            service = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")
            service.rpicam_executable = "/usr/bin/rpicam-still"
            service.set_autofocus_mode("continuous")
            service.set_autofocus_range("macro")
            pi_source = CameraSource(
                source_id="pi-camera-0",
                label="Pi Camera 1 (Camera Module 3)",
                kind="pi",
                available=True,
                backend="libcamera",
                command="/usr/bin/rpicam-still",
                camera_index=0,
                sensor_name="imx708",
                model_name="Camera Module 3",
            )

            with patch("app.camera.subprocess.run") as run:
                service._capture_pi_image(
                    Path(temp_dir) / "frame.jpg",
                    width=640,
                    height=480,
                    quality=90,
                    camera_index=0,
                    source=pi_source,
                )

            command = run.call_args.args[0]
            self.assertEqual(command[command.index("--autofocus-mode") + 1], "continuous")
            self.assertEqual(command[command.index("--autofocus-range") + 1], "macro")
            self.assertNotIn("--autofocus-on-capture", command)

    def test_pi_capture_command_uses_manual_lens_position_for_imx708(self):
        with TemporaryDirectory() as temp_dir:
            service = CameraService(snapshot_path=Path(temp_dir) / "latest.jpg")
            service.rpicam_executable = "/usr/bin/rpicam-still"
            service.set_autofocus_mode("manual")
            service.set_lens_position(3.2)
            pi_source = CameraSource(
                source_id="pi-camera-0",
                label="Pi Camera 1 (Camera Module 3)",
                kind="pi",
                available=True,
                backend="libcamera",
                command="/usr/bin/rpicam-still",
                camera_index=0,
                sensor_name="imx708",
                model_name="Camera Module 3",
            )

            with patch("app.camera.subprocess.run") as run:
                service._capture_pi_image(
                    Path(temp_dir) / "frame.jpg",
                    width=640,
                    height=480,
                    quality=90,
                    camera_index=0,
                    source=pi_source,
                )

            command = run.call_args.args[0]
            self.assertEqual(command[command.index("--autofocus-mode") + 1], "manual")
            self.assertEqual(command[command.index("--lens-position") + 1], "3.2")
            self.assertNotIn("--autofocus-range", command)
            self.assertNotIn("--autofocus-on-capture", command)


if __name__ == "__main__":
    unittest.main()
