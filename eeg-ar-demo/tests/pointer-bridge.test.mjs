import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import test from 'node:test';
import { startPointerBridge } from '../web/src/pointerBridge.js';

const flush = () => new Promise(resolve => setImmediate(resolve));
function surface() {
  const listeners = new Map();
  return {
    listeners,
    addEventListener(name, fn, capture) { assert.equal(capture, true); if (!listeners.has(name)) listeners.set(name, new Set()); listeners.get(name).add(fn); },
    removeEventListener(name, fn) { listeners.get(name)?.delete(fn); },
    fire(name, event = {}) { for (const fn of listeners.get(name) || []) fn({ target: this, ...event }); },
  };
}
function makeBridge() {
  let clock = 0, state;
  const requests = [], intervals = new Set();
  const doc = { ...surface(), hidden: false, documentElement: {} };
  const win = {
    ...surface(), crypto: { randomUUID }, innerWidth: 1000, innerHeight: 800,
    performance: { now: () => clock },
    setInterval(fn, ms) { assert.equal(ms, 40); intervals.add(fn); return fn; },
    clearInterval(fn) { intervals.delete(fn); },
  };
  const fetcher = (url, options) => new Promise((resolve, reject) => requests.push({ url, options, body: JSON.parse(options.body), resolve, reject }));
  const stop = startPointerBridge(next => { state = next; }, win, doc, fetcher);
  return {
    doc, win, stop, requests, state: () => state,
    tick(ms = 40) { clock += ms; for (const fn of intervals) fn(); },
    async respond(index, consumer_connected = true) { requests[index].resolve({ ok: true, json: async () => ({ consumer_connected }) }); await flush(); },
    async fail(index) { requests[index].reject(new Error('offline')); await flush(); },
  };
}

test('tracks exact viewport pixels, coalesces movement, and sends stationary heartbeats', async () => {
  const bridge = makeBridge();
  assert.equal(bridge.requests[0].body.active, false);
  assert.equal(bridge.state().consumer_connected, false);
  await bridge.respond(0);
  bridge.doc.fire('pointermove', { clientX: 240, clientY: 160 });
  bridge.doc.fire('pointermove', { clientX: 750, clientY: 640 });
  assert.deepEqual(bridge.state(), { x: 750, y: 640, active: true, consumer_connected: true });
  assert.equal(bridge.requests.length, 1);
  bridge.tick();
  assert.equal(bridge.requests[1].body.x, .75);
  assert.equal(bridge.requests[1].body.y, .8);
  assert.deepEqual(bridge.requests[1].body.viewport, { width: 1000, height: 800 });
  await bridge.respond(1);
  bridge.tick(480);
  assert.equal(bridge.requests.length, 2);
  bridge.tick(40);
  assert.equal(bridge.requests.length, 3);
  assert.equal(bridge.requests[2].body.active, true);
  assert.ok(bridge.requests.every(request => request.url === '/api/pointer'));
  bridge.stop();
});

test('leaving sends a newer inactive update immediately, even with a request in flight', async () => {
  const bridge = makeBridge();
  await bridge.respond(0);
  bridge.doc.fire('pointermove', { clientX: 100, clientY: 200 });
  bridge.tick(); // Keep this active update in flight.
  bridge.win.fire('blur');
  assert.equal(bridge.state().active, false);
  assert.equal(bridge.requests[2].body.active, false);
  assert.equal(bridge.requests[2].options.keepalive, true);
  assert.ok(bridge.requests[2].body.seq > bridge.requests[1].body.seq);
  await bridge.respond(1);
  assert.equal(bridge.state().active, false); // Late active response cannot reactivate cursor.
  bridge.doc.fire('pointermove', { clientX: 200, clientY: 300 });
  bridge.tick();
  assert.equal(bridge.requests[3].body.active, true);
  assert.ok(bridge.requests[3].body.seq > bridge.requests[2].body.seq);
  bridge.stop();
});

test('hidden pages go inactive, stop heartbeats, and discard the connected indicator', async () => {
  const bridge = makeBridge();
  await bridge.respond(0);
  bridge.doc.fire('pointermove', { clientX: 200, clientY: 300 });
  bridge.doc.hidden = true;
  bridge.doc.fire('visibilitychange');
  assert.equal(bridge.requests[1].body.active, false);
  await bridge.respond(1);
  bridge.tick(1100);
  assert.equal(bridge.requests.length, 2);
  assert.equal(bridge.state().consumer_connected, false);
  assert.equal(bridge.state().active, false);
  bridge.stop();
});

test('transport failure hides the cursor without dispatching app actions, then recovers', async () => {
  const bridge = makeBridge();
  await bridge.respond(0);
  bridge.doc.fire('pointermove', { clientX: 999, clientY: 799 });
  bridge.tick();
  await bridge.fail(1);
  assert.equal(bridge.state().consumer_connected, false);
  bridge.tick(500);
  await bridge.respond(2);
  assert.equal(bridge.state().consumer_connected, true);
  bridge.doc.fire('mouseleave', { target: bridge.doc.documentElement });
  assert.equal(bridge.state().active, false);
  bridge.stop();
  const count = bridge.requests.length;
  bridge.doc.fire('pointermove', { clientX: 1, clientY: 1 });
  bridge.tick(500);
  assert.equal(bridge.requests.length, count);
});
