import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from demo_engine import DemoEngine, EEG_BANDS
from demo_server import create_server


class Clock:
    now = 0.0

    def __call__(self):
        return self.now

    def add(self, seconds):
        self.now += seconds


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.engine = DemoEngine(self.clock)

    def event(self, kind, target="water"):
        return self.engine.event({"type": kind, "target": {"id": target, "label": target}, "client_id": "test"})

    def wait(self, seconds):
        for _ in range(int(seconds / .1 + .5)):
            self.clock.add(.1)
            self.event("heartbeat")
        return self.engine.snapshot()

    def test_early_click_needs_full_dwell_and_confirmation_is_once(self):
        self.event("click")
        state = self.wait(.8)
        self.assertIsNone(state["confirmed_id"])
        self.event("click")
        self.wait(.8)
        state = self.engine.snapshot()
        self.assertEqual(state["confirmed_id"], "water")
        self.assertEqual(state["confirmation_seq"], 1)
        self.event("click")
        self.wait(4)
        self.assertEqual(self.engine.snapshot()["confirmation_seq"], 1)

    def test_target_switch_requires_new_dwell(self):
        self.event("hover")
        self.wait(1.2)
        state = self.event("hover", "music")
        self.assertEqual(state["attention"], 32)
        self.assertEqual(state["progress"], 0)
        self.wait(1.0)
        self.assertIsNone(self.engine.snapshot()["confirmed_id"])
        self.wait(.6)
        self.assertEqual(self.engine.snapshot()["confirmed_id"], "music")

    def test_same_target_hover_does_not_restart_accumulation(self):
        self.event("hover")
        self.wait(1)
        before = self.engine.snapshot()["progress"]
        self.event("hover")
        self.assertEqual(self.engine.snapshot()["progress"], before)
        self.wait(.6)
        self.assertEqual(self.engine.snapshot()["confirmation_seq"], 1)

    def test_leave_and_stale_leave(self):
        self.event("hover", "water")
        self.wait(.5)
        self.event("hover", "music")
        self.event("leave", "water")
        self.assertEqual(self.engine.snapshot()["target"]["id"], "music")
        self.event("leave", "music")
        self.wait(2)
        self.assertEqual(self.engine.snapshot()["phase"], "idle")
        self.assertEqual(self.engine.snapshot()["confirmation_seq"], 0)

    def test_disconnect_cancels_pending_before_reconnection(self):
        self.event("hover")
        self.clock.add(2.1)
        state = self.engine.snapshot()
        self.assertFalse(state["ar_connected"])
        self.assertIsNone(state["target"])
        self.assertEqual(state["confirmation_seq"], 0)
        self.event("heartbeat")
        self.wait(2)
        self.assertIsNone(self.engine.snapshot()["confirmed_id"])

    def test_other_clients_heartbeat_cannot_keep_pending_alive(self):
        self.event("hover")
        self.clock.add(1)
        self.engine.event({"type": "heartbeat", "client_id": "other"})
        self.clock.add(1.1)
        self.assertFalse(self.engine.snapshot()["ar_connected"])
        self.assertEqual(self.engine.snapshot()["confirmation_seq"], 0)

    def test_distracted_click_never_confirms(self):
        self.engine.configure({"mode": "distracted"})
        self.event("click")
        self.wait(15)
        state = self.engine.snapshot()
        self.assertEqual(state["phase"], "distracted")
        self.assertLess(state["attention"], state["config"]["threshold"])
        self.assertIsNone(state["confirmed_id"])
        self.assertEqual(state["confirmation_seq"], 0)

    def test_configuration_is_atomic_and_resets_dwell(self):
        self.event("hover")
        self.wait(1)
        before = self.engine.snapshot()
        for bad in ({"focus": 60}, {"dwell_ms": 0}, {"threshold": True}, {"mode": "unknown"}, {"mode": []}, {"baseline": float("nan")}):
            with self.assertRaises(ValueError):
                self.engine.configure(bad)
            self.assertEqual(self.engine.snapshot()["config"], before["config"])
            self.assertEqual(self.engine.snapshot()["target"], before["target"])
        self.engine.configure({"dwell_ms": 2000})
        self.assertIsNone(self.engine.snapshot()["target"])
        self.event("hover")
        self.wait(1.6)
        self.assertIsNone(self.engine.snapshot()["confirmed_id"])
        self.wait(.4)
        self.assertEqual(self.engine.snapshot()["confirmation_seq"], 1)

    def test_reset_does_not_reuse_sequence_and_snapshot_is_detached(self):
        self.event("hover")
        self.wait(1.6)
        self.engine.reset()
        state = self.engine.snapshot()
        self.assertEqual(state["confirmation_seq"], 1)
        self.assertEqual(state["reset_seq"], 1)
        self.assertIsNone(state["confirmed_id"])
        state["config"]["focus"] = 1
        self.assertEqual(self.engine.snapshot()["config"]["focus"], 90)
        self.assertEqual(len(state["raw"]), 128)
        self.assertEqual(set(state["bands"]), set(EEG_BANDS))

    def test_malformed_event_is_rejected_without_losing_target(self):
        self.event("hover")
        with self.assertRaises(ValueError):
            self.engine.event({"type": []})
        with self.assertRaises(ValueError):
            self.engine.event({"type": "hover", "target": {"id": "music"}})
        self.assertEqual(self.engine.snapshot()["target"]["id"], "water")


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "site"
        self.root.mkdir()
        (self.root / "index.html").write_text("<h1>demo</h1>", encoding="utf-8")
        (Path(self.temp.name) / "secret.txt").write_text("not served")
        self.server = create_server(0, static_root=self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.temp.cleanup()

    def test_health_static_and_state(self):
        with urlopen(self.url + "/api/health") as response:
            self.assertTrue(json.load(response)["ok"])
        with urlopen(self.url + "/") as response:
            self.assertIn(b"demo", response.read())
        with urlopen(self.url + "/api/state") as response:
            self.assertEqual(json.load(response)["quality"], 100)

    def test_invalid_config_and_cross_origin_leave_state_unchanged(self):
        for body, origin, expected in [({"focus": 1}, self.url, 400), ({"focus": 95}, "https://other.example", 403)]:
            request = Request(self.url + "/api/config", data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "Origin": origin})
            with self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual(error.exception.code, expected)
        self.assertEqual(self.server.engine.snapshot()["config"]["focus"], 90)

    def test_traversal_and_body_limit(self):
        for path in ("/%2e%2e/secret.txt", "/..%5csecret.txt"):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.url + path)
            self.assertIn(error.exception.code, (400, 403))
        request = Request(self.url + "/api/event", data=b" " * 17000, headers={"Content-Type": "application/json"})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 413)


if __name__ == "__main__":
    unittest.main()
