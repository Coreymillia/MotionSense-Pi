from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.camera import CameraService, CameraSource


class CameraServiceTests(unittest.TestCase):
    def test_prefers_pi_camera_and_allows_switching_to_usb(self):
        service = CameraService(snapshot_path=Path("/tmp/latest.jpg"))
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
        service = CameraService(snapshot_path=Path("/tmp/latest.jpg"))
        service._selected_source_id = "usb-video1"
        service._selected_source_name = "USB Camera (video1)"

        with patch.object(service, "_probe_pi_source", return_value=None), patch.object(
            service, "_probe_usb_sources", return_value=[]
        ):
            payload = service.list_sources()

            self.assertFalse(payload[0]["available"])
            self.assertTrue(payload[0]["selected"])

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


if __name__ == "__main__":
    unittest.main()
