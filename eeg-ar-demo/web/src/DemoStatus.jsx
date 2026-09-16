import { eeg, useEEG } from './eegBridge';
import { useInputMode } from './gazeInput';
import { useEffect, useRef, useState } from 'react';

const STORAGE_KEY = 'echomind.eeg-panel.v1';
const MARGIN = 12;

function fitPanel(value = {}) {
  const number = (key, fallback) => Number.isFinite(value[key]) ? value[key] : fallback;
  const maxWidth = Math.max(160, window.innerWidth - MARGIN * 2);
  const maxHeight = Math.max(150, window.innerHeight - MARGIN * 2);
  const width = Math.min(maxWidth, Math.max(Math.min(280, maxWidth), number('width', 340)));
  const height = Math.min(maxHeight, Math.max(Math.min(218, maxHeight), number('height', 238)));
  return {
    width, height,
    x: Math.max(MARGIN, Math.min(window.innerWidth - width - MARGIN, number('x', window.innerWidth - width - 24))),
    y: Math.max(MARGIN, Math.min(window.innerHeight - height - MARGIN, number('y', window.innerHeight - height - 24))),
    hidden: value.hidden === true,
  };
}

function savedPanel() {
  try { return fitPanel(JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}); }
  catch { return fitPanel(); }
}

export function DemoStatus() {
  const inputMode = useInputMode();
  const state = useEEG();
  const [panel, setPanel] = useState(savedPanel);
  const gesture = useRef(null);
  const reopenButton = useRef(null);
  const moveHandle = useRef(null);
  const restoreFocus = useRef(false);
  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(panel)); } catch { /* Storage may be unavailable. */ }
  }, [panel]);
  useEffect(() => {
    const resize = () => setPanel(current => fitPanel(current));
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, []);
  useEffect(() => {
    if (restoreFocus.current) {
      (panel.hidden ? reopenButton : moveHandle).current?.focus({ preventScroll: true });
      restoreFocus.current = false;
    }
  }, [panel.hidden]);

  const begin = (event, mode) => {
    if (event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    gesture.current = { mode, pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, panel };
  };
  const move = event => {
    const drag = gesture.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const dx = event.clientX - drag.startX, dy = event.clientY - drag.startY;
    setPanel(fitPanel(drag.mode === 'move'
      ? { ...drag.panel, x: drag.panel.x + dx, y: drag.panel.y + dy }
      : { ...drag.panel, width: Math.min(window.innerWidth - drag.panel.x - MARGIN, drag.panel.width + dx), height: Math.min(window.innerHeight - drag.panel.y - MARGIN, drag.panel.height + dy) }));
  };
  const end = event => {
    if (gesture.current?.pointerId !== event.pointerId) return;
    gesture.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  const keyboard = (event, mode) => {
    const directions = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
    if (!directions[event.key]) return;
    event.preventDefault();
    event.stopPropagation();
    const [dx, dy] = directions[event.key].map(n => n * (event.shiftKey ? 40 : 10));
    setPanel(current => fitPanel(mode === 'move' ? { ...current, x: current.x + dx, y: current.y + dy }
      : { ...current, width: Math.min(window.innerWidth - current.x - MARGIN, current.width + dx), height: Math.min(window.innerHeight - current.y - MARGIN, current.height + dy) }));
  };
  const toggle = hidden => {
    restoreFocus.current = true;
    setPanel(current => ({ ...current, hidden }));
  };
  const handles = mode => ({ onPointerDown: event => begin(event, mode), onPointerMove: move, onPointerUp: end, onPointerCancel: end, onLostPointerCapture: () => { gesture.current = null; }, onKeyDown: event => keyboard(event, mode) });
  const phase = !state.online ? 'Connecting to EEG monitor…' : state.phase === 'confirmed' ? 'Intent confirmed' : state.config.mode === 'distracted' ? 'Low attention · confirmation held' : state.target ? 'Building focus' : 'Move to a card to begin';
  if (panel.hidden) return <button ref={reopenButton} className="eeg-demo-reopen" type="button" aria-label="Show attention panel" title="Show attention panel" onClick={() => toggle(false)} onPointerDown={event => event.stopPropagation()}>EEG <span aria-hidden="true">↗</span></button>;
  return <aside className="eeg-demo-strip" aria-label="Virtual EEG demo status" data-testid="eeg-demo-status"
    style={{ left: panel.x, top: panel.y, width: panel.width, height: panel.height }}
    onPointerDown={event => event.stopPropagation()} onPointerMove={event => event.stopPropagation()}
    onKeyDown={event => event.stopPropagation()} onContextMenu={event => { event.preventDefault(); event.stopPropagation(); }}>
    <header className="eeg-demo-toolbar">
      <button ref={moveHandle} type="button" className="eeg-demo-drag" aria-label="Move attention panel" title="Drag to move · arrow keys to adjust" {...handles('move')}><span aria-hidden="true">⠿</span> EEG <small>DEMO</small></button>
      <button className="eeg-demo-hide" type="button" onClick={() => toggle(true)} aria-label="Hide attention panel" title="Hide attention panel">−</button>
    </header>
    <div className="eeg-demo-body">
      <div className="eeg-demo-meter"><span>Attention <b data-testid="eeg-attention">{Math.round(state.attention)}</b><small>/ 100</small></span><div className="eeg-meter-track"><i style={{ width: `${state.attention}%` }}/><em style={{ left: `${state.config.threshold}%` }} /></div></div>
      <div className="eeg-demo-copy"><strong data-testid="eeg-phase">{phase}</strong><small>{state.target?.label || `Hold ${ (state.config.dwell_ms / 1000).toFixed(1) }s · threshold ${state.config.threshold}`}</small></div>
      <footer><small>{inputMode === 'camera' ? 'Camera gaze' : 'Mouse gaze'} + virtual EEG</small><button type="button" onClick={() => eeg.reset()} aria-label="Reset demo">Reset</button></footer>
    </div>
    <button type="button" className="eeg-demo-resize" aria-label="Resize attention panel" title="Drag to resize · arrow keys to adjust" {...handles('resize')}><span aria-hidden="true">◢</span></button>
  </aside>;
}
