"""TGAM EEG Monitor - English Windows desktop demonstration application."""

from __future__ import annotations

import csv
from datetime import datetime
import math
import queue
import random
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # Demo Mode remains usable before dependencies are installed.
    serial = None
    list_ports = None

from thinkgear import (
    BAND_LABELS,
    EEG_BANDS,
    EEGModel,
    ParserStats,
    ThinkGearParser,
    build_packet,
)


APP_TITLE = "TGAM EEG Monitor"
DEFAULT_BAUD = 57600

BG = "#07131D"
PANEL = "#0C1E2A"
PANEL_ALT = "#102735"
BORDER = "#173847"
GRID = "#183642"
TEXT = "#EAF7F4"
MUTED = "#7FA4AA"
ACCENT = "#36E8BB"
GREEN = "#53E58A"
YELLOW = "#F2C14E"
RED = "#FF6B6B"


class SerialWorker(threading.Thread):
    """Read the USB serial adapter without blocking the Tkinter UI."""

    def __init__(self, port: str, baud: int, output_queue: queue.Queue) -> None:
        super().__init__(daemon=True)
        self.port = port
        self.baud = baud
        self.output_queue = output_queue
        self.parser = ThinkGearParser()
        self._stop_event = threading.Event()
        self._serial_port = None

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        if serial is None:
            self.output_queue.put(
                ("error", "pyserial is not installed. Use Demo Mode or reinstall the app.")
            )
            return

        try:
            self._serial_port = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.05,
            )
            self.output_queue.put(("connection", True, self.port))
            last_stats_update = 0.0

            while not self._stop_event.is_set():
                waiting = self._serial_port.in_waiting
                chunk = self._serial_port.read(waiting if waiting else 1)
                if chunk:
                    for packet in self.parser.feed(chunk):
                        self.output_queue.put(("packet", packet))

                now = time.monotonic()
                if now - last_stats_update >= 0.25:
                    self.output_queue.put(("stats", self.parser.stats))
                    last_stats_update = now
        except Exception as error:  # Serial exceptions differ between platforms.
            if not self._stop_event.is_set():
                self.output_queue.put(("error", f"Serial connection failed: {error}"))
        finally:
            if self._serial_port is not None:
                try:
                    self._serial_port.close()
                except Exception:
                    pass
            self.output_queue.put(("connection", False, self.port))


class DemoEngine:
    """Generate valid TGAM packets and feed them through the real parser."""

    SAMPLE_RATE = 512
    SAMPLES_PER_TICK = 10

    def __init__(self) -> None:
        self.parser = ThinkGearParser()
        self.sample_index = 0
        self.next_summary_sample = self.SAMPLE_RATE
        self.random = random.Random(20260825)

    def reset(self) -> None:
        self.parser.reset()
        self.sample_index = 0
        self.next_summary_sample = self.SAMPLE_RATE

    def step(self) -> list[dict]:
        stream = bytearray()

        for _ in range(self.SAMPLES_PER_TICK):
            raw_value = self._raw_sample(self.sample_index)
            raw_bytes = int(raw_value).to_bytes(2, "big", signed=True)
            stream.extend(build_packet(bytes((0x80, 0x02)) + raw_bytes))
            self.sample_index += 1

            if self.sample_index >= self.next_summary_sample:
                stream.extend(build_packet(self._summary_payload()))
                self.next_summary_sample += self.SAMPLE_RATE

        return self.parser.feed(stream)

    def _raw_sample(self, index: int) -> int:
        seconds = index / self.SAMPLE_RATE
        signal_value = (
            360 * math.sin(2 * math.pi * 10.0 * seconds)
            + 180 * math.sin(2 * math.pi * 6.0 * seconds + 0.7)
            + 80 * math.sin(2 * math.pi * 22.0 * seconds)
            + self.random.gauss(0, 65)
        )

        # A short artefact resembles a blink in raw frontal-electrode data.
        blink_phase = seconds % 7.0
        if 0.02 < blink_phase < 0.12:
            signal_value += 2200 * math.sin(math.pi * (blink_phase - 0.02) / 0.10)

        return max(-32768, min(32767, int(signal_value)))

    def _summary_payload(self) -> bytes:
        seconds = self.sample_index / self.SAMPLE_RATE
        attention = round(62 + 18 * math.sin(seconds / 5.0))
        meditation = round(58 + 15 * math.sin(seconds / 7.0 + 1.1))
        attention = max(0, min(100, attention))
        meditation = max(0, min(100, meditation))

        band_values = {
            "delta": 320_000 + int(55_000 * (1 + math.sin(seconds / 4.0))),
            "theta": 175_000 + int(40_000 * (1 + math.sin(seconds / 3.0 + 1.0))),
            "low_alpha": 78_000 + meditation * 1_200,
            "high_alpha": 61_000 + meditation * 950,
            "low_beta": 48_000 + attention * 1_100,
            "high_beta": 35_000 + attention * 900,
            "low_gamma": 24_000 + attention * 420,
            "mid_gamma": 18_000 + attention * 310,
        }

        eeg_bytes = bytearray()
        for band in EEG_BANDS:
            value = max(0, min(0xFFFFFF, int(band_values[band])))
            eeg_bytes.extend(value.to_bytes(3, "big"))

        return (
            bytes((0x02, 0, 0x83, 24))
            + bytes(eeg_bytes)
            + bytes((0x04, attention, 0x05, meditation))
        )


