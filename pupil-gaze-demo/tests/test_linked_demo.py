"""The simulated link must reject stale, invalid or real-camera payloads."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from linked_demo import PointerClient, validate_pointer


def payload(**updates):
    return {"simulated": True, "source": "mouse", "x": .2, "y": .8,
            "age_ms": 10, "active": True, **updates}


class LinkedDemoTests(unittest.TestCase):
    def test_pointer_preserves_exact_normalized_position(self):
        state = validate_pointer(payload())
        self.assertTrue(state["active"])
        self.assertEqual((state["x"], state["y"]), (.2, .8))

    def test_bad_coordinates_and_unmarked_simulations_rejected(self):
        for update in ({"x": float("nan")}, {"y": float("inf")}, {"x": 2},
                       {"x": True}, {"simulated": False}, {"source": "camera"}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate_pointer(payload(**update))

    def test_inactive_and_stale_pointer_do_not_replay(self):
        for update in ({"active": False}, {"age_ms": 1500}, {"age_ms": None}, {"age_ms": -1}):
            with self.subTest(update=update):
                self.assertFalse(validate_pointer(payload(**update))["active"])

    def test_stalled_network_clears_live_pointer(self):
        client = PointerClient()
        client._state = validate_pointer(payload())
        client._received_at = 10.
        with patch("linked_demo.time.monotonic", return_value=10.1):
            self.assertTrue(client.snapshot()["active"])
        with patch("linked_demo.time.monotonic", return_value=11.):
            self.assertFalse(client.snapshot()["online"])
            self.assertFalse(client.snapshot()["active"])


if __name__ == "__main__":
    unittest.main()
