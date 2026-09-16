"""Local, deterministic simulated EEG and intent-gating state machine.

These values illustrate an interaction. They are not measured EEG or a medical
interpretation of attention. No hardware, network or third-party packages needed.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
import math
import threading
import time


EEG_BANDS = (
    "delta", "theta", "low_alpha", "high_alpha", "low_beta", "high_beta",
    "low_gamma", "mid_gamma",
)
DEFAULT_CONFIG = {
    "baseline": 32, "focus": 90, "threshold": 75, "dwell_ms": 1600,
    "mode": "assisted",
}


class DemoEngine:
    """One authoritative state for the AR browser and independent monitor.

    Inject a seconds-based monotonic ``clock`` for deterministic tests.
    Public operations return a detached snapshot and are safe across threads.
    """

    DISCONNECT_SECONDS = 2.0

    def __init__(self, clock=None):
        self._clock = clock or time.monotonic
        self._lock = threading.RLock()
        now = self._clock()
        self._created_at = now
        self._last_tick = now
        self._last_seen = None
        self._client_id = None
        self._target = None
        self._started = None
        self._start_attention = 32.0
        self._attention = 32.0
        self._phase = "idle"
        self._progress = 0.0
        self._confirmed_id = None
        self._confirmation_seq = 0
        self._reset_seq = 0
        self._events = deque(maxlen=32)
        self._config = dict(DEFAULT_CONFIG)
        self._log("虚拟 EEG 演示已就绪", "system")

    def _log(self, label, kind):
        self._events.appendleft({"time": time.strftime("%H:%M:%S"),
                                 "label": label, "kind": kind})

    def _connected(self, now):
        return self._last_seen is not None and now - self._last_seen <= self.DISCONNECT_SECONDS

    def _clear_target(self):
        self._target = None
        self._started = None
        self._progress = 0.0
        self._confirmed_id = None
        self._phase = "idle"

    def _advance(self, now):
        dt = max(0.0, now - self._last_tick)
        self._last_tick = now
        if not self._connected(now) and self._target is not None:
            self._log("AR 窗口连接中断，已取消当前意图", "disconnected")
            self._clear_target()
        if self._target is None:
            baseline = self._config["baseline"]
            self._attention = baseline + (self._attention - baseline) * math.exp(-dt * 3.2)
            return

        elapsed = max(0.0, now - self._started)
        dwell = self._config["dwell_ms"] / 1000.0
        if self._config["mode"] == "distracted":
            # Keep a visibly low, gently varying synthetic attention trace.
            cap = min(44.0, self._config["threshold"] - 1.0)
            self._attention = max(0.0, cap - 1.4 + 1.4 * math.sin(elapsed * 2.7))
            self._phase = "distracted"
            self._progress = 0.0
            return

        ramp = min(1.0, elapsed / (dwell * 0.85))
        eased = ramp * ramp * (3.0 - 2.0 * ramp)
        self._attention = self._start_attention + (self._config["focus"] - self._start_attention) * eased
        self._progress = min(1.0, elapsed / dwell)
        if self._confirmed_id == self._target["id"]:
            self._phase = "confirmed"
        elif elapsed + 1e-9 >= dwell and self._attention >= self._config["threshold"]:
            self._confirmed_id = self._target["id"]
            self._confirmation_seq += 1
            self._phase = "confirmed"
            self._progress = 1.0
            self._log("意图已确认 · " + self._target["label"], "confirmed")
        elif self._attention >= self._config["threshold"]:
            self._phase = "ready"
        else:
            self._phase = "focusing"

    def _snapshot(self, now):
        a = self._attention / 100.0
        t = max(0.0, now - self._created_at)
        # Raw-like signed samples at 256 Hz. Frequencies/amplitudes are synthetic.
        end_sample = int(t * 256)
        raw = []
        for sample in range(end_sample - 127, end_sample + 1):
            s = sample / 256.0
            value = (40 * math.sin(math.tau * 2.1 * s)
                     + (58 - 33 * a) * math.sin(math.tau * 9.5 * s)
                     + (15 + 54 * a) * math.sin(math.tau * 19.2 * s)
                     + 7 * math.sin(math.tau * 37.1 * s))
            raw.append(round(value))
        powers = (27000 - 13000 * a, 24500 - 12500 * a,
                  21000 - 10500 * a, 17000 - 6500 * a,
                  8500 + 36000 * a, 6500 + 25500 * a,
                  4800 + 9200 * a, 3500 + 6500 * a)
        bands = {band: round(value * (1 + .035 * math.sin(t * 1.7 + i)))
                 for i, (band, value) in enumerate(zip(EEG_BANDS, powers))}
        return {
            "attention": round(self._attention),
            "relaxation": round(max(0, min(100, 78 - 0.48 * self._attention))),
            "quality": 100, "phase": self._phase,
            "target": deepcopy(self._target), "progress": round(self._progress, 4),
            "confirmed_id": self._confirmed_id, "confirmation_seq": self._confirmation_seq,
            "reset_seq": self._reset_seq,
            "ar_connected": self._connected(now), "bands": bands, "raw": raw,
            "events": deepcopy(list(self._events)), "config": dict(self._config),
        }

    def tick(self):
        with self._lock:
            now = self._clock()
            self._advance(now)
            return self._snapshot(now)

    snapshot = tick

    @staticmethod
    def _validate_target(value):
        if not isinstance(value, dict):
            raise ValueError("target 必须包含 id 和 label")
        target = {}
        for key, max_len in (("id", 160), ("label", 160)):
            item = value.get(key)
            if not isinstance(item, str) or not item.strip() or len(item) > max_len:
                raise ValueError("target." + key + " 必须是 1–160 字符的文本")
            target[key] = item.strip()
        return target

    def event(self, payload=None, **kwargs):
        """Accept a JSON event dictionary (or matching named fields)."""
        if payload is None:
            payload = kwargs
        if not isinstance(payload, dict):
            raise ValueError("事件必须为 JSON 对象")
        kind = payload.get("type")
        if not isinstance(kind, str) or kind not in {"hover", "leave", "click", "heartbeat", "reset"}:
            raise ValueError("不支持的演示事件")
        client = payload.get("client_id", "ar")
        if not isinstance(client, str) or not client or len(client) > 160:
            raise ValueError("client_id 必须是 1–160 字符的文本")
        target = self._validate_target(payload.get("target")) if kind in {"hover", "click"} else None
        with self._lock:
            now = self._clock()
            # Expire before applying the new heartbeat: reconnecting cannot revive old dwell.
            self._advance(now)
            if kind == "reset":
                return self.reset()
            if kind == "heartbeat":
                if self._target is None or client == self._client_id:
                    self._last_seen = now
                    self._client_id = client
            elif kind == "leave":
                leave_target = payload.get("target")
                same_target = not isinstance(leave_target, dict) or not self._target or leave_target.get("id") == self._target["id"]
                if client == self._client_id and same_target:
                    self._last_seen = now
                    if self._target:
                        self._log("已移开 · " + self._target["label"], "leave")
                    self._clear_target()
            else:
                if self._target is None or self._target["id"] != target["id"] or client != self._client_id:
                    self._clear_target()
                    self._target = target
                    self._started = now
                    # Every new target needs its own accumulation, even after a high-attention target.
                    self._attention = float(self._config["baseline"])
                    self._start_attention = self._attention
                    self._log("聚焦目标 · " + target["label"], "hover")
                self._client_id = client
                self._last_seen = now
                if kind == "click" and self._confirmed_id is None:
                    self._log("点击候选 · 等待注意力确认", "click")
            self._advance(now)
            return self._snapshot(now)

    def configure(self, updates):
        if not isinstance(updates, dict):
            raise ValueError("设置必须为 JSON 对象")
        if set(updates) - set(DEFAULT_CONFIG):
            raise ValueError("设置包含未知字段")
        with self._lock:
            candidate = {**self._config, **updates}
            for key, low, high in (("baseline", 0, 99), ("focus", 1, 100),
                                   ("threshold", 1, 100), ("dwell_ms", 500, 10000)):
                value = candidate[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or int(value) != value or not low <= value <= high:
                    raise ValueError(f"{key} 需要 {low}–{high} 之间的整数")
                candidate[key] = int(value)
            if not candidate["baseline"] < candidate["threshold"] <= candidate["focus"]:
                raise ValueError("请设置：基线 < 确认阈值 ≤ 聚焦值")
            if not isinstance(candidate["mode"], str) or candidate["mode"] not in {"assisted", "distracted"}:
                raise ValueError("mode 仅支持 assisted 或 distracted")
            if candidate != self._config:
                self._config = candidate
                self._clear_target()
                self._attention = float(candidate["baseline"])
                self._last_tick = self._clock()
                self._log("演示参数已更新，重新等待目标", "config")
            return self.tick()

    def reset(self):
        with self._lock:
            self._reset_seq += 1
            self._clear_target()
            self._attention = float(self._config["baseline"])
            self._last_tick = self._clock()
            self._events.clear()
            self._log("演示已重置", "reset")
            return self.tick()
