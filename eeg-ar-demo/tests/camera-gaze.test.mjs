import assert from 'node:assert/strict';
import test from 'node:test';
import { cameraTargetAt, createInputArbiter, projectCameraGaze } from '../web/src/gazeInputCore.js';
import { startCameraGazeBridge } from '../web/src/cameraGazeBridge.js';

const sample = {
  source: 'camera', simulated: false, connected: true, enabled: true, active: true,
  calibrated: true, x: .25, y: .75, quality: .8, eyes: 2, age_ms: 50,
};
const environment = { fullscreen: true, visible: true, focused: true, width: 1001, height: 801, now: 1000, receivedAt: 1000 };
test('maps real calibrated gaze to fullscreen pixels, including screen edges', () => {
  assert.deepEqual(projectCameraGaze(sample, environment), { x: 250, y: 600 });
  assert.deepEqual(projectCameraGaze({ ...sample, x: 1, y: 0 }, environment), { x: 1000, y: 0 });
  for (const flag of ['fullscreen', 'visible', 'focused']) {
    assert.equal(projectCameraGaze(sample, { ...environment, [flag]: false }), null);
  }
});
test('never accepts simulated, uncalibrated, disabled, lost or invalid gaze', () => {
  for (const patch of [
    { source: 'mouse' }, { simulated: true }, { active: false }, { enabled: false },
    { calibrated: false }, { connected: false }, { quality: .49 }, { x: NaN },
    { x: 1.01 }, { y: -.01 }, { age_ms: null }, { age_ms: -1 },
  ]) assert.equal(projectCameraGaze({ ...sample, ...patch }, environment), null, JSON.stringify(patch));
});
test('expires at 350 ms total age even when browser transport has not failed yet', () => {
  assert.notEqual(projectCameraGaze(sample, { ...environment, now: 1299 }), null);
  assert.equal(projectCameraGaze(sample, { ...environment, now: 1300 }), null);
  assert.equal(projectCameraGaze({ ...sample, age_ms: 350 }, environment), null);
  assert.equal(projectCameraGaze(sample, { ...environment, now: 999 }), null);
});
test('hit test allows only explicit dwell targets and honors disabled controls', () => {
  const element = { disabled: false, getAttribute: name => name === 'data-eeg-target' ? 'water' : null };
  let called;
  const doc = { elementFromPoint(x, y) {
    called = [x, y];
    return { closest(selector) { assert.equal(selector, '[data-eeg-target]'); return element; } };
  } };
  assert.equal(cameraTargetAt(doc, { x: 500, y: 300 }), 'water');
  assert.deepEqual(called, [500, 300]);
  element.disabled = true;
  assert.equal(cameraTargetAt(doc, { x: 500, y: 300 }), null);
  assert.equal(cameraTargetAt({ elementFromPoint: () => ({ closest: () => null }) }, { x: 1, y: 1 }), null);
  assert.equal(cameraTargetAt(doc, null), null);
});
function controller(mode = 'camera') {
  const events = [];
  const input = createInputArbiter({
    focus: (...args) => events.push(['focus', ...args]), leave: (...args) => events.push(['leave', ...args]),
  }, mode);
  return { input, events };
}
test('camera focus reaches only registered controls and never calls the page directly', () => {
  const { input, events } = controller();
  let activations = 0;
  input.register('water', { label: 'Water', disabled: () => false, confirm: () => activations++ });
  input.cameraAt('upload', 0);
  assert.equal(events.length, 0);
  input.cameraAt('water', 0);
  input.cameraAt('water', 40);
  assert.equal(events.filter(event => event[0] === 'focus').length, 1);
  assert.equal(activations, 0);
  const focus = events.find(event => event[0] === 'focus');
  assert.deepEqual(focus.slice(1, 3), ['water', 'Water']);
  assert.equal(focus[4], 'hover');
  focus[3](); // This is invoked only by the EEG bridge's confirmed response.
  assert.equal(activations, 1);
});
test('switching sources cancels dwell and makes mouse and gaze mutually exclusive', () => {
  const { input, events } = controller('mouse');
  input.register('water', { label: 'Water', disabled: () => false, confirm() {} });
  input.cameraAt('water', 0);
  assert.equal(events.length, 0);
  input.mouseFocus('water', 'click');
  assert.equal(events.at(-1)[4], 'click');
  input.setMode('camera');
  assert.equal(events.at(-1)[0], 'leave');
  const length = events.length;
  input.mouseFocus('water');
  input.mouseLeave('water');
  assert.equal(events.length, length);
  input.cameraAt('water', 100);
  assert.equal(events.at(-1)[4], 'hover');
  input.setMode('mouse');
  assert.equal(events.at(-1)[0], 'leave');
});
test('loss, disabled state and unmount immediately cancel the current camera dwell', () => {
  const { input, events } = controller();
  let disabled = false;
  const remove = input.register('water', { label: 'Water', disabled: () => disabled, confirm() {} });
  input.cameraAt('water', 0);
  input.cameraAt(null, 40);
  assert.equal(events.at(-1)[0], 'leave');
  input.cameraAt('water', 80);
  disabled = true;
  input.cameraAt('water', 120);
  assert.equal(events.at(-1)[0], 'leave');
  disabled = false;
  input.cameraAt('water', 160);
  remove();
  assert.equal(events.at(-1)[0], 'leave');
});
test('re-hit-testing a static gaze switches to newly rendered controls', () => {
  const { input, events } = controller();
  for (const id of ['activate', 'water']) input.register(id, { label: id, disabled: () => false, confirm() {} });
  input.cameraAt('activate', 0);
  input.cameraAt('water', 40);
  assert.deepEqual(events.map(event => [event[0], event[1]]), [
    ['leave', undefined], ['focus', 'activate'], ['leave', undefined], ['focus', 'water'],
  ]);
});

