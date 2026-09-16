"""Assemble the standalone Windows demo release without changing application files."""
from __future__ import annotations

import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "releases"
ZIP = OUT / "EchoMind-Demo-Windows-2026-09-16.zip"

README = """# EchoMind Windows Demo — 2026-09-16

Extract the entire ZIP to a folder before launching. Keep both demo folders next
to the two launchers. Windows includes the PowerShell used by the launchers;
Python and Node are not needed. Use Edge or Chrome for the AR window.

## Start the demo

- Double-click **Start Camera AR.cmd** for a real camera gaze demonstration.
- Double-click **Start Mouse Demo.cmd** for a mouse-linked presentation without
  camera calibration. This mode uses simulated gaze.

Each launcher starts the bundled EEG companion (or reuses an EchoMind companion
already listening at 127.0.0.1:8765), waits up to 30 seconds for its local service,
then starts the bundled eye app and opens AR. Close existing eye/EEG demo windows
before changing modes or testing this new release, so the latest bundled apps run.
The EEG monitor remains open while AR is in use. Closing it stops the local link.
The launchers need no administrator access and change no security settings.

## Camera setup and calibration

1. In the eye app, keep Live camera, Two eyes / one camera, and Link camera to AR
   selected. Select your camera and Connect. Both eyes must be visible clearly.
2. Select eye A and eye B, then run 9-point calibration. Keep your camera and head
   still, follow the green targets, and complete validation. The eye previews
   remain visible throughout. Real gaze stays paused until calibration succeeds.
3. Press Esc to return to the eye app. On the AR page, select Camera gaze and
   choose Start fullscreen gaze on the same monitor used for calibration.
4. Look at a dwell-enabled control. The simulated EEG attention and dwell rules
   still determine whether the control activates. Eye loss, switching windows,
   leaving fullscreen, or stale camera frames pauses camera gaze interaction.

Recalibrate after moving the camera/head, changing eye regions or mirroring, or
restarting. Fullscreen is required because calibration covers the entire monitor.
The apps do not move the Windows mouse or automatically click other applications.

## Simulation and local processing

Camera gaze is camera-derived; EEG waveforms, attention, and confirmation support
are ALWAYS SIMULATED. Mouse Demo also simulates gaze. This is a local presentation,
not a medical device. Camera images remain in memory on this computer; only gaze
coordinates and tracking status pass through the loopback connection.

## Manual launch / troubleshooting

When extracted outside Desktop, start
EchoMind-EEG-Demo/EchoMind_EEG_AR_Demo.exe FIRST and wait for the monitor, then start
EchoMind-Eye-Demo/EchoMind_Pupil_Gaze_Demo.exe. The eye app's built-in automatic
companion search expects Desktop/EchoMind-EEG-Demo; the supplied CMD launchers
handle other extraction locations by starting the relative bundled companion.

The linked eye app uses port 8765. If another program occupies that port, the
launcher reports an error instead of connecting the eye app to another service.
Close the conflicting program yourself and retry. If the companion takes longer
than 30 seconds, wait for its monitor and rerun the launcher. See each app's README
for full controls, limitations, and source/build instructions.
"""


