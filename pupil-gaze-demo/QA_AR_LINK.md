# English UI and linked demo QA

## Real camera-to-AR checks

- Only real, calibrated, fresh camera detections publish active screen-normalized coordinates. Relative motion, synthetic frames, native calibration/fullscreen, lost eyes and stale capture timestamps cannot activate the webpage.
- Opening AR from Live camera preserves the camera and calibration; the mouse-linked virtual-eye demo remains an explicit separate mode.
- Web Camera gaze requires fullscreen on the calibrated monitor and suppresses mouse target input. A background/hidden page, fullscreen exit or lost transport clears the ring and EEG focus.
- Multiple known test coordinates must map to the web ring and registered dwell controls. Confirmation must still wait for the Python EEG engine; low simulated attention must block it.
- No video transport; loopback and same-origin protections remain in force.
- Build both standalone executables and check the installed pair. Real-person calibration/accuracy requires user positioning and cannot be substituted with simulated QA input.

### Real gaze verification, 2026-09-16

- Eye app: 101 Python tests passed; local companion: 30 Python tests passed; web bridge: 21 JavaScript tests passed.
- Isolated localhost QA at port 8878 used numeric test coordinates, not camera footage. Fullscreen ring positions matched the supplied normalized coordinates; dwell and simulated EEG confirmation opened the menu and its request dialog.
- Low simulated attention blocked activation. Camera mode ignored physical mouse target movement. Lost-eye status and an expired stream removed the ring and cleared focus. Mouse demo still confirmed normally after switching modes.
- Fixed native recalibration briefly exposing a previous coordinate and fullscreen-button blur incorrectly pausing gaze. Native v1.3 controls were visually checked using the clearly labeled synthetic binocular fixture.
- Real-user camera alignment, calibration and measured gaze accuracy still require the user; no camera footage was uploaded for these checks.
- Both desktop executables were rebuilt, installed and hash-checked. The Camera AR shortcut starts the binocular app, companion and dedicated AR camera page. Installed `/api/gaze` reports connected=true, eyes=2 and inactive/camera_off while awaiting device selection; the installed page serves the final verified bundle. Test browser and port 8878 server were closed.

## Calibration eye preview checks

- Both eye crops and their pupil overlays appear in preparation, sampling, retry, error, validation and completion.
- Fixed ROI previews share the mirrored full-frame coordinates and retain aspect ratio.
- Missing video removes old images and lock labels; loss/low quality is reported for each eye independently.
- The preview avoids all nine calibration targets and the held-out validation target, including a compact fullscreen viewport.
- Existing calibration sampling and rejection rules remain unchanged. Verify layout with the synthetic two-eye fixture and rebuild the installed executable.

### Preview verification, 2026-09-16

- All 82 Python tests passed. New coverage checks crop pixels and full-frame overlays, no accidental second mirror, independent eye lock/quality, stale-image clearing, each calibration stage, and target clearance at 640 x 480 through 1920 x 1080.
- In the native fullscreen UI, selected both synthetic eye regions and entered calibration normally. Both eye crops and pupil marks remained visible during the preparation and live sampling stages; no camera image was captured for QA.
- The preview is display-only: calibration timing, sample acceptance and validation thresholds were unchanged.
- Version 1.2.1 standalone build succeeded, installed executable hash matches the build, and the restarted binocular app responds normally. The existing desktop shortcut opens the updated version.

## Real binocular camera checklist

- One full camera frame feeds two independent selected eye regions and overlays.
- The preview crops to the union of both eye regions; reselection, cancellation and mirroring preserve coordinate alignment.
- Missing either pupil pauses the fused point; missing video clears stale overlays.
- Both eyes receive independent calibration and independent held-out validation before fusion.
- Single-eye mode and AR simulation remain available, with separate calibration state.
- The UI stays English. Synthetic fixtures are labeled; no unmeasured accuracy claim.
- Check the installed executable after rebuilding. Real-person validation requires the user's eye alignment and calibration.

### Binocular verification, 2026-09-16

- All 75 Python tests passed, including paired image detection, independent calibration, per-eye held-out validation, crop/mirror/selection flows, and missing-eye pause. Existing AR/single-eye tests still pass.
- On-screen synthetic fixture: selected eye A then eye B through the actual UI; both independent green pupil overlays locked and the preview cropped to the union of the regions. No real camera image was needed or captured for this QA.
- Adjusted window spacing and reserved the bottom controls so multiline selection hints do not push the controls below the window.
- Rebuilt the standalone executable and updated the desktop installation plus the new EchoMind Binocular Camera shortcut.
- Device enumeration currently lists USB2.0 HD UVC WebCam and Brio 95, not a device named exactly USB Camera. No alternate camera was automatically opened. Real-user calibration and measured improvement remain unverified until the user positions the intended camera to show both eyes.

Required checks before desktop delivery:

- The live-camera UI, crop controls, camera errors and calibration screens use English.
- Camera mode still supports horizontal flip and an enlarged eye crop.
- AR linked demo releases the camera and labels the eye/pointer as simulated.
- Move the AR pointer to multiple viewport locations: the page reticle and desktop gaze point use the same normalized x/y; virtual pupil direction agrees.
- Stop moving: a stationary pointer remains active through browser heartbeats.
- Leave or blur the page: the pointer becomes inactive, and no stale target remains live.
- Disconnect the bridge: the native UI stays responsive and shows waiting/unavailable state.
- Stop consuming pointer data: the AR reticle disappears; EEG hover/dwell confirmation and floating-panel controls continue working.
- Reload/resize the webpage: positions still map to the current viewport.
- Switch to Live camera and back: crop/mirror settings are preserved, demo data is never shown as real tracking confidence.
- Check the final standalone eye and EEG/AR executables after rebuilding.

No camera images are needed for this QA: use the synthetic/virtual eye and local webpage.

## Verified 2026-09-16

- Eye application: 45 Python tests passed; companion: 19 Python tests and 9 frontend tests passed. Vite production build and both PyInstaller builds succeeded.
- Source integration: multiple mouse positions matched the webpage ring center exactly; native page percentages and virtual pupil direction agreed. Stationary heartbeats, blur/inactive handling, viewport resize, and consumer disconnect were checked.
- Existing EEG confirmation still required dwell and attention; pointer input did not bypass it. No browser page errors were observed.
- Rebuilt desktop executables were installed and launched through the new linked-demo entry point. The eye application automatically started the local EEG/AR companion and opened its dedicated browser window.
- Packaged check at a 1000 x 700 viewport: mouse (740, 340) produced ring bounds (723, 323, 34, 34), native Page X 74% / Y 49%, and a rightward virtual pupil. The native English layout, disabled camera controls, simulation labels, and v1.1 footer were visually checked.
- Temporary QA browser and port 8878 server were closed. The installed applications and local AR window remain running on port 8765.
