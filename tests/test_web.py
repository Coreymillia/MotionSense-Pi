import unittest

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
        self.assertIn("motion_events", payload)


if __name__ == "__main__":
    unittest.main()
