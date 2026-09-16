import { useSyncExternalStore } from 'react';

const initial = { online: false, attention: 32, phase: 'idle', progress: 0, target: null, confirmation_seq: 0, reset_seq: 0, config: { threshold: 75, dwell_ms: 1600, mode: 'assisted' } };
let state = initial;
let active = null;
let running = false;
let pending = [];
let focusEpoch = 0;
let lastSentTarget = null;
const listeners = new Set();
const client_id = crypto.randomUUID();

function publish(next) {
  const ours = active && next.target?.id === active.wireId;
  state = { ...next, online: true, target: ours ? { ...next.target, id: active.id } : null };
  for (const fn of listeners) fn();
  if (ours && !active.done && next.phase === 'confirmed' && next.confirmed_id === active.wireId) {
    active.done = true;
    active.confirm();
  }
}

async function pump() {
  if (running) return;
  running = true;
  try {
    do {
      const event = pending.shift() || { type: 'heartbeat' };
      if (event.type === 'hover' || event.type === 'click') lastSentTarget = event.target;
      const response = await fetch('/api/event', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...event, client_id }), signal: AbortSignal.timeout(1200),
      });
      if (!response.ok) throw new Error('Demo bridge unavailable');
      publish(await response.json());
    } while (pending.length);
  } catch {
    // A timed-out write may still have reached Python. Cancel that exact round
    // before sending more heartbeats, so an abandoned target cannot stay alive.
    pending = lastSentTarget ? [{ type: 'leave', target: lastSentTarget }] : [];
    active = null;
    state = { ...state, online: false, target: null, progress: 0, phase: 'idle' };
    for (const fn of listeners) fn();
  } finally { running = false; }
}

function send(event) { pending.push(event); void pump(); }

export const eeg = {
  focus(id, label, confirm, type = 'hover') {
    if (!active || active.id !== id || (type === 'click' && active.done)) active = { id, wireId: `${client_id}:${id}:${++focusEpoch}`, label, confirm, done: false };
    else active.confirm = confirm;
    send({ type, target: { id: active.wireId, label } });
  },
  leave(id) {
    if (!active || (id && active.id !== id)) return;
    const previous = active;
    active = null;
    send({ type: 'leave', target: { id: previous.wireId, label: previous.label } });
  },
  reset() { active = null; send({ type: 'reset' }); },
};

setInterval(() => { if (!running && !document.hidden) void pump(); }, 100);
window.addEventListener('blur', () => eeg.leave());
document.addEventListener('visibilitychange', () => { if (document.hidden) eeg.leave(); });
window.addEventListener('keydown', event => { if (['Escape', 'ArrowLeft', 'ArrowRight', 'c', 'f'].includes(event.key)) eeg.leave(); });
export function useEEG() {
  return useSyncExternalStore(fn => { listeners.add(fn); return () => listeners.delete(fn); }, () => state);
}
