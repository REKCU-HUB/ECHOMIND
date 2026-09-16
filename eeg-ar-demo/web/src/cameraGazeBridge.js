import { projectCameraGaze } from './gazeInputCore.js';

// Only gaze numbers cross the local bridge; camera images stay in the native app.
export function startCameraGazeBridge(onChange, win = window, doc = document, fetcher = fetch) {
  let sample = null, receivedAt = -Infinity, stopped = false, inFlight = false, lastRequest = -Infinity, epoch = 0;
  let focused = doc.hasFocus();
  const now = () => win.performance.now();
  const publish = () => {
    if (stopped) return;
    const environment = {
      fullscreen: Boolean(doc.fullscreenElement), visible: !doc.hidden,
      focused: focused && doc.hasFocus(), width: win.innerWidth, height: win.innerHeight,
      now: now(), receivedAt,
    };
    onChange({ sample, point: projectCameraGaze(sample, environment), environment });
  };
  const poll = async () => {
    if (stopped || inFlight || doc.hidden) return;
    inFlight = true;
    const requestEpoch = epoch;
    lastRequest = now();
    try {
      const response = await fetcher('/api/gaze', { cache: 'no-store', signal: AbortSignal.timeout(450) });
      if (!response.ok) throw new Error('Camera bridge unavailable');
      const next = await response.json();
      if (stopped || requestEpoch !== epoch) return;
      sample = next;
      receivedAt = now();
    } catch { if (!stopped && requestEpoch === epoch) { sample = null; receivedAt = -Infinity; } }
    finally { inFlight = false; publish(); }
  };
  const invalidate = () => { epoch++; sample = null; receivedAt = -Infinity; publish(); };
  // Capture listeners also receive blur/focus from descendant buttons. Losing
  // a button's focus (including the fullscreen button) is not leaving the page.
  const blur = event => { if (event.target === win) { focused = false; invalidate(); } };
  const focus = event => { if (event.target === win) { focused = true; publish(); } };
  const bindings = [
    [win, 'blur', blur], [win, 'focus', focus], [win, 'pagehide', invalidate],
    [doc, 'visibilitychange', invalidate], [doc, 'fullscreenchange', invalidate],
    [win, 'resize', invalidate],
  ];
  for (const [surface, name, handler] of bindings) surface.addEventListener(name, handler, true);
  const interval = win.setInterval(() => {
    publish(); // Re-check DOM targets and expire samples even if a fetch stalls.
    if (now() - lastRequest >= 80) void poll();
  }, 40);
  publish();
  void poll();
  return () => {
    stopped = true;
    win.clearInterval(interval);
    for (const [surface, name, handler] of bindings) surface.removeEventListener(name, handler, true);
  };
}
