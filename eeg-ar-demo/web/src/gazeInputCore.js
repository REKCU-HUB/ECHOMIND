// Coordinates stay screen-normalized until the page is truly fullscreen. A
// browser window is not a calibration surface and must never stretch the gaze.
export function projectCameraGaze(sample, environment) {
  const { fullscreen, visible, focused, width, height, now, receivedAt } = environment;
  if (!fullscreen || !visible || !focused || !(width > 0 && height > 0)) return null;
  if (!sample || sample.source !== 'camera' || sample.simulated !== false ||
      sample.connected !== true || sample.enabled !== true || sample.active !== true ||
      sample.calibrated !== true) return null;
  if (![sample.x, sample.y, sample.quality, sample.age_ms, now, receivedAt].every(Number.isFinite)) return null;
  if (sample.x < 0 || sample.x > 1 || sample.y < 0 || sample.y > 1 ||
      sample.quality < .5 || sample.age_ms < 0 || now < receivedAt ||
      sample.age_ms + now - receivedAt >= 350) return null;
  return { x: sample.x * (width - 1), y: sample.y * (height - 1) };
}

export function cameraTargetAt(doc, point) {
  if (!point) return null;
  // Only explicitly registered dwell controls can receive gaze. Settings,
  // upload/export controls and ordinary buttons are deliberately excluded.
  const element = doc.elementFromPoint(point.x, point.y)?.closest('[data-eeg-target]');
  if (!element || element.disabled || element.getAttribute('aria-disabled') === 'true') return null;
  return element.getAttribute('data-eeg-target');
}

export function createInputArbiter(bridge, initialMode = 'mouse') {
  let mode = initialMode === 'camera' ? 'camera' : 'mouse';
  let cameraTarget = null, lastFocusAt = -Infinity;
  const targets = new Map(), listeners = new Set();
  const clear = () => { cameraTarget = null; lastFocusAt = -Infinity; bridge.leave(); };
  return {
    mode: () => mode,
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    setMode(next) {
      if (!['mouse', 'camera'].includes(next) || next === mode) return;
      clear();
      mode = next;
      for (const fn of listeners) fn();
    },
    register(id, target) {
      targets.set(id, target);
      return () => {
        if (targets.get(id) !== target) return;
        targets.delete(id);
        if (cameraTarget === id) clear();
        else bridge.leave(id);
      };
    },
    mouseFocus(id, type = 'hover') {
      if (mode !== 'mouse') return;
      const target = targets.get(id);
      if (target && !target.disabled()) bridge.focus(id, target.label, target.confirm, type);
    },
    mouseLeave(id) { if (mode === 'mouse') bridge.leave(id); },
    cameraAt(id, now) {
      if (mode !== 'camera') return;
      const target = targets.get(id);
      if (!target || target.disabled()) { if (cameraTarget !== null) clear(); return; }
      if (cameraTarget !== id) { clear(); cameraTarget = id; }
      // Refresh the same focus after a bridge reconnect. eeg.focus owns its
      // confirmation epoch, so this cannot directly invoke a page action.
      if (now - lastFocusAt >= 300) {
        bridge.focus(id, target.label, target.confirm, 'hover');
        lastFocusAt = now;
      }
    },
    suspend: clear,
  };
}