class MetricCard(tk.Frame):
    def __init__(self, parent, title: str, accent: str = ACCENT) -> None:
        super().__init__(
            parent,
            bg=PANEL,
            highlightbackground=BORDER,
            highlightthickness=1,
            bd=0,
        )
        self.accent = accent
        self.configure(padx=18, pady=14)
        tk.Label(
            self,
            text=title.upper(),
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI Semibold", 9),
            anchor="w",
        ).pack(fill="x")
        self.value_label = tk.Label(
            self,
            text="--",
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI Semibold", 24),
            anchor="w",
        )
        self.value_label.pack(fill="x", pady=(4, 0))
        self.detail_label = tk.Label(
            self,
            text="Waiting for data",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 9),
            anchor="w",
        )
        self.detail_label.pack(fill="x")
        self.progress = tk.Canvas(
            self, height=3, bg=GRID, highlightthickness=0, bd=0
        )
        self.progress.pack(fill="x", pady=(11, 0))
        self.progress.bind("<Configure>", lambda _event: self._draw_progress())
        self._percent = 0.0

    def set(self, value: str, detail: str, percent: float = 0.0, color: str | None = None) -> None:
        self.value_label.configure(text=value, fg=color or TEXT)
        self.detail_label.configure(text=detail)
        self._percent = max(0.0, min(100.0, float(percent)))
        self._draw_progress(color or self.accent)

    def _draw_progress(self, color: str | None = None) -> None:
        self.progress.delete("all")
        width = max(1, self.progress.winfo_width())
        self.progress.create_rectangle(
            0,
            0,
            width * self._percent / 100.0,
            3,
            fill=color or self.accent,
            outline="",
        )


class WaveformCanvas(tk.Canvas):
    def __init__(self, parent) -> None:
        super().__init__(
            parent,
            bg=PANEL,
            highlightthickness=0,
            bd=0,
            height=260,
        )

    def draw(self, samples) -> None:
        self.delete("all")
        width = max(300, self.winfo_width())
        height = max(180, self.winfo_height())
        left, top, right, bottom = 54, 18, width - 18, height - 34

        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            y = top + (bottom - top) * fraction
            self.create_line(left, y, right, y, fill=GRID, width=1)
        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            x = left + (right - left) * fraction
            self.create_line(x, top, x, bottom, fill=GRID, width=1)

        self.create_text(
            left,
            bottom + 18,
            text="3 seconds",
            fill=MUTED,
            font=("Segoe UI", 8),
            anchor="w",
        )

        values = list(samples)
        if len(values) < 2:
            self.create_text(
                (left + right) / 2,
                (top + bottom) / 2,
                text="Waiting for raw EEG samples",
                fill=MUTED,
                font=("Segoe UI", 11),
            )
            return

        display_count = min(1536, len(values))
        values = values[-display_count:]
        abs_values = sorted(abs(value) for value in values)
        robust_peak = abs_values[min(len(abs_values) - 1, int(len(abs_values) * 0.95))]
        scale = max(300.0, robust_peak * 1.25)
        center = (top + bottom) / 2
        amplitude = (bottom - top) * 0.46
        points: list[float] = []

        for index, value in enumerate(values):
            x = left + index * (right - left) / max(1, len(values) - 1)
            clipped = max(-scale, min(scale, float(value)))
            y = center - clipped / scale * amplitude
            points.extend((x, y))

        self.create_line(points, fill=ACCENT, width=2, smooth=False)
        self.create_text(
            10,
            top,
            text=f"+{int(scale)}",
            fill=MUTED,
            font=("Consolas", 8),
            anchor="w",
        )
        self.create_text(
            10,
            center,
            text="0",
            fill=MUTED,
            font=("Consolas", 8),
            anchor="w",
        )
        self.create_text(
            10,
            bottom,
            text=f"-{int(scale)}",
            fill=MUTED,
            font=("Consolas", 8),
            anchor="w",
        )


