// A separate, simulated pointer feed. This never dispatches an EEG event or click.
export function startPointerBridge(onChange, win = window, doc = document, fetcher = fetch) {
  const client_id = win.crypto.randomUUID();
  let seq = 0, x = 0, y = 0, active = false, dirty = true;
  let inFlight = false, stopped = false, connected = false, lastConsumerAt = 0;
  let lastSent = -Infinity;
  const now = () => win.performance.now();
  const publish = () => onChange({ x, y, active, consumer_connected: connected });
  const payload = () => ({
    client_id, seq: ++seq, active,
    x: Math.max(0, Math.min(1, x / Math.max(1, win.innerWidth))),
    y: Math.max(0, Math.min(1, y / Math.max(1, win.innerHeight))),
    viewport: { width: Math.max(1, win.innerWidth), height: Math.max(1, win.innerHeight) },
  });

  async function send(urgent = false) {
    if (stopped || (!urgent && inFlight)) return;
    if (!urgent) inFlight = true;
    dirty = false;
    lastSent = now();
    try {
      const response = await fetcher('/api/pointer', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload()), keepalive: urgent,
        signal: AbortSignal.timeout(900),
      });
      if (!response.ok) throw new Error('Pointer bridge unavailable');
      const next = await response.json();
      if (stopped) return;
      connected = next.consumer_connected === true;
      if (connected) lastConsumerAt = now();
      publish();
    } catch {
      if (!stopped) { connected = false; publish(); }
    } finally { if (!urgent) inFlight = false; }
  }

  const move = event => {
    if (doc.hidden || !Number.isFinite(event.clientX) || !Number.isFinite(event.clientY)) return;
    x = Math.max(0, Math.min(win.innerWidth, event.clientX));
    y = Math.max(0, Math.min(win.innerHeight, event.clientY));
    active = true;
    dirty = true;
    publish(); // Local ring follows the actual pixel position without network lag.
  };
  const leave = () => { active = false; dirty = true; publish(); void send(true); };
  const boundaryLeave = event => {
    if (event.target === doc || event.target === doc.documentElement) leave();
  };
  const enter = event => { if (event.relatedTarget == null) move(event); };
  const visibility = () => { if (doc.hidden) leave(); };
  const resize = () => { x = Math.min(x, win.innerWidth); y = Math.min(y, win.innerHeight); dirty = true; publish(); };
  const bindings = [
    [doc, 'pointermove', move], [doc, 'pointerover', enter],
    [doc, 'pointerleave', boundaryLeave], [doc, 'mouseleave', boundaryLeave],
    [doc, 'visibilitychange', visibility], [win, 'blur', leave],
    [win, 'pagehide', leave], [win, 'resize', resize],
  ];
  for (const [surface, name, handler] of bindings) surface.addEventListener(name, handler, true);
  const interval = win.setInterval(() => {
    if (connected && now() - lastConsumerAt >= 1000) { connected = false; publish(); }
    if (!doc.hidden && (dirty || now() - lastSent >= 500)) void send();
  }, 40);
  publish();
  void send();
  return () => {
    leave();
    stopped = true;
    win.clearInterval(interval);
    for (const [surface, name, handler] of bindings) surface.removeEventListener(name, handler, true);
  };
}
