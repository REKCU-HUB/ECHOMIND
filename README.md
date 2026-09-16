# EchoMind

AR glasses interaction prototype combining gaze input with EEG-assisted intent confirmation.

## Latest demo — 2026-09-16

The current Windows demo connects a real eye camera to the EchoMind AR interface. One camera can track two separately selected eye regions. Both eyes are calibrated independently before their screen positions are combined.

**Camera gaze is real; EEG attention, waveforms and confirmation assistance in the linked demo are simulated.** The original serial EEG monitor and Arduino controller remain available at the repository root.

Download the Windows bundle from [Releases](https://github.com/REKCU-HUB/ECHOMIND/releases). It includes both standalone applications, the offline AR website and launch instructions; Python and Node are not needed to run the bundle.

### Use the camera link

1. Start the EEG/AR companion and the eye demo using the bundle's **Start Camera AR** launcher.
2. In the eye app, select **Live camera**, connect your camera, and use **Two eyes / one camera**. Select eye A and eye B in the image.
3. Complete **9-point calibration**. Live previews of both eyes help keep the camera and head position stable. Press **Esc** after calibration.
4. Keep **Link camera to AR** enabled. On the webpage, select **Camera gaze** and **Start fullscreen gaze** on the same monitor used for calibration.
5. Look at a supported control and hold. The existing simulated EEG threshold and dwell time decide when it activates. Missing eyes, stale video, window blur or leaving fullscreen pause gaze input.

Actual gaze accuracy depends on your camera, pupil visibility and personal calibration. Camera frames remain in the eye application; only gaze coordinates and tracking status cross the local connection.

The separate **Mouse demo / AR linked demo** mode retains the mouse-driven virtual eye presentation. The in-page attention panel can be moved, resized and hidden.

## Repository contents

| Path | Purpose |
|---|---|
| [`pupil-gaze-demo/`](pupil-gaze-demo/) | English Windows eye tracker, single-eye and binocular calibration, live calibration previews and real gaze publisher |
| [`eeg-ar-demo/`](eeg-ar-demo/) | Independent simulated EEG monitor, local HTTP bridge and React AR website |
| [`eeg-ar-demo/web/dist/`](eeg-ar-demo/web/dist/) | Built offline webpage included for running the Python desktop companion |
| [`app.py`](app.py), [`thinkgear.py`](thinkgear.py) | Earlier serial TGAM EEG monitor and protocol parser |
| [`ar_glasses_controller.ino`](ar_glasses_controller.ino) | Earlier Arduino glasses controller |

## Run from source

Use Python with Tkinter. The eye application was built with 64-bit Python 3.12.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r pupil-gaze-demo/requirements.txt
.\.venv\Scripts\python.exe eeg-ar-demo/launch_demo.py --no-browser --port 8765
```

Keep the companion open; in another terminal:

```powershell
.\.venv\Scripts\python.exe pupil-gaze-demo/app.py --binocular --camera-ar --open-ar
```

For mouse presentation use `--ar-demo --open-ar` instead. The legacy serial EEG monitor optionally uses `pyserial` (`python -m pip install pyserial`).

To rebuild the web interface with Node.js 22.12 or later:

```powershell
cd eeg-ar-demo/web
npm ci
npm run build
```

## Verification and packaging

Run `python -m unittest discover -s tests` inside each Python project. Run `node --test tests/*.test.mjs` inside `eeg-ar-demo`. The 2026-09-16 update passed 101 eye-app tests, 30 companion tests and 21 frontend tests, plus isolated local browser checks of gaze coordinates, dwell confirmation, low attention and lost tracking.

Each project contains a PyInstaller `.spec` file. Build the webpage first, then run `python -m PyInstaller --noconfirm <project-spec-file>` from each project directory. Executables are distributed as Release assets rather than stored in Git history.

See the [eye application guide](pupil-gaze-demo/README.md) and [EEG/AR guide](eeg-ar-demo/README.md) for detailed controls and troubleshooting.
