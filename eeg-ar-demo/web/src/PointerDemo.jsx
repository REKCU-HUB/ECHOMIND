import { useEffect, useState } from 'react';
import { startPointerBridge } from './pointerBridge';
import { useInputMode } from './gazeInput';

export function PointerDemo() {
  const mode = useInputMode();
  const [pointer, setPointer] = useState({ active: false, consumer_connected: false });
  useEffect(() => {
    setPointer({ active: false, consumer_connected: false });
    if (mode === 'mouse') return startPointerBridge(setPointer);
  }, [mode]);
  if (mode !== 'mouse' || !pointer.active || !pointer.consumer_connected) return null;
  return <div className="eye-pointer-demo" aria-hidden="true" data-testid="mouse-linked-gaze">
    <span className="eye-pointer-ring" style={{ left: pointer.x, top: pointer.y }}><i /></span>
    <span className="eye-pointer-label">MOUSE-LINKED DEMO</span>
  </div>;
}
