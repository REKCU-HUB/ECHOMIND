import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import test from 'node:test';
import vm from 'node:vm';

// Run the real bridge without React or a browser. Only transport and the browser
// scheduling surfaces are faked; tests control the order responses actually arrive.
const source = readFileSync(new URL('../web/src/eegBridge.js', import.meta.url), 'utf8')
  .replace(/^import .* from ['"]react['"];?\s*$/m, '')
  .replace(/\bexport\s+(?=const|function)/g, '');

const flush = () => new Promise(resolve => setImmediate(resolve));

function makeBridge() {
  const requests = [];
  const intervals = [];
  const documentListeners = new Map();
  const windowListeners = new Map();
  const context = vm.createContext({
    crypto: { randomUUID },
    AbortSignal: { timeout: () => ({}) },
    useSyncExternalStore: (_subscribe, getSnapshot) => getSnapshot(),
    document: { hidden: false, addEventListener: (name, fn) => documentListeners.set(name, fn) },
    window: { addEventListener: (name, fn) => windowListeners.set(name, fn) },
    setInterval: fn => { intervals.push(fn); return intervals.length; },
    fetch: (url, options) => new Promise((resolve, reject) => {
      requests.push({ url, event: JSON.parse(options.body), resolve, reject });
    }),
  });
  vm.runInContext(`${source}\n;globalThis.bridge = { eeg, useEEG };`, context);
  return {
    eeg: context.bridge.eeg,
    state: () => context.bridge.useEEG(),
    requests,
    poll: () => intervals.forEach(fn => fn()),
    async respond(index, next) {
      assert.ok(requests[index], `request ${index} must already exist`);
      requests[index].resolve({ ok: true, json: async () => next });
      await flush();
    },
    async fail(index) {
      assert.ok(requests[index], `request ${index} must already exist`);
      requests[index].reject(new Error('simulated response timeout'));
      await flush();
    },
  };
}

function snapshot(target = null, phase = target ? 'focusing' : 'idle', seq = 0) {
  return {
    attention: phase === 'confirmed' ? 90 : 32,
    phase, progress: phase === 'confirmed' ? 1 : 0,
    target, confirmed_id: phase === 'confirmed' ? target.id : null,
    confirmation_seq: seq, reset_seq: 0, ar_connected: true,
    config: { threshold: 75, dwell_ms: 1600, mode: 'assisted' },
  };
}

test('late confirmation from an old dwell cannot confirm a new dwell on the same button', async () => {
  const bridge = makeBridge();
  let oldActivations = 0;
  let newActivations = 0;
  bridge.eeg.focus(':r1:', 'Water', () => oldActivations++);
  const oldTarget = bridge.requests[0].event.target;
  await bridge.respond(0, snapshot(oldTarget));

  bridge.poll(); // Heartbeat response remains in flight while the pointer leaves/re-enters.
  bridge.eeg.leave(':r1:');
  bridge.eeg.focus(':r1:', 'Water', () => newActivations++);
  await bridge.respond(1, snapshot(oldTarget, 'confirmed', 1));
  assert.equal(oldActivations, 0);
  assert.equal(newActivations, 0);
  assert.equal(bridge.state().target, null);
  assert.equal(bridge.requests[2].event.type, 'leave');
  assert.equal(bridge.requests[2].event.target.id, oldTarget.id);

  await bridge.respond(2, snapshot());
  const newTarget = bridge.requests[3].event.target;
  assert.notEqual(newTarget.id, oldTarget.id);
  await bridge.respond(3, snapshot(newTarget));
  assert.equal(bridge.state().target.id, ':r1:'); // UI still gets its component-local ID.
  bridge.poll();
  await bridge.respond(4, snapshot(newTarget, 'confirmed', 2));
  assert.equal(newActivations, 1);
  assert.equal(oldActivations, 0);
});

test('a second page with the same React useId cannot inherit another client confirmation', async () => {
  const first = makeBridge();
  const second = makeBridge();
  let firstActivations = 0;
  let secondActivations = 0;
  first.eeg.focus(':r0:', 'Activate', () => firstActivations++);
  second.eeg.focus(':r0:', 'Activate', () => secondActivations++);
  const firstEvent = first.requests[0].event;
  const secondEvent = second.requests[0].event;
  assert.notEqual(firstEvent.client_id, secondEvent.client_id);
  assert.notEqual(firstEvent.target.id, secondEvent.target.id);
  await first.respond(0, snapshot(firstEvent.target, 'confirmed', 1));
  await second.respond(0, snapshot(firstEvent.target, 'confirmed', 1));
  assert.equal(firstActivations, 1);
  assert.equal(secondActivations, 0);
  assert.equal(second.state().target, null);
});

test('a failed write recovers with leave, retries cancellation, then resumes heartbeat', async () => {
  const bridge = makeBridge();
  let activations = 0;
  bridge.eeg.focus('water', 'Water', () => activations++);
  const target = bridge.requests[0].event.target;
  await bridge.fail(0);
  assert.equal(bridge.state().online, false);

  bridge.poll();
  assert.equal(bridge.requests[1].event.type, 'leave');
  assert.equal(bridge.requests[1].event.target.id, target.id);
  await bridge.fail(1);
  bridge.poll();
  assert.equal(bridge.requests[2].event.type, 'leave');
  assert.equal(bridge.requests[2].event.target.id, target.id);
  await bridge.respond(2, snapshot());
  bridge.poll();
  assert.equal(bridge.requests[3].event.type, 'heartbeat');
  await bridge.respond(3, snapshot());
  assert.equal(bridge.state().online, true);
  assert.equal(activations, 0);
});

test('continued hover confirms once, but an explicit click after confirmation starts a fresh round', async () => {
  const bridge = makeBridge();
  let activations = 0;
  const activate = () => activations++;
  bridge.eeg.focus('play', 'Play', activate);
  const firstTarget = bridge.requests[0].event.target;
  await bridge.respond(0, snapshot(firstTarget, 'confirmed', 1));
  assert.equal(activations, 1);

  bridge.eeg.focus('play', 'Pause', activate);
  assert.equal(bridge.requests[1].event.target.id, firstTarget.id);
  await bridge.respond(1, snapshot(firstTarget, 'confirmed', 1));
  assert.equal(activations, 1);

  bridge.eeg.focus('play', 'Pause', activate, 'click');
  const nextTarget = bridge.requests[2].event.target;
  assert.notEqual(nextTarget.id, firstTarget.id);
  assert.equal(bridge.requests[2].event.type, 'click');
  await bridge.respond(2, snapshot(nextTarget));
  assert.equal(activations, 1);
  bridge.poll();
  await bridge.respond(3, snapshot(nextTarget, 'confirmed', 2));
  assert.equal(activations, 2);
});

test('timeout cancels the target that may have reached the server, not a newer unsent target', async () => {
  const bridge = makeBridge();
  bridge.eeg.focus('water', 'Water', () => {});
  const sentTarget = bridge.requests[0].event.target;
  bridge.eeg.leave('water');
  bridge.eeg.focus('music', 'Music', () => {}); // Queued, never sent before timeout.
  assert.equal(bridge.requests.length, 1);
  await bridge.fail(0);
  bridge.poll();
  assert.equal(bridge.requests[1].event.type, 'leave');
  assert.equal(bridge.requests[1].event.target.id, sentTarget.id);
  await bridge.respond(1, snapshot());
});
