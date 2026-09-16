import { useSyncExternalStore } from 'react';
import { eeg } from './eegBridge';
import { createInputArbiter } from './gazeInputCore';

const initialMode = new URLSearchParams(window.location.search).get('input') === 'camera' ? 'camera' : 'mouse';
export const input = createInputArbiter(eeg, initialMode);
export function useInputMode() {
  return useSyncExternalStore(input.subscribe, input.mode);
}