class BandChart(tk.Canvas):
    def __init__(self, parent) -> None:
        super().__init__(
            parent,
            bg=PANEL,
            highlightthickness=0,
            bd=0,
            height=340,
        )

    def draw(self, bands: dict[str, float]) -> None:
        self.delete("all")
        width = max(320, self.winfo_width())
        height = max(280, self.winfo_height())
        label_width = 92
        value_width = 70
        bar_left = label_width
        bar_right = width - value_width
        row_height = (height - 18) / len(EEG_BANDS)
        log_values = [math.log10(max(0.0, bands.get(band, 0.0)) + 1.0) for band in EEG_BANDS]
        maximum = max(log_values) if log_values else 0.0

        for index, band in enumerate(EEG_BANDS):
            y = 8 + index * row_height
            center_y = y + row_height / 2
            self.create_text(
                0,
                center_y,
                text=BAND_LABELS[band],
                fill=TEXT,
                font=("Segoe UI", 9),
                anchor="w",
            )
            self.create_rectangle(
                bar_left,
                center_y - 5,
                bar_right,
                center_y + 5,
                fill=GRID,
                outline="",
            )
            ratio = (log_values[index] / maximum) if maximum > 0 else 0.0
            self.create_rectangle(
                bar_left,
                center_y - 5,
                bar_left + (bar_right - bar_left) * ratio,
                center_y + 5,
                fill=ACCENT if index < 4 else GREEN,
                outline="",
            )
            value = bands.get(band, 0.0)
            display = "--" if value <= 0 else f"{int(value):,}"
            self.create_text(
                width - 2,
                center_y,
                text=display,
                fill=MUTED,
                font=("Consolas", 8),
                anchor="e",
            )


class TGAMApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.configure(bg=BG)
        self.root.minsize(1080, 720)
        self._set_window_size()

        self.model = EEGModel()
        self.event_queue: queue.Queue = queue.Queue()
        self.serial_worker: SerialWorker | None = None
        self.demo_engine = DemoEngine()
        self.demo_active = False
        self.connected = False
        self.current_port = ""
        self.parser_stats = ParserStats()
        self.port_devices: dict[str, str] = {}
        self.session_rows: list[dict] = []
        self._last_record_second = -1
        self._closing = False

        self._configure_styles()
        self._build_ui()
        self.refresh_ports()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.root.after(20, self._poll_queue)
        self.root.after(20, self._demo_tick)
        self.root.after(100, self._update_display)
        self.root.after(1000, self._record_snapshot)

    def _set_window_size(self) -> None:
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width = min(1380, max(1100, screen_width - 100))
        height = min(900, max(740, screen_height - 100))
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _configure_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "TGAM.TCombobox",
            fieldbackground=PANEL_ALT,
            background=PANEL_ALT,
            foreground=TEXT,
            arrowcolor=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=7,
        )
        style.map(
            "TGAM.TCombobox",
            fieldbackground=[("readonly", PANEL_ALT)],
            foreground=[("readonly", TEXT)],
            selectbackground=[("readonly", PANEL_ALT)],
            selectforeground=[("readonly", TEXT)],
        )

    def _panel(self, parent, **grid_options) -> tk.Frame:
        frame = tk.Frame(
            parent,
            bg=PANEL,
            highlightbackground=BORDER,
            highlightthickness=1,
            bd=0,
        )
        if grid_options:
            frame.grid(**grid_options)
        return frame

    def _section_title(self, parent, title: str, subtitle: str = "") -> None:
        header = tk.Frame(parent, bg=PANEL)
        header.pack(fill="x", padx=18, pady=(15, 5))
        tk.Label(
            header,
            text=title,
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI Semibold", 12),
        ).pack(side="left")
        if subtitle:
            tk.Label(
                header,
                text=subtitle,
                bg=PANEL,
                fg=MUTED,
                font=("Segoe UI", 9),
            ).pack(side="right")

    def _button(self, parent, text: str, command, accent: bool = False) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=ACCENT if accent else PANEL_ALT,
            fg=BG if accent else TEXT,
            activebackground=GREEN if accent else BORDER,
            activeforeground=BG if accent else TEXT,
            relief="flat",
            bd=0,
            padx=16,
            pady=8,
            cursor="hand2",
            font=("Segoe UI Semibold", 9),
        )

    def _build_ui(self) -> None:
        container = tk.Frame(self.root, bg=BG)
        container.pack(fill="both", expand=True, padx=22, pady=18)

        top = tk.Frame(container, bg=BG)
        top.pack(fill="x", pady=(0, 14))
        title_box = tk.Frame(top, bg=BG)
        title_box.pack(side="left")
        tk.Label(
            title_box,
            text="TGAM EEG MONITOR",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI Semibold", 22),
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text="ThinkGear serial visualization · Bluetooth 2.0 · 57,600 baud",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w")

        self.connection_badge = tk.Label(
            top,
            text="●  DISCONNECTED",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI Semibold", 10),
        )
        self.connection_badge.pack(side="right", pady=8)

        connection_panel = self._panel(container)
        connection_panel.pack(fill="x", pady=(0, 14))
        controls = tk.Frame(connection_panel, bg=PANEL)
        controls.pack(fill="x", padx=16, pady=13)

        tk.Label(controls, text="Serial port", bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(
            controls,
            textvariable=self.port_var,
            state="readonly",
            width=31,
            style="TGAM.TCombobox",
        )
        self.port_combo.pack(side="left", padx=(8, 8))
        self._button(controls, "Refresh", self.refresh_ports).pack(side="left", padx=(0, 18))

        tk.Label(controls, text="Baud", bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        self.baud_var = tk.StringVar(value=str(DEFAULT_BAUD))
        self.baud_combo = ttk.Combobox(
            controls,
            textvariable=self.baud_var,
            values=("9600", "57600", "115200"),
            state="readonly",
            width=9,
            style="TGAM.TCombobox",
        )
        self.baud_combo.pack(side="left", padx=(8, 18))

        self.connect_button = self._button(controls, "Connect", self.toggle_connection, accent=True)
        self.connect_button.pack(side="left")
        self.demo_button = self._button(controls, "Start Demo", self.toggle_demo)
        self.demo_button.pack(side="left", padx=8)
        self._button(controls, "Export CSV", self.export_csv).pack(side="right")

        metrics = tk.Frame(container, bg=BG)
        metrics.pack(fill="x", pady=(0, 14))
        for column in range(4):
            metrics.grid_columnconfigure(column, weight=1, uniform="metrics")
        self.signal_card = MetricCard(metrics, "Signal quality", GREEN)
        self.attention_card = MetricCard(metrics, "Attention", ACCENT)
        self.meditation_card = MetricCard(metrics, "Relaxation", "#70A9FF")
        self.state_card = MetricCard(metrics, "Current state", YELLOW)
        cards = (self.signal_card, self.attention_card, self.meditation_card, self.state_card)
        for column, card in enumerate(cards):
            card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 6, 0 if column == 3 else 6))

        content = tk.Frame(container, bg=BG)
        content.pack(fill="both", expand=True)
        content.grid_columnconfigure(0, weight=2)
        content.grid_columnconfigure(1, weight=1)
        content.grid_rowconfigure(0, weight=1)
        content.grid_rowconfigure(1, weight=0)

        waveform_panel = self._panel(content, row=0, column=0, sticky="nsew", padx=(0, 7), pady=(0, 7))
        self._section_title(waveform_panel, "Raw EEG waveform", "512 samples/second")
        self.waveform = WaveformCanvas(waveform_panel)
        self.waveform.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        bands_panel = self._panel(content, row=0, column=1, rowspan=2, sticky="nsew", padx=(7, 0))
        self._section_title(bands_panel, "EEG power bands", "Relative, unitless values")
        self.band_chart = BandChart(bands_panel)
        self.band_chart.pack(fill="both", expand=True, padx=16, pady=(3, 8))
        tk.Label(
            bands_panel,
            text="Band values are intended for relative comparison over time.",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 8),
            anchor="w",
        ).pack(fill="x", padx=18, pady=(0, 14))

        summary_panel = self._panel(content, row=1, column=0, sticky="ew", padx=(0, 7), pady=(7, 0))
        self._section_title(summary_panel, "Session summary")
        summary_body = tk.Frame(summary_panel, bg=PANEL)
        summary_body.pack(fill="x", padx=18, pady=(2, 15))
        self.summary_title = tk.Label(
            summary_body,
            text="Waiting for TGAM data",
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI Semibold", 15),
            anchor="w",
        )
        self.summary_title.pack(fill="x")
        self.summary_details = tk.Label(
            summary_body,
            text="Dominant band: --   ·   Average attention: --   ·   Average relaxation: --",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 9),
            anchor="w",
        )
        self.summary_details.pack(fill="x", pady=(3, 0))

        footer = tk.Frame(container, bg=BG)
        footer.pack(fill="x", pady=(12, 0))
        self.protocol_status = tk.Label(
            footer,
            text="Packets: 0   ·   Checksum errors: 0   ·   Bytes: 0",
            bg=BG,
            fg=MUTED,
            font=("Consolas", 8),
        )
        self.protocol_status.pack(side="left")
        tk.Label(
            footer,
            text="Prototype interpretation only — not a medical diagnosis.",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 8),
        ).pack(side="right")

    def refresh_ports(self) -> None:
        self.port_devices.clear()
        labels: list[str] = []
        if list_ports is not None:
            for info in sorted(list_ports.comports(), key=lambda item: item.device):
                label = f"{info.device}  —  {info.description}"
                labels.append(label)
                self.port_devices[label] = info.device

        if labels:
            self.port_combo.configure(values=labels)
            if self.port_var.get() not in labels:
                self.port_var.set(labels[0])
        else:
            placeholder = "No serial ports found"
            self.port_combo.configure(values=(placeholder,))
            self.port_var.set(placeholder)

    def toggle_connection(self) -> None:
        if self.serial_worker is not None:
            self.disconnect_serial()
            return

        selected = self.port_var.get()
        port = self.port_devices.get(selected)
        if not port:
            messagebox.showinfo(
                APP_TITLE,
                "No serial port is available. Connect the USB adapter and press Refresh.",
            )
            return

        self.stop_demo()
        self.model.reset()
        self.session_rows.clear()
        self._last_record_second = -1
        self.parser_stats = ParserStats()
        self.current_port = port
        self.connection_badge.configure(text=f"●  CONNECTING {port}", fg=YELLOW)
        self.serial_worker = SerialWorker(port, int(self.baud_var.get()), self.event_queue)
        self.serial_worker.start()
        self.connect_button.configure(text="Disconnect", bg=RED, activebackground=RED)
        self.port_combo.configure(state="disabled")
        self.baud_combo.configure(state="disabled")

    def disconnect_serial(self) -> None:
        worker = self.serial_worker
        self.serial_worker = None
        if worker is not None:
            worker.stop()
        self.connected = False
        self.connect_button.configure(text="Connect", bg=ACCENT, activebackground=GREEN)
        self.port_combo.configure(state="readonly")
        self.baud_combo.configure(state="readonly")
        self.connection_badge.configure(text="●  DISCONNECTED", fg=MUTED)

    def toggle_demo(self) -> None:
        if self.demo_active:
            self.stop_demo()
        else:
            self.start_demo()

    def start_demo(self) -> None:
        self.disconnect_serial()
        self.demo_engine.reset()
        self.model.reset()
        self.session_rows.clear()
        self._last_record_second = -1
        self.parser_stats = ParserStats()
        self.demo_active = True
        self.demo_button.configure(text="Stop Demo", bg=YELLOW, fg=BG)
        self.connection_badge.configure(text="●  DEMO MODE", fg=YELLOW)

    def stop_demo(self) -> None:
        if not self.demo_active:
            return
        self.demo_active = False
        self.demo_button.configure(text="Start Demo", bg=PANEL_ALT, fg=TEXT)
        if not self.connected:
            self.connection_badge.configure(text="●  DISCONNECTED", fg=MUTED)

    def _demo_tick(self) -> None:
        if self._closing:
            return
        if self.demo_active:
            for packet in self.demo_engine.step():
                self.model.update(packet)
            self.parser_stats = self.demo_engine.parser.stats
        self.root.after(20, self._demo_tick)

    def _poll_queue(self) -> None:
        if self._closing:
            return
        while True:
            try:
                event = self.event_queue.get_nowait()
            except queue.Empty:
                break

            kind = event[0]
            if kind == "packet":
                self.model.update(event[1])
            elif kind == "stats":
                self.parser_stats = event[1]
            elif kind == "connection":
                self.connected = bool(event[1])
                port = event[2]
                if self.connected:
                    self.connection_badge.configure(text=f"●  CONNECTED {port}", fg=GREEN)
                elif self.serial_worker is not None:
                    self.serial_worker = None
                    self.connect_button.configure(text="Connect", bg=ACCENT, activebackground=GREEN)
                    self.port_combo.configure(state="readonly")
                    self.baud_combo.configure(state="readonly")
                    self.connection_badge.configure(text="●  DISCONNECTED", fg=MUTED)
            elif kind == "error":
                self.disconnect_serial()
                messagebox.showerror(APP_TITLE, event[1])

        self.root.after(20, self._poll_queue)

    def _update_display(self) -> None:
        if self._closing:
            return

        signal = self.model.poor_signal
        if signal is None:
            self.signal_card.set("--", "Waiting for data", 0)
        else:
            color = GREEN if signal <= 25 else YELLOW if signal <= 50 else RED
            quality_percent = max(0, 100 - min(200, signal) / 2)
            self.signal_card.set(str(signal), self.model.signal_label, quality_percent, color)

        attention = self.model.attention
        meditation = self.model.meditation
        self.attention_card.set(
            "--" if attention is None else f"{attention}%",
            "eSense attention",
            0 if attention is None else attention,
        )
        self.meditation_card.set(
            "--" if meditation is None else f"{meditation}%",
            "eSense meditation",
            0 if meditation is None else meditation,
        )

        state = self.model.state_summary
        state_color = RED if "contact" in state.lower() or "not detected" in state.lower() else TEXT
        self.state_card.set(state, f"Dominant: {self.model.dominant_band}", 100 if self.model.has_data else 0, state_color)

        self.waveform.draw(self.model.raw_samples)
        self.band_chart.draw(self.model.bands)
        self.summary_title.configure(text=state)

        avg_attention = self.model.average(self.model.attention_history)
        avg_meditation = self.model.average(self.model.meditation_history)
        avg_attention_text = "--" if avg_attention is None else f"{avg_attention:.0f}%"
        avg_meditation_text = "--" if avg_meditation is None else f"{avg_meditation:.0f}%"
        self.summary_details.configure(
            text=(
                f"Dominant band: {self.model.dominant_band}   ·   "
                f"Average attention: {avg_attention_text}   ·   "
                f"Average relaxation: {avg_meditation_text}"
            )
        )

        stats = self.parser_stats
        self.protocol_status.configure(
            text=(
                f"Packets: {stats.packets_ok:,}   ·   "
                f"Checksum errors: {stats.checksum_errors:,}   ·   "
                f"Bytes: {stats.bytes_received:,}"
            )
        )
        self.root.after(100, self._update_display)

    def _record_snapshot(self) -> None:
        if self._closing:
            return
        if self.model.has_data:
            elapsed_second = int(self.model.elapsed_seconds)
            if elapsed_second != self._last_record_second:
                self._last_record_second = elapsed_second
                snapshot = self.model.snapshot()
                snapshot["timestamp"] = datetime.now().isoformat(timespec="seconds")
                snapshot["mode"] = "Demo" if self.demo_active else "Serial"
                self.session_rows.append(snapshot)
        self.root.after(1000, self._record_snapshot)

    def export_csv(self) -> None:
        if not self.session_rows:
            messagebox.showinfo(APP_TITLE, "No session data is available to export.")
            return

        suggested = f"TGAM_session_{datetime.now():%Y%m%d_%H%M%S}.csv"
        path = filedialog.asksaveasfilename(
            title="Export TGAM session",
            defaultextension=".csv",
            initialfile=suggested,
            filetypes=(("CSV file", "*.csv"), ("All files", "*.*")),
        )
        if not path:
            return

        fields = (
            "timestamp",
            "mode",
            "elapsed_seconds",
            "poor_signal",
            "signal_label",
            "attention",
            "meditation",
            "average_attention",
            "average_meditation",
            "dominant_band",
            "state",
            *EEG_BANDS,
        )
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(self.session_rows)
            messagebox.showinfo(APP_TITLE, f"Session exported successfully:\n{path}")
        except OSError as error:
            messagebox.showerror(APP_TITLE, f"Could not save the CSV file:\n{error}")

    def close(self) -> None:
        self._closing = True
        if self.serial_worker is not None:
            self.serial_worker.stop()
        self.root.destroy()


def enable_windows_dpi_awareness() -> None:
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def main() -> None:
    enable_windows_dpi_awareness()
    root = tk.Tk()
    TGAMApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
