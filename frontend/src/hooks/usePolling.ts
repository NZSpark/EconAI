import { useEffect, useRef, useCallback } from 'react';

export function usePolling(
  callback: () => Promise<void>,
  intervalMs: number,
  enabled: boolean
) {
  const savedCallback = useRef(callback);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Update saved callback when it changes
  useEffect(() => {
    savedCallback.current = callback;
  }, [callback]);

  const clear = useCallback(() => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      clear();
      return;
    }

    // Run immediately when enabled
    savedCallback.current();

    intervalRef.current = setInterval(() => {
      savedCallback.current();
    }, intervalMs);

    return clear;
  }, [enabled, intervalMs, clear]);
}