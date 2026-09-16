import json
from pathlib import Path
import sys
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from demo_server import create_server
from gaze_state import GazeState


CLIENT_A = "5a045683-8593-4ab9-b8ec-b2b362f8f20d"
CLIENT_B = "9166b026-30c7-48d4-8b0c-1a9c4f3b8f04"


def sample(client=CLIENT_A, seq=1, **extra):
    return {
        "client_id": client, "seq": seq, "enabled": True, "active": True,
        "calibrated": True, "x": .25, "y": .75, "quality": .8, "eyes": 2,
        "reason": "tracking", "sample_age_ms": 20,
        "calibration_screen": {"width": 1920, "height": 1080},
        "source": "camera", "simulated": False, **extra,
    }


class GazeTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.
        self.gaze = GazeState(lambda: self.now)

    def test_real_camera_fields_and_no_connection_initially(self):
        empty = self.gaze.snapshot()
        self.assertFalse(empty["active"])
        self.assertFalse(empty["enabled"])
        self.assertFalse(empty["connected"])
        self.assertIsNone(empty["age_ms"])
        state = self.gaze.update(sample())
        self.assertEqual(state["source"], "camera")
        self.assertIs(state["simulated"], False)
        self.assertTrue(state["active"])
        self.assertTrue(state["connected"])
        self.assertEqual(state["age_ms"], 20)
        self.assertNotIn("client_id", state)
        self.assertNotIn("sample_age_ms", state)

    def test_active_expires_by_total_sample_age_before_connection(self):
        self.gaze.update(sample(sample_age_ms=200))
        self.now = .149
        self.assertTrue(self.gaze.snapshot()["active"])
        self.now = .150
        state = self.gaze.snapshot()
        self.assertFalse(state["active"])
        self.assertTrue(state["connected"])
        self.assertTrue(state["enabled"])
        self.assertEqual(state["reason"], "stale_frame")
        self.assertEqual(state["age_ms"], 350)
        self.now = 1.
        state = self.gaze.snapshot()
        self.assertFalse(state["connected"])
        self.assertFalse(state["active"])
        self.assertTrue(state["enabled"])
        self.assertEqual(state["reason"], "disconnected")

    def test_stale_frame_heartbeats_cannot_create_an_active_pointer(self):
        for seq in range(1, 10):
            self.now += .4
            state = self.gaze.update(sample(seq=seq, sample_age_ms=250))
            self.assertTrue(state["connected"])
            self.assertTrue(state["enabled"])
            self.assertFalse(state["active"])
            self.assertEqual(state["reason"], "stale_frame")

    def test_active_requires_calibration_screen_quality_and_live_tracking(self):
        conditions = [
            ({"enabled": False}, "disabled"),
            ({"calibrated": False}, "uncalibrated"),
            ({"calibration_screen": None}, "uncalibrated"),
            ({"quality": .499}, "eye_lost"),
            ({"active": False}, "eye_lost"),
            ({"reason": "eye_lost"}, "eye_lost"),
            ({"reason": "calibrating", "calibrated": False}, "calibrating"),
            ({"reason": "camera_off"}, "camera_off"),
            ({"reason": "synthetic"}, "synthetic"),
        ]
        for seq, (changes, reason) in enumerate(conditions, 1):
            with self.subTest(changes=changes):
                state = self.gaze.update(sample(seq=seq, **changes))
                self.assertFalse(state["active"])
                self.assertEqual(state["reason"], reason)
        self.assertTrue(self.gaze.update(sample(seq=20, quality=.5))["active"])

    def test_old_instance_disable_cannot_cancel_new_owner(self):
        self.gaze.update(sample())
        self.gaze.update(sample(CLIENT_B, x=.9))
        state = self.gaze.update(sample(seq=2, enabled=False, active=False, reason="disabled"))
        self.assertTrue(state["active"])
        self.assertEqual(state["x"], .9)
        state = self.gaze.update(sample(CLIENT_B, seq=2, enabled=False, active=False, reason="disabled"))
        self.assertFalse(state["active"])
        self.assertFalse(state["enabled"])

    def test_replays_and_malformed_data_leave_previous_state_unchanged(self):
        self.gaze.update(sample())
        bad = [
            sample(), sample(seq=0), sample(seq=True), sample(seq=2 ** 53),
            sample(seq=2, client_id="not-a-uuid"), sample(seq=2, enabled=1),
            sample(seq=2, calibrated=1), sample(seq=2, active=1),
            sample(seq=2, x=float("nan")), sample(seq=2, x=True),
            sample(seq=2, y=1.1), sample(seq=2, y=10 ** 500),
            sample(seq=2, quality=-.1), sample(seq=2, quality=float("inf")),
            sample(seq=2, eyes=True), sample(seq=2, eyes=0),
            sample(seq=2, reason="anything"), sample(seq=2, reason=[]),
            sample(seq=2, sample_age_ms=-1), sample(seq=2, sample_age_ms=None),
            sample(seq=2, source="mouse"), sample(seq=2, simulated=0),
            sample(seq=2, image="data:image/png;base64,not-an-image"),
            sample(seq=2, calibration_screen={"width": 1920., "height": 1080}),
            sample(seq=2, calibration_screen={"width": 0, "height": 1080}),
            sample(seq=2, calibration_screen={"width": True, "height": 1080}),
            sample(seq=2, calibration_screen={"width": 1920, "height": 1080, "image": "x"}),
        ]
        missing = sample(seq=2)
        del missing["source"]
        bad.append(missing)
        for payload in bad:
            with self.subTest(payload=str(payload)[:160]):
                with self.assertRaises(ValueError):
                    self.gaze.update(payload)
                self.assertEqual(self.gaze.snapshot()["seq"], 1)
        self.assertEqual(self.gaze.update(sample(seq=2, x=.8))["x"], .8)

    def test_client_replay_memory_is_bounded_and_keeps_live_owner(self):
        self.gaze.update(sample(seq=10))
        for _ in range(self.gaze.MAX_CLIENTS + 30):
            self.gaze.update(sample(str(uuid4()), enabled=False, active=False))
        self.assertLessEqual(len(self.gaze._sequences), self.gaze.MAX_CLIENTS)
        self.assertIn(str(UUID(CLIENT_A)), self.gaze._sequences)
        with self.assertRaises(ValueError):
            self.gaze.update(sample(seq=9))
        self.assertTrue(self.gaze.snapshot()["active"])

    def test_payload_and_snapshot_screen_mutation_cannot_change_server_state(self):
        payload = sample()
        state = self.gaze.update(payload)
        payload["calibration_screen"]["width"] = 1
        state["calibration_screen"]["width"] = 2
        self.assertEqual(self.gaze.snapshot()["calibration_screen"]["width"], 1920)


