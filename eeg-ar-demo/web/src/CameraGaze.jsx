import { useEffect, useState } from 'react';
import { startCameraGazeBridge } from './cameraGazeBridge';
import { cameraTargetAt } from './gazeInputCore';
import { input, useInputMode } from './gazeInput';

function cameraMessage(status) {
  if (!status?.environment.fullscreen) return 'Enter fullscreen on the same monitor used for calibration.';
  if (!status.environment.focused || !status.environment.visible) return 'Paused · Return to this page to continue.';
  const sample = status.sample;
  if (!sample?.connected) return 'Open the eye app and enable Link camera to AR.';
  if (!sample.enabled || sample.reason === 'disabled') return 'Enable Link camera to AR in the eye app.';
  if (sample.reason === 'calibrating') return 'Calibration in progress · Gaze is paused.';
  if (!sample.calibrated || sample.reason === 'uncalibrated') return 'Complete 9-point calibration in the eye app first.';
  if (sample.reason === 'camera_off') return 'Connect your camera in the eye app.';
  if (sample.reason === 'synthetic') return 'Switch the eye app to Live camera.';
  if (!status.point) return 'Tracking paused · Keep both eyes inside their selected areas.';
  return `${sample.eyes === 2 ? 'Both eyes' : 'Eye'} tracked · Look at a control and hold to confirm.`;
}

export function CameraGaze() {
  const mode = useInputMode();
  const [status, setStatus] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const stop = startCameraGazeBridge(next => {
      setStatus(next);
      input.cameraAt(cameraTargetAt(document, next.point), next.environment.now);
    });
    return () => { stop(); input.suspend(); };
  }, []);
  useEffect(() => {
    document.body.dataset.inputSource = mode;
    setError('');
  }, [mode]);
  const fullscreen = Boolean(status?.environment.fullscreen);
  const point = mode === 'camera' ? status?.point : null;
  const enterFullscreen = async () => {
    input.suspend();
    setError('');
    try { await document.documentElement.requestFullscreen(); }
    catch { setError('Fullscreen could not start. Click the button again in a supported browser.'); }
  };
  return <>
    {point && <div className="eye-pointer-demo camera-gaze-demo" aria-hidden="true" data-testid="camera-linked-gaze">
      <span className="eye-pointer-ring" style={{ left: point.x, top: point.y }}><i /></span>
      <span className="eye-pointer-label">CAMERA GAZE · EEG SIMULATED</span>
    </div>}
    <aside className={`gaze-source-panel ${mode === 'camera' ? 'is-camera' : ''}`} aria-label="Gaze input source" data-testid="gaze-source-panel">
      <div className="gaze-source-options" role="group" aria-label="Input source">
        <button type="button" aria-pressed={mode === 'mouse'} onClick={() => input.setMode('mouse')}>Mouse demo</button>
        <button type="button" aria-pressed={mode === 'camera'} onClick={() => input.setMode('camera')}>Camera gaze</button>
      </div>
      {mode === 'camera' && <>
        <strong className={`camera-link-state ${point ? 'is-tracking' : ''}`}><i />{point ? 'CAMERA GAZE · EEG SIMULATED' : 'CAMERA GAZE · PAUSED'}</strong>
        <p role="status">{error || cameraMessage(status)}</p>
        {!fullscreen && <button type="button" className="gaze-fullscreen-button" onClick={enterFullscreen}>Start fullscreen gaze</button>}
        {fullscreen && <small>Esc exits fullscreen · Camera video stays local</small>}
      </>}
    </aside>
  </>;
}
