import json
from pathlib import Path
import sys
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from demo_server import create_server
from pointer_state import PointerState


def sample(client="page-a", seq=1, active=True, **extra):
    return {"client_id": client, "seq": seq, "active": active, "x": .25, "y": .75,
            "viewport": {"width": 1920, "height": 1080}, **extra}


class PointerTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.
        self.pointer = PointerState(lambda: self.now)

    def test_stale_and_malformed_updates_cannot_replace_valid_state(self):
        self.pointer.update(sample())
        bad = [sample(), sample(seq=0), sample(seq=True), sample(seq=2, x=float("nan")),
               sample(seq=2, y=1.1), sample(seq=2, active=1), sample(seq=2, x=True),
               sample(seq=2, x=10 ** 500), sample(seq=2, viewport={"width": 0, "height": 100})]
        for payload in bad:
            with self.subTest(payload=str(payload)[:120]):
                with self.assertRaises(ValueError):
                    self.pointer.update(payload)
                self.assertEqual(self.pointer.snapshot()["seq"], 1)
        self.assertEqual(self.pointer.update(sample(seq=2, x=.8))["x"], .8)

    def test_old_window_leave_cannot_cancel_new_window(self):
        self.pointer.update(sample())
        self.pointer.update(sample(client="page-b", x=.6))
        state = self.pointer.update(sample(seq=2, active=False))
        self.assertTrue(state["active"])
        self.assertEqual(state["x"], .6)
        self.assertFalse(self.pointer.update(sample(client="page-b", seq=2, active=False))["active"])

    def test_stationary_heartbeat_and_disconnect_timeout(self):
        self.pointer.update(sample())
        self.now = 1.4
        self.assertTrue(self.pointer.snapshot()["active"])
        self.pointer.update(sample(seq=2))
        self.now = 2.8
        self.assertTrue(self.pointer.snapshot()["active"])
        self.now = 2.91
        self.assertFalse(self.pointer.snapshot()["active"])
        self.assertEqual(self.pointer.snapshot()["age_ms"], 1510)

    def test_consumer_lease_requires_viewer_polling(self):
        self.assertIsNone(self.pointer.snapshot()["age_ms"])
        self.assertFalse(self.pointer.snapshot()["consumer_connected"])
        self.assertTrue(self.pointer.snapshot(consumer=True)["consumer_connected"])
        self.now = .8
        self.pointer.update(sample())  # Browser heartbeats cannot renew desktop lease.
        self.now = 1.01
        self.assertFalse(self.pointer.snapshot()["consumer_connected"])
        self.assertTrue(self.pointer.snapshot(consumer=True)["consumer_connected"])


class PointerHTTPTests(unittest.TestCase):
    def setUp(self):
        self.server = create_server(0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def test_pointer_transport_is_independent_of_eeg_confirmation(self):
        before = self.server.engine.snapshot()
        request = Request(self.url + "/api/pointer", data=json.dumps(sample()).encode(),
                          headers={"Content-Type": "application/json", "Origin": self.url})
        with urlopen(request) as response:
            self.assertTrue(json.load(response)["active"])
        with urlopen(self.url + "/api/pointer?viewer=eye-demo") as response:
            state = json.load(response)
            self.assertTrue(state["consumer_connected"])
            self.assertEqual(state["source"], "mouse")
            self.assertTrue(state["simulated"])
        after = self.server.engine.snapshot()
        for key in ("target", "confirmed_id", "confirmation_seq", "phase"):
            self.assertEqual(after[key], before[key])
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 400)

    def test_pointer_rejects_wrong_host_origin_and_cross_site_reader(self):
        for headers in ({"Host": "other.example"}, {"Origin": "https://other.example"}, {"Sec-Fetch-Site": "cross-site"}):
            for data in (None, json.dumps(sample()).encode()):
                request = Request(self.url + "/api/pointer?viewer=eye-demo", data=data,
                                  headers={"Content-Type": "application/json", **headers})
                with self.assertRaises(HTTPError) as error:
                    urlopen(request)
                self.assertEqual(error.exception.code, 403)
        self.assertFalse(self.server.pointer.snapshot()["consumer_connected"])


if __name__ == "__main__":
    unittest.main()