class GazeHTTPTests(unittest.TestCase):
    def setUp(self):
        self.server = create_server(0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def test_real_gaze_transport_does_not_change_mouse_or_eeg(self):
        eeg_before = self.server.engine.snapshot()
        pointer_before = self.server.pointer.snapshot()
        request = Request(self.url + "/api/gaze", data=json.dumps(sample()).encode(),
                          headers={"Content-Type": "application/json", "Origin": self.url})
        with urlopen(request) as response:
            state = json.load(response)
            self.assertTrue(state["active"])
            self.assertFalse(state["simulated"])
            self.assertEqual(state["calibration_screen"]["width"], 1920)
        with urlopen(self.url + "/api/gaze") as response:
            state = json.load(response)
            self.assertTrue(state["connected"])
            self.assertEqual(state["source"], "camera")
        eeg_after = self.server.engine.snapshot()
        for key in ("target", "confirmed_id", "confirmation_seq", "phase"):
            self.assertEqual(eeg_after[key], eeg_before[key])
        self.assertEqual(self.server.pointer.snapshot(), pointer_before)
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 400)

    def test_host_origin_and_cross_site_protections_cover_get_and_post(self):
        for headers in ({"Host": "other.example"}, {"Origin": "https://other.example"}, {"Sec-Fetch-Site": "cross-site"}):
            for data in (None, json.dumps(sample()).encode()):
                request = Request(self.url + "/api/gaze", data=data,
                                  headers={"Content-Type": "application/json", **headers})
                with self.assertRaises(HTTPError) as error:
                    urlopen(request)
                self.assertEqual(error.exception.code, 403)
        self.assertFalse(self.server.gaze.snapshot()["connected"])

    def test_images_are_rejected_and_never_activate_the_stream(self):
        request = Request(self.url + "/api/gaze",
                          data=json.dumps(sample(image="private-eye-frame")).encode(),
                          headers={"Content-Type": "application/json"})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 400)
        self.assertFalse(self.server.gaze.snapshot()["connected"])


if __name__ == "__main__":
    unittest.main()