const flush = () => new Promise(resolve => setImmediate(resolve));
function surface() {
  const listeners = new Map();
  return {
    addEventListener(name, fn) { if (!listeners.has(name)) listeners.set(name, new Set()); listeners.get(name).add(fn); },
    removeEventListener(name, fn) { listeners.get(name)?.delete(fn); },
    fire(name, event = {}) { for (const fn of listeners.get(name) || []) fn({ target: this, ...event }); },
  };
}
function bridge() {
  let clock = 0, state;
  const requests = [], intervals = new Set();
  const doc = { ...surface(), hidden: false, fullscreenElement: {}, hasFocus: () => true };
  const win = {
    ...surface(), innerWidth: 1001, innerHeight: 801, performance: { now: () => clock },
    setInterval(fn) { intervals.add(fn); return fn; }, clearInterval(fn) { intervals.delete(fn); },
  };
  const fetcher = (url, options) => new Promise((resolve, reject) => requests.push({ url, options, resolve, reject }));
  const stop = startCameraGazeBridge(next => { state = next; }, win, doc, fetcher);
  return {
    win, doc, requests, stop, state: () => state,
    tick(ms = 40) { clock += ms; for (const fn of intervals) fn(); },
    async respond(index, next = sample) { requests[index].resolve({ ok: true, json: async () => next }); await flush(); },
  };
}
test('camera bridge polls only local numeric gaze and expires a stalled response', async () => {
  const stream = bridge();
  assert.equal(stream.requests[0].url, '/api/gaze');
  assert.equal(stream.requests[0].options.cache, 'no-store');
  await stream.respond(0);
  assert.deepEqual(stream.state().point, { x: 250, y: 600 });
  stream.tick(80); // Next fetch stays pending.
  stream.tick(220);
  assert.equal(stream.state().point, null);
  stream.stop();
});
test('blur cannot be undone by a late fetch; fullscreen exit and hiding invalidate the sample', async () => {
  const stream = bridge();
  stream.win.fire('blur');
  await stream.respond(0);
  assert.equal(stream.state().point, null);
  stream.win.fire('focus');
  assert.equal(stream.state().point, null); // Pre-blur response was discarded.
  stream.tick(80);
  await stream.respond(1);
  assert.notEqual(stream.state().point, null);
  stream.doc.fullscreenElement = null;
  stream.doc.fire('fullscreenchange');
  assert.equal(stream.state().point, null);
  stream.doc.fullscreenElement = {};
  stream.doc.fire('fullscreenchange');
  assert.equal(stream.state().point, null); // Requires a fresh API response.
  stream.tick(80);
  await stream.respond(2);
  assert.notEqual(stream.state().point, null);
  stream.doc.hidden = true;
  stream.doc.fire('visibilitychange');
  assert.equal(stream.state().point, null);
  stream.stop();
});
test('rapid fullscreen exit and re-entry cannot revive a pre-exit fetch', async () => {
  const stream = bridge();
  stream.doc.fullscreenElement = null;
  stream.doc.fire('fullscreenchange');
  stream.doc.fullscreenElement = {};
  stream.doc.fire('fullscreenchange');
  await stream.respond(0);
  assert.equal(stream.state().point, null);
  stream.tick(80);
  await stream.respond(1);
  assert.notEqual(stream.state().point, null);
  stream.stop();
});
test('fullscreen button blur does not impersonate browser-window blur', async () => {
  const stream = bridge();
  await stream.respond(0);
  stream.win.fire('blur', { target: { tagName: 'BUTTON' } });
  assert.notEqual(stream.state().point, null);
  assert.equal(stream.state().environment.focused, true);
  stream.doc.fire('fullscreenchange');
  assert.equal(stream.state().point, null);
  stream.win.fire('blur', { target: { tagName: 'BUTTON' } });
  stream.tick(80);
  await stream.respond(1);
  assert.notEqual(stream.state().point, null);
  assert.equal(stream.state().environment.focused, true);
  stream.win.fire('blur');
  stream.win.fire('focus', { target: { tagName: 'BUTTON' } });
  assert.equal(stream.state().point, null);
  assert.equal(stream.state().environment.focused, false);
  stream.stop();
});
