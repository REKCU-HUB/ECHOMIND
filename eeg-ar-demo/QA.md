# Demo verification inventory

- Native EEG window launches independently; AR uses a separate browser app window.
- Idle waveform and eight relative power bands animate; all data visibly marked virtual.
- Hover a target: monitor and website show the same target, attention and progress.
- Leaving early cancels; changing targets restarts dwell and attention.
- A click before the threshold cannot bypass the gate; continued focus confirms once.
- Activate -> thirsty care card -> Send request -> local demo success, no real message.
- Family message selection and reaction remain usable.
- Low-attention mode blocks hover/click confirmation; returning to assisted restores it.
- Valid parameter edits take effect; invalid edits leave prior configuration intact.
- Reset returns AR to its relaxed home screen and clears the monitor state/history.
- Disconnecting the browser cancels a pending target after two seconds.
- Reopen/reload has no stale action. Closing the monitor stops its local server.
- Visual pass: initial/focusing/confirmed/low-attention and settings at desktop and smaller desktop sizes.
- Check layout clipping, readability, input timing, transition continuity, console errors.

## Floating attention panel

- Drag title bar, resize bottom-right corner, hide and reopen.
- Show/hide does not move AR cards or reserve header space.
- Position, size and visibility persist across reload; smaller windows clamp panel bounds.
- Hidden panel leaves the EEG bridge and AR intention gate running.
- Pointer capture ends on release; keyboard adjustment does not move the AR carousel.
- Short voice views scroll; screenshots omit the floating controls.

2026-09-16: Floating-panel browser checks passed at 1280×800 and 800×600: pointer drag/resize, hide/reopen, unchanged primary layout, reload persistence, keyboard move, viewport clamping, and EEG activation with panel hidden. No browser errors.

## Mouse-linked eye demo bridge

2026-09-16: 19 Python tests and 9 JavaScript bridge tests pass; Vite production build passes. New coverage checks finite/ranged coordinate validation, stale sequence rejection, old-window leave isolation, stationary heartbeats, pointer/consumer expiry, local Host/Origin enforcement, EEG engine isolation, exact client-pixel state, throttled transport, immediate inactive messages, hidden-page behavior, disconnect/recovery, and listener cleanup. The pointer listener uses capture so the movable EEG panel does not suppress coordinate tracking. The view overlay has `pointer-events: none` and no layout footprint.
# Latest real camera link verification — 2026-09-16

- Current linked demo: 30 Python companion tests and 21 frontend tests passed; the eye application passed 101 Python tests.
- Real camera coordinates use a separate local endpoint. Fullscreen gaze selection still requires the simulated EEG threshold and dwell time. Lost eyes, stale input and window blur pause selection.
- The browser flow was checked with isolated numeric QA input, including low-attention blocking, mouse/camera exclusivity and resuming mouse demo. Real-person accuracy still requires camera alignment and personal calibration.
- The earlier counts below describe the initial EEG/AR demo, before real gaze support.
