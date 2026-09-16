"""Transport must stay local, preserve frame age, and fail closed on stale data."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from real_gaze import GazePublisher, validate_gaze


def tracking(**updates):
    return {"enabled": True, "active": True, "calibrated": True,
            "x": .25, "y": .75, "quality": .9, "eyes": 2, "reason": "tracking",
            "calibration_screen": {"width": 1920, "height": 1080}, **updates}


def wait_until(predicate, timeout=2.):
    end = time.monotonic()+timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(.005)
    return False


class LocalServer:
    def __init__(self, status=200, block=None):
        self.packets = []
        self.requests = []
        self.status = status
        self.block = block
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                packet = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fixture.packets.append(packet)
                fixture.requests.append(self.path)
                if fixture.block:
                    fixture.block.wait(.3)
                self.send_response(fixture.status)
                if fixture.status == 302:
                    self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/escaped")
                self.end_headers()
                response = {**packet, "connected": True, "age_ms": packet["sample_age_ms"]}
                try:
                    self.wfile.write(json.dumps(response).encode())
                except OSError:
                    pass

            def do_GET(self):
                fixture.requests.append(self.path)
                self.send_response(200)
                self.end_headers()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": .02}, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        if self.block:
            self.block.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(1.)

    def client(self):
        return GazePublisher(self.server.server_port)


class RealGazeValidationTests(unittest.TestCase):
    def test_rejects_unknown_fields_nonfinite_coordinates_and_bad_metadata(self):
        for updates in ({"image": "not permitted"}, {"x": float("nan")},
                        {"y": float("inf")}, {"x": True}, {"y": -1},
                        {"active": 1}, {"eyes": True}, {"eyes": 3},
                        {"sample_age_ms": -1}, {"reason": "made_up"},
                        {"calibration_screen": {"width": 0, "height": 1080}},
                        {"calibration_screen": {"width": True, "height": 1080}}):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                validate_gaze(tracking(**updates))

    def test_active_requires_enabled_calibration_quality_and_tracking_reason(self):
        for updates, reason in (({"enabled": False}, "disabled"),
                                ({"calibrated": False}, "uncalibrated"),
                                ({"calibration_screen": None}, "uncalibrated"),
                                ({"quality": .49}, "eye_lost"),
                                ({"reason": "synthetic"}, "synthetic"),
                                ({"reason": "calibrating"}, "calibrating")):
            with self.subTest(updates=updates):
                value = validate_gaze(tracking(**updates))
                self.assertFalse(value["active"])
                self.assertEqual(value["reason"], reason)

    def test_capture_and_queue_age_both_count_without_renewing_frame(self):
        client = GazePublisher()
        with patch("real_gaze.time.monotonic", return_value=10.):
            client.update(tracking(), capture_stamp=9.9)
        with patch("real_gaze.time.monotonic", return_value=10.1):
            packet = client._packet()
        self.assertAlmostEqual(packet["sample_age_ms"], 200.)
        self.assertTrue(packet["active"])
        with patch("real_gaze.time.monotonic", return_value=10.2):
            packet = client._packet()
        self.assertAlmostEqual(packet["sample_age_ms"], 300.)
        self.assertFalse(packet["active"])
        self.assertEqual(packet["reason"], "stale_frame")

    def test_same_capture_stamp_cannot_be_kept_alive_by_repeated_updates(self):
        client = GazePublisher()
        with patch("real_gaze.time.monotonic", return_value=10.):
            client.update(tracking(), capture_stamp=10.)
        with patch("real_gaze.time.monotonic", return_value=10.3):
            client.update(tracking(), capture_stamp=10.)
            packet = client._packet()
        self.assertFalse(packet["active"])
        self.assertGreaterEqual(packet["sample_age_ms"], 250)

    def test_future_capture_timestamp_is_rejected(self):
        with patch("real_gaze.time.monotonic", return_value=10.), self.assertRaises(ValueError):
            GazePublisher().update(tracking(), capture_stamp=11.)

    def test_copied_calibration_metadata_cannot_be_mutated_after_update(self):
        client = GazePublisher()
        fields = tracking()
        client.update(fields)
        fields["calibration_screen"]["width"] = 10
        self.assertEqual(client._packet()["calibration_screen"]["width"], 1920)

    def test_port_cannot_select_a_remote_host(self):
        for port in (True, 0, 65536, "https://example.com"):
            with self.subTest(port=port), self.assertRaises((ValueError, TypeError)):
                GazePublisher(port)
        self.assertEqual(GazePublisher(8878).url, "http://127.0.0.1:8878/api/gaze")


class RealGazeTransportTests(unittest.TestCase):
    def stop_client(self, client):
        client.stop()
        if client._thread:
            client._thread.join(1.)

    def test_real_payload_freshness_and_final_deactivation(self):
        with LocalServer() as server:
            client = server.client()
            try:
                client.update(tracking(), capture_stamp=time.monotonic())
                client.start()
                self.assertTrue(wait_until(lambda: client.snapshot()["online"]))
                self.assertTrue(server.packets[0]["active"])
                self.assertFalse(server.packets[0]["simulated"])
                self.assertEqual(server.packets[0]["source"], "camera")
                self.assertEqual((server.packets[0]["x"], server.packets[0]["y"]), (.25, .75))
                self.assertTrue(wait_until(lambda: any(p["reason"] == "stale_frame" for p in server.packets)))
                self.assertFalse(client.snapshot()["active"])
                self.assertTrue(client.snapshot()["online"])
            finally:
                self.stop_client(client)
            self.assertEqual(server.packets[-1]["reason"], "disabled")
            self.assertFalse(server.packets[-1]["enabled"])
            self.assertFalse(server.packets[-1]["active"])
            seq = [packet["seq"] for packet in server.packets]
            self.assertEqual(seq, sorted(set(seq)))

    def test_http_wait_does_not_block_ui_updates_and_latest_snapshot_wins(self):
        gate = threading.Event()
        with LocalServer(block=gate) as server:
            client = server.client()
            try:
                client.update(tracking())
                client.start()
                self.assertTrue(wait_until(lambda: len(server.packets) == 1))
                started = time.monotonic()
                for x in (.3, .4, .7):
                    client.update(tracking(x=x))
                self.assertLess(time.monotonic()-started, .1)
                gate.set()
                self.assertTrue(wait_until(lambda: len(server.packets) >= 2))
                self.assertEqual(server.packets[1]["x"], .7)
                self.assertNotIn(.3, [p["x"] for p in server.packets])
                self.assertNotIn(.4, [p["x"] for p in server.packets])
            finally:
                self.stop_client(client)

    def test_old_companion_reports_english_repair_message(self):
        with LocalServer(status=404) as server:
            client = server.client()
            try:
                client.update(tracking())
                client.start()
                self.assertTrue(wait_until(lambda: "update" in client.snapshot()["error"]))
                self.assertFalse(client.snapshot()["online"])
                self.assertFalse(client.snapshot()["active"])
            finally:
                self.stop_client(client)

    def test_redirects_are_never_followed_even_to_another_local_path(self):
        with LocalServer(status=302) as server:
            client = server.client()
            try:
                client.update(tracking())
                client.start()
                self.assertTrue(wait_until(lambda: "unavailable" in client.snapshot()["error"]))
            finally:
                self.stop_client(client)
            self.assertNotIn("/escaped", server.requests)

    def test_disable_clears_snapshot_before_network_round_trip(self):
        client = GazePublisher()
        client.update(tracking())
        client._received_at = time.monotonic()
        client._state.update(online=True, active=True)
        self.assertTrue(client.snapshot()["active"])
        client.update(tracking(enabled=False))
        self.assertFalse(client.snapshot()["active"])
        self.assertFalse(client.snapshot()["enabled"])


if __name__ == "__main__":
    unittest.main()