def launcher(arguments: str) -> bytes:
    # All paths come from an environment variable, never inserted into PS code.
    # -Command requires no script execution-policy changes.
    ps = (
        "$ErrorActionPreference='Stop'; "
        "$bundle=$env:ECHOMIND_BUNDLE_ROOT; "
        "$companion=Join-Path $bundle 'EchoMind-EEG-Demo\\EchoMind_EEG_AR_Demo.exe'; "
        "$eye=Join-Path $bundle 'EchoMind-Eye-Demo\\EchoMind_Pupil_Gaze_Demo.exe'; "
        "function Test-EchoMind { try { "
        "$health=Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/health' -TimeoutSec 1; "
        "return ($health.ok -eq $true -and $health.service -eq 'echomind-eeg-demo') "
        "} catch { return $false } }; "
        "try { "
        "if (!(Test-Path -LiteralPath $companion -PathType Leaf) -or "
        "!(Test-Path -LiteralPath $eye -PathType Leaf)) { "
        "throw 'Extract the entire ZIP before starting. Both demo EXEs must be next to this launcher in their folders.' }; "
        "if (!(Test-EchoMind)) { "
        "$probe=[System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback,8765); "
        "try { $probe.Start() } catch { "
        "throw 'Port 8765 is already occupied. Close the conflicting program, then retry.' "
        "} finally { $probe.Stop() }; "
        "Write-Host 'Starting EchoMind EEG companion...'; "
        "Start-Process -FilePath $companion -WorkingDirectory (Split-Path -LiteralPath $companion) "
        "-ArgumentList '--no-browser','--port','8765'; "
        "$timer=[System.Diagnostics.Stopwatch]::StartNew(); "
        "$ready=$false; "
        "while ($timer.Elapsed.TotalSeconds -lt 30) { "
        "if (Test-EchoMind) { $ready=$true; break }; Start-Sleep -Milliseconds 400 }; "
        "if (!$ready) { throw 'EchoMind did not become ready on port 8765 within 30 seconds. Wait for the EEG monitor, then retry.' } }; "
        "Write-Host 'Starting EchoMind eye demo...'; "
        f"Start-Process -FilePath $eye -WorkingDirectory (Split-Path -LiteralPath $eye) -ArgumentList {arguments}; "
        "exit 0 "
        "} catch { Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red; exit 1 }"
    )
    lines = [
        "@echo off",
        "setlocal",
        'set "ECHOMIND_BUNDLE_ROOT=%~dp0"',
        f'powershell.exe -NoLogo -NoProfile -Command "{ps}"',
        "if errorlevel 1 (",
        "  echo.",
        "  pause",
        "  exit /b 1",
        ")",
        "exit /b 0",
        "",
    ]
    return "\r\n".join(lines).encode("ascii")


files = {
    "EchoMind-Eye-Demo/EchoMind_Pupil_Gaze_Demo.exe": ROOT / "pupil-gaze-demo/dist/EchoMind_Pupil_Gaze_Demo.exe",
    "EchoMind-Eye-Demo/README.md": ROOT / "pupil-gaze-demo/README.md",
    "EchoMind-EEG-Demo/EchoMind_EEG_AR_Demo.exe": ROOT / "eeg-ar-demo/dist/EchoMind_EEG_AR_Demo.exe",
    "EchoMind-EEG-Demo/README.md": ROOT / "eeg-ar-demo/README.md",
}
extras = {
    "README.md": README.encode("utf-8"),
    "Start Camera AR.cmd": launcher("'--binocular','--camera-ar','--open-ar'"),
    "Start Mouse Demo.cmd": launcher("'--ar-demo','--open-ar'"),
}

OUT.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for name, path in files.items():
        archive.write(path, name)
    for name, data in extras.items():
        archive.writestr(name, data)

with zipfile.ZipFile(ZIP) as archive:
    assert archive.testzip() is None, "ZIP integrity failure"
    assert set(archive.namelist()) == set(files) | set(extras)
    for name, path in files.items():
        digest = hashlib.sha256(archive.read(name)).hexdigest()
        assert digest == hashlib.sha256(path.read_bytes()).hexdigest(), name
        print(f"VERIFIED {name}: {digest}")
    for name, data in extras.items():
        assert archive.read(name) == data, name
        print(f"VERIFIED {name}")

digest = hashlib.sha256(ZIP.read_bytes()).hexdigest()
(OUT / "SHA256SUMS.txt").write_text(f"{digest}  {ZIP.name}\n", encoding="ascii")
print(f"ZIP: {ZIP}")
print(f"BYTES: {ZIP.stat().st_size}")
print(f"SHA256: {digest}")
