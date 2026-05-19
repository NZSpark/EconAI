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
    onSuccess?: (data: T) => void;
    onError?: (error: Error) => void;
  }
): UseRequestReturn<T> {
  const [state, setState] = useState<UseRequestState<T>>({
    data: null,
    loading: false,
    error: null,
  });

  const mountedRef = useRef(true);
  const requestFnRef = useRef(requestFn);
  requestFnRef.current = requestFn;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const run = useCallback(
    async (...args: unknown[]): Promise<T | null> => {
      setState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        const data = await requestFnRef.current(...args);
        if (mountedRef.current) {
          setState({ data, loading: false, error: null });
          options?.onSuccess?.(data);
        }
        return data;
      } catch (error) {
        if (mountedRef.current) {
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

  return {
    ...state,
    run,
    reset,
  };
}