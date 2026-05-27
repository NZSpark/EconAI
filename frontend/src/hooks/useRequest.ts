import { useState, useCallback, useEffect, useRef } from 'react';

interface UseRequestState<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
}

interface UseRequestReturn<T> extends UseRequestState<T> {
  run: (...args: unknown[]) => Promise<T | null>;
  reset: () => void;
}

export function useRequest<T>(
  requestFn: (...args: unknown[]) => Promise<T>,
  options?: {
    immediate?: boolean;
    refreshDeps?: unknown[];
    onSuccess?: (data: T) => void;
    onError?: (error: Error) => void;
  }
): UseRequestReturn<T> {
  const [state, setState] = useState<UseRequestState<T>>({
    data: null,
    loading: false,
    error: null,
  });

  const requestFnRef = useRef(requestFn);
  requestFnRef.current = requestFn;

  // Incrementing counter to discard stale responses
  const runIdRef = useRef(0);

  const run = useCallback(
    async (...args: unknown[]): Promise<T | null> => {
      const runId = ++runIdRef.current;
      setState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        const data = await requestFnRef.current(...args);
        // Only apply the result if this is still the latest invocation
        if (runId === runIdRef.current) {
          setState({ data, loading: false, error: null });
          options?.onSuccess?.(data);
        }
        return data;
      } catch (error) {
        if (runId === runIdRef.current) {
          setState((prev) => ({ ...prev, loading: false, error: error as Error }));
          options?.onError?.(error as Error);
        }
        return null;
      }
    },
    [options]
  );

  const reset = useCallback(() => {
    setState({ data: null, loading: false, error: null });
  }, []);

  // Immediate run on mount (defaults to true)
  useEffect(() => {
    if (options?.immediate !== false) {
      run();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-refresh when dependencies change (e.g. page/pageSize via pagination)
  const skipFirstRef = useRef(true);
  useEffect(() => {
    if (options?.refreshDeps) {
      if (skipFirstRef.current) {
        skipFirstRef.current = false;
        return;
      }
      run();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, options?.refreshDeps ?? []);

  return {
    ...state,
    run,
    reset,
  };
}