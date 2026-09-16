"""Independent native monitor for the local, explicitly simulated EEG demo.

Only DemoEngine supplies state; this module never opens a serial connection.
Run launch_demo.py (or this file) to open the linked monitor and AR windows.
"""
from __future__ import annotations

from collections import deque
import math
import time
import tkinter as tk
from tkinter import ttk

from legacy_monitor import (
    BG, PANEL, PANEL_ALT, BORDER, GRID, TEXT, MUTED, ACCENT, GREEN, YELLOW, RED,
    MetricCard, WaveformCanvas, BandChart,
)
from thinkgear import EEG_BANDS, BAND_LABELS


class DemoWaveform(WaveformCanvas):
    """Responsive version of the original canvas, with honest demo units."""
    def draw(self, samples):
        self.delete("all")
        width, height = max(180, self.winfo_width()), max(80, self.winfo_height())
        left, top, right, bottom = 48, 12, width - 12, height - 25
        for fraction in (0, .25, .5, .75, 1):
            x, y = left + (right-left)*fraction, top + (bottom-top)*fraction
            self.create_line(left, y, right, y, fill=GRID)
            self.create_line(x, top, x, bottom, fill=GRID)
        self.create_text(left, bottom+14, anchor="w", text="SIMULATED RAW COUNTS",
                         fill=MUTED, font=("Segoe UI", 8))
        values = list(samples)
        if len(values) < 2:
            return
        peak = sorted(abs(v) for v in values)[min(len(values)-1, int(len(values)*.95))]
        scale = max(100, peak*1.25)
        center, amplitude = (top+bottom)/2, (bottom-top)*.46
        points = []
        for index, value in enumerate(values):
            points.extend((left+index*(right-left)/(len(values)-1),
                           center-max(-scale, min(scale, value))/scale*amplitude))
        self.create_line(points, fill=ACCENT, width=1.6)
        for y, value in ((top, f"+{scale:.0f}"), (center, "0"), (bottom, f"-{scale:.0f}")):
            self.create_text(5, y, anchor="w", text=value, fill=MUTED, font=("Consolas", 8))


class DemoBands(BandChart):
    """Eight original bands, fitted to the available panel height."""
    def draw(self, bands):
        self.delete("all")
        width, height = max(190, self.winfo_width()), max(155, self.winfo_height())
        left, right = 76, width-54
        values = [max(0, float(bands.get(band, 0))) for band in EEG_BANDS]
        powers = [math.log10(value+1) for value in values]
        maximum = max(powers, default=1) or 1
        row_height = (height-8)/8
        for i, band in enumerate(EEG_BANDS):
            y = 4+(i+.5)*row_height
            self.create_text(0, y, anchor="w", text=BAND_LABELS[band], fill=TEXT,
                             font=("Segoe UI", 8))
            self.create_rectangle(left, y-4, right, y+4, fill=GRID, outline="")
            self.create_rectangle(left, y-4, left+(right-left)*powers[i]/maximum, y+4,
                                  fill=ACCENT if i<4 else GREEN, outline="")
            self.create_text(width-2, y, anchor="e", text=f"{values[i]:,.0f}",
                             fill=MUTED, font=("Consolas", 8))


def validate_settings(values):
    """English validation before passing settings to the shared engine."""
    result = {}
    labels = {"baseline": "Baseline", "focus": "Focus", "threshold": "Threshold", "dwell_ms": "Dwell time"}
    for key, label in labels.items():
        try:
            value = float(values[key])
            if not math.isfinite(value) or value != int(value):
                raise ValueError
            result[key] = int(value)
        except (ValueError, TypeError, OverflowError):
            raise ValueError(f"{label} must be a whole number.") from None
    if not 0 <= result["baseline"] < result["threshold"] <= result["focus"] <= 100:
        raise ValueError("Use 0 <= baseline < threshold <= focus <= 100.")
    if not 500 <= result["dwell_ms"] <= 10000:
        raise ValueError("Dwell time must be between 500 and 10,000 ms.")
    return result


def _english_event(event):
    kind = str(event.get("kind", "system"))
    labels = {"system": "Virtual EEG demo ready", "reset": "Demo reset",
              "config": "Demo parameters updated", "disconnected": "AR disconnected; intention cancelled",
              "hover": "Focus started", "leave": "Target released",
              "click": "Click received; waiting for attention", "confirmed": "Intention confirmed"}
    label = labels.get(kind, "Demo state updated")
    if kind in {"hover", "leave", "confirmed"}:
        suffix = str(event.get("label", "")).rsplit(" · ", 1)[-1]
        if suffix and not any("\u3400" <= c <= "\u9fff" for c in suffix):
            label += " · " + suffix
    return label


class DemoMonitor:
    def __init__(self, root, engine, open_ar, on_close):
        self.root, self.engine = root, engine
        self._open_ar_callback, self._on_close_callback = open_ar, on_close
        self._closing, self._after_id = False, None
        self._raw = deque(maxlen=1024)
        self._last_raw, self._last_raw_time = (), None
        self._last_events, self._reset_seq = None, None
        self._last_confirmation_seq, self._confirmation_base = 0, 0
        self._last_confirmed_label = None
        self._config_loaded, self._parameters_open = False, False
        self._progress = 0.0
        self.root.title("EchoMind EEG Monitor · Demo")
        self.root.configure(bg=BG)
        self.root.minsize(900, 680)
        self.root.geometry("1100x800")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._build()
        self._refresh()

    def _label(self, parent, text, color=TEXT, size=10, bold=False, **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color,
                        font=("Segoe UI Semibold" if bold else "Segoe UI", size), **kwargs)

    def _panel(self, parent):
        return tk.Frame(parent, bg=PANEL, highlightbackground=BORDER, highlightthickness=1, bd=0)

    def _button(self, parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command, bg=ACCENT if primary else PANEL_ALT,
                         fg=BG if primary else TEXT, activebackground=GREEN if primary else BORDER,
                         activeforeground=BG if primary else TEXT, bd=0, padx=14, pady=8,
                         cursor="hand2", font=("Segoe UI Semibold", 9), highlightthickness=0)

    def _build(self):
        shell = tk.Frame(self.root, bg=BG, padx=18, pady=14)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(4, weight=1, minsize=215)

        header = tk.Frame(shell, bg=BG)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        self._label(header, "EchoMind EEG Monitor", size=21, bold=True).grid(row=0, column=0, sticky="w")
        self._label(header, "VIRTUAL EEG · MOUSE DEMO", ACCENT, 10, True).grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.ar_status = self._label(header, "AR DISCONNECTED", YELLOW, 10, True, padx=12, pady=6)
        self.ar_status.configure(bg=PANEL_ALT)
        self.ar_status.grid(row=0, column=1, rowspan=2, sticky="e")

        metrics = tk.Frame(shell, bg=BG)
        metrics.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.cards = {}
        for i, (key, title, color) in enumerate((("attention", "Attention", ACCENT),
                ("relaxation", "Relaxation", GREEN), ("quality", "Virtual signal", ACCENT),
                ("phase", "Current state", YELLOW))):
            metrics.columnconfigure(i, weight=1, uniform="metric")
            card = MetricCard(metrics, title, color)
            card.configure(padx=12, pady=9)
            card.value_label.configure(font=("Segoe UI Semibold", 22))
            card.grid(row=0, column=i, sticky="nsew", padx=(0, 8 if i<3 else 0))
            self.cards[key] = card

        focus = self._panel(shell)
        focus.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        focus.columnconfigure(0, weight=1)
        focus.columnconfigure(1, weight=1)
        target_box = tk.Frame(focus, bg=PANEL)
        target_box.grid(row=0, column=0, sticky="nsew", padx=14, pady=10)
        self._label(target_box, "CURRENT TARGET", MUTED, 8, True).pack(anchor="w")
        self.target_label = self._label(target_box, "Waiting for a target", TEXT, 14, True, anchor="w")
        self.target_label.pack(fill="x", pady=(3, 4))
        target_box.bind("<Configure>", lambda event: self.target_label.configure(wraplength=max(180, event.width-12)))
        self.focus_hint = self._label(target_box, "Hover over a control in the AR window.", MUTED, 9, anchor="w")
        self.focus_hint.pack(fill="x")
        progress_box = tk.Frame(focus, bg=PANEL)
        progress_box.grid(row=0, column=1, sticky="nsew", padx=14, pady=10)
        self.progress_text = self._label(progress_box, "CONFIRMATION  0%", MUTED, 9, True, anchor="w")
        self.progress_text.pack(fill="x", pady=(0, 6))
        self.progress_canvas = tk.Canvas(progress_box, bg=GRID, height=8, highlightthickness=0)
        self.progress_canvas.pack(fill="x")
        self.progress_canvas.bind("<Configure>", lambda _event: self._draw_progress())
        self.threshold_label = self._label(progress_box, "Threshold 75 / 100 · Dwell 1.6 s", MUTED, 9, anchor="w")
        self.threshold_label.pack(fill="x", pady=(7, 0))

        actions = tk.Frame(shell, bg=BG)
        actions.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        self._button(actions, "Open AR window", self._open_ar, True).pack(side="left")
        self._button(actions, "Reset demo", self._reset).pack(side="left", padx=8)
        self.low_attention = tk.BooleanVar(value=False)
        tk.Checkbutton(actions, text="Low attention · block confirmation", variable=self.low_attention,
                       command=self._change_mode, bg=BG, fg=TEXT, activebackground=BG,
                       activeforeground=ACCENT, selectcolor=PANEL_ALT, bd=0,
                       font=("Segoe UI", 9), cursor="hand2").pack(side="left", padx=4)
        self._button(actions, "Exit", self.close).pack(side="right")

        charts = tk.Frame(shell, bg=BG)
        charts.grid(row=4, column=0, sticky="nsew", pady=(0, 10))
        charts.rowconfigure(0, weight=1)
        for i, weight in enumerate((43, 31, 26)):
            charts.columnconfigure(i, weight=weight, uniform="body")
        waveform_panel = self._panel(charts)
        waveform_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._label(waveform_panel, "RAW WAVEFORM", TEXT, 10, True).pack(anchor="w", padx=12, pady=(11, 2))
        self._label(waveform_panel, "Synthetic waveform · rolling view", MUTED, 8).pack(anchor="w", padx=12)
        self.waveform = DemoWaveform(waveform_panel)
        self.waveform.configure(height=220)
        self.waveform.pack(fill="both", expand=True, padx=5, pady=(3, 5))
        bands_panel = self._panel(charts)
        bands_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 8))
        self._label(bands_panel, "EEG BAND POWER", TEXT, 10, True).pack(anchor="w", padx=12, pady=(11, 2))
        self._label(bands_panel, "Simulated values · log-scale bars", MUTED, 8).pack(anchor="w", padx=12)
        self.bands = DemoBands(bands_panel)
        self.bands.configure(height=220)
        self.bands.pack(fill="both", expand=True, padx=10, pady=(5, 8))
        events_panel = self._panel(charts)
        events_panel.grid(row=0, column=2, sticky="nsew")
        self._label(events_panel, "EVENT LOG", TEXT, 10, True).pack(anchor="w", padx=12, pady=(11, 2))
        self.event_count = self._label(events_panel, "0 confirmations", MUTED, 8)
        self.event_count.pack(anchor="w", padx=12, pady=(0, 6))
        event_body = tk.Frame(events_panel, bg=PANEL)
        event_body.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.events_text = tk.Text(event_body, bg=PANEL, fg=MUTED, font=("Segoe UI", 9),
                                   bd=0, highlightthickness=0, wrap="word", width=1, height=6,
                                   state="disabled", cursor="arrow", padx=2, spacing3=7)
        self.events_text.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(event_body, command=self.events_text.yview)
        scroll.pack(side="right", fill="y")
        self.events_text.configure(yscrollcommand=scroll.set)
        self.events_text.tag_configure("confirmed", foreground=GREEN)
        self.events_text.tag_configure("stamp", foreground=MUTED, font=("Consolas", 8))
        self.events_text.tag_configure("regular", foreground=TEXT)

        params = self._panel(shell)
        params.grid(row=5, column=0, sticky="ew", pady=(0, 7))
        parameter_top = tk.Frame(params, bg=PANEL)
        parameter_top.pack(fill="x", padx=10, pady=5)
        self.parameter_toggle = self._button(parameter_top, "Demo parameters  +", self._toggle_parameters)
        self.parameter_toggle.configure(pady=5)
        self.parameter_toggle.pack(side="left")
        self.settings_status = self._label(parameter_top, "Hover → focus → confirmed", MUTED, 9, anchor="w")
        self.settings_status.pack(side="left", fill="x", expand=True, padx=12)
        self.parameter_fields = tk.Frame(params, bg=PANEL)
        self.parameters = {}
        defaults = (("baseline", "Baseline", 32), ("focus", "Focus", 90),
                    ("threshold", "Threshold", 75), ("dwell_ms", "Dwell (ms)", 1600))
        for index, (key, label, default) in enumerate(defaults):
            self.parameter_fields.columnconfigure(index, weight=1, uniform="parameter")
            box = tk.Frame(self.parameter_fields, bg=PANEL)
            box.grid(row=0, column=index, sticky="ew", padx=(0, 10))
            self._label(box, label, MUTED, 8).pack(anchor="w")
            variable = tk.StringVar(value=str(default))
            entry = tk.Entry(box, textvariable=variable, bg=PANEL_ALT, fg=TEXT,
                             insertbackground=ACCENT, relief="flat", width=8,
                             font=("Consolas", 10), highlightthickness=1,
                             highlightbackground=BORDER, highlightcolor=ACCENT)
            entry.pack(fill="x", ipady=5, pady=(4, 0))
            entry.bind("<Return>", lambda _event: self._apply_parameters())
            self.parameters[key] = variable
        self._button(self.parameter_fields, "Apply", self._apply_parameters, True).grid(row=0, column=4, sticky="s")
        self._label(shell, "All EEG values are scripted simulations. Mouse hover represents gaze; attention gates confirmation.",
                    MUTED, 8, anchor="w").grid(row=6, column=0, sticky="ew")

    def _status(self, text, error=False):
        self.settings_status.configure(text=text, fg=RED if error else MUTED)

    def _toggle_parameters(self):
        self._parameters_open = not self._parameters_open
        self.parameter_toggle.configure(text="Demo parameters  −" if self._parameters_open else "Demo parameters  +")
        if self._parameters_open:
            self.parameter_fields.pack(fill="x", padx=14, pady=(5, 12))
        else:
            self.parameter_fields.pack_forget()

    def _apply_parameters(self):
        try:
            updates = validate_settings({key: var.get() for key, var in self.parameters.items()})
        except ValueError as error:
            self._status(str(error), True)
            return
        try:
            self.engine.configure(updates)
        except Exception:
            self._status("Could not apply parameters. Check the values and try again.", True)
            return
        self._status("Parameters applied. Hover over a target to begin.")

    def _change_mode(self):
        try:
            self.engine.configure({"mode": "distracted" if self.low_attention.get() else "assisted"})
            self._status("Low attention: clicks cannot confirm." if self.low_attention.get()
                         else "Assisted focus enabled. Hover to confirm.")
        except Exception:
            self.low_attention.set(not self.low_attention.get())
            self._status("Could not change the demo mode. Try again.", True)

    def _open_ar(self):
        try:
            self._open_ar_callback()
        except Exception:
            self._status("Could not open the AR window. Check the local demo launcher.", True)

    def _reset(self):
        try:
            self.engine.reset()
            self._status("Demo reset. Hover over an AR control to begin.")
        except Exception:
            self._status("Could not reset the demo. Try again.", True)

    def _draw_progress(self):
        self.progress_canvas.delete("all")
        self.progress_canvas.create_rectangle(0, 0, self.progress_canvas.winfo_width()*self._progress, 8,
                                              fill=GREEN if self._progress>=1 else ACCENT, outline="")

    def _append_raw(self, raw):
        current = tuple(float(value) for value in raw)
        now = time.monotonic()
        if current and current != self._last_raw:
            count = len(current) if self._last_raw_time is None else max(1, min(len(current), round((now-self._last_raw_time)*256)))
            # Stable windows can be aligned exactly. During attention changes
            # the engine recomputes amplitudes, so use fresh samples at 256 Hz.
            for overlap in range(min(len(current), len(self._last_raw)), 0, -1):
                if self._last_raw[-overlap:] == current[:overlap]:
                    count = len(current)-overlap
                    break
            if count:
                self._raw.extend(current[-count:])
        self._last_raw, self._last_raw_time = current, now

    def _render_events(self, events):
        signature = tuple((str(e.get("time", "")), str(e.get("kind", "")), str(e.get("label", ""))) for e in events)
        if signature == self._last_events:
            return
        self._last_events = signature
        self.events_text.configure(state="normal")
        self.events_text.delete("1.0", "end")
        if not events:
            self.events_text.insert("end", "Confirmed actions appear here.", "stamp")
        for event in events[:32]:
            self.events_text.insert("end", str(event.get("time", ""))+"\n", "stamp")
            self.events_text.insert("end", _english_event(event)+"\n\n",
                                    "confirmed" if event.get("kind")=="confirmed" else "regular")
        self.events_text.configure(state="disabled")

    def _observe_confirmations(self, state):
        """Retain the last accepted action independently of the live phase."""
        sequence = int(state.get("confirmation_seq", 0))
        reset_sequence = state.get("reset_seq", 0)
        reset_changed = reset_sequence != self._reset_seq
        if reset_changed:
            self._reset_seq = reset_sequence
            self._confirmation_base = sequence
            self._last_confirmed_label = None
        elif sequence > self._last_confirmation_seq:
            confirmed = next((event for event in state.get("events", [])
                              if event.get("kind") == "confirmed"), None)
            if confirmed:
                english = _english_event(confirmed)
                self._last_confirmed_label = english.partition(" · ")[2] or "AR action"
            else:
                self._last_confirmed_label = "AR action"
        self._last_confirmation_seq = sequence
        return reset_changed

    def _refresh(self):
        if self._closing:
            return
        try:
            state = self.engine.snapshot()
            config = state.get("config", {})
            if not self._config_loaded:
                for key, variable in self.parameters.items():
                    if key in config:
                        variable.set(str(config[key]))
                self._config_loaded = True
            self.low_attention.set(config.get("mode")=="distracted")
            if self._observe_confirmations(state):
                self._raw.clear()
                self._last_raw, self._last_raw_time = (), None
            attention = max(0, min(100, float(state.get("attention", 0))))
            relaxation = max(0, min(100, float(state.get("relaxation", 0))))
            quality = max(0, min(100, float(state.get("quality", 100))))
            threshold, dwell = config.get("threshold", 75), config.get("dwell_ms", 1600)
            phase = state.get("phase", "idle")
            phase_color = GREEN if phase=="confirmed" else YELLOW if phase=="distracted" else ACCENT
            self.cards["attention"].set(f"{attention:.0f}", f"Confirmation threshold: {threshold}", attention, ACCENT)
            self.cards["relaxation"].set(f"{relaxation:.0f}", "Simulated relaxation / 100", relaxation, GREEN)
            self.cards["quality"].set(f"{quality:.0f}%", "Virtual signal · no sensor", quality, ACCENT)
            names = {"idle": "Idle", "focusing": "Focusing", "ready": "Ready", "confirmed": "Confirmed", "distracted": "Distracted"}
            details = {"idle": "Waiting for a target", "focusing": "Attention is rising", "ready": "Hold focus to confirm",
                       "confirmed": "Intention accepted", "distracted": "Confirmation blocked"}
            self.cards["phase"].set(names.get(phase, "Idle"), details.get(phase, "Demo running"),
                                    float(state.get("progress", 0))*100, phase_color)
            connected = bool(state.get("ar_connected"))
            self.ar_status.configure(text="AR CONNECTED" if connected else "AR DISCONNECTED", fg=GREEN if connected else YELLOW)
            target = state.get("target") or {}
            target_label = str(target.get("label") or "Waiting for a target")
            if any("\u3400" <= c <= "\u9fff" for c in target_label):
                target_label = str(target.get("id", "AR target")).replace("_", " ").title()
            self.target_label.configure(text=target_label)
            hint = ("Low attention: clicking does not confirm." if phase=="distracted"
                    else "Confirmed. Continue in the AR window." if phase=="confirmed"
                    else "Hover → focus → confirmed" if target
                    else "Hover over a control in the AR window.")
            if self._last_confirmed_label:
                self.focus_hint.configure(text=f"Last confirmed: {self._last_confirmed_label}", fg=GREEN)
            else:
                self.focus_hint.configure(text=hint, fg=phase_color if target else MUTED)
            self._progress = max(0, min(1, float(state.get("progress", 0))))
            self.progress_text.configure(text=f"CONFIRMATION  {self._progress:.0%}", fg=phase_color)
            self.threshold_label.configure(text=f"Threshold {threshold} / 100 · Dwell {dwell/1000:g} s")
            self._draw_progress()
            self._append_raw(state.get("raw", []))
            self.waveform.draw(self._raw)
            self.bands.draw(state.get("bands", {}))
            confirmation_count = max(0, self._last_confirmation_seq-self._confirmation_base)
            self.event_count.configure(text=f"{confirmation_count} confirmation" + ("" if confirmation_count==1 else "s"))
            self._render_events(state.get("events", []))
        except tk.TclError:
            return
        except Exception:
            self._status("Monitor update unavailable. Retrying the local demo connection…", True)
        self._after_id = self.root.after(100, self._refresh)

    def close(self):
        if self._closing:
            return
        self._closing = True
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except tk.TclError:
                pass
        try:
            self._on_close_callback()
        finally:
            try:
                if self.root.winfo_exists():
                    self.root.destroy()
            except tk.TclError:
                pass


if __name__ == "__main__":
    from launch_demo import main
    main()
