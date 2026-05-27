/**
 * Tests for useRequest hook — refreshDeps auto-fetch on dependency changes.
 *
 * Regression: pagination in all pages was broken because useRequest only ran once
 * on mount and never re-fetched when page/pageSize changed. The fix adds a
 * refreshDeps option that triggers run() when watched values change.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useRequest } from '../../hooks/useRequest';

// Flush all pending microtasks
const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

describe('useRequest', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('basic behavior', () => {
    it('runs immediately by default and returns data', async () => {
      const mockFn = vi.fn().mockResolvedValue({ items: [1, 2], total: 2 });

      const { result } = renderHook(() => useRequest(mockFn));

      expect(result.current.loading).toBe(true);

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.data).toEqual({ items: [1, 2], total: 2 });
      expect(mockFn).toHaveBeenCalledTimes(1);
    });

    it('does NOT run when immediate=false', async () => {
      const mockFn = vi.fn();

      const { result } = renderHook(() =>
        useRequest(mockFn, { immediate: false })
      );

      // Give time for any async work
      await flush();

      expect(result.current.loading).toBe(false);
      expect(mockFn).not.toHaveBeenCalled();
    });

    it('exposes run() for manual invocation', async () => {
      const mockFn = vi.fn().mockResolvedValue({ ok: true });

      const { result } = renderHook(() =>
        useRequest(mockFn, { immediate: false })
      );

      expect(mockFn).not.toHaveBeenCalled();

      await act(async () => {
        await result.current.run();
      });

      expect(mockFn).toHaveBeenCalledTimes(1);
      expect(result.current.data).toEqual({ ok: true });
    });

    it('handles errors gracefully', async () => {
      const mockFn = vi.fn().mockRejectedValue(new Error('Network error'));

      const { result } = renderHook(() => useRequest(mockFn));

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.error).toBeInstanceOf(Error);
      expect(result.current.error?.message).toBe('Network error');
      expect(result.current.data).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // refreshDeps — THE REGRESSION FIX
  // -------------------------------------------------------------------------

  describe('refreshDeps', () => {
    it('re-fetches when a refreshDep changes', async () => {
      const mockFn = vi
        .fn()
        .mockResolvedValueOnce({ page: 1 })
        .mockResolvedValueOnce({ page: 2 });

      // Start with page=1
      const { result, rerender } = renderHook(
        ({ page }) => useRequest(mockFn, { refreshDeps: [page] }),
        { initialProps: { page: 1 } }
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });
      expect(result.current.data).toEqual({ page: 1 });
      expect(mockFn).toHaveBeenCalledTimes(1);

      // Change page → should trigger re-fetch
      rerender({ page: 2 });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });
      expect(result.current.data).toEqual({ page: 2 });
      expect(mockFn).toHaveBeenCalledTimes(2);
    });

    it('skips first render (no double-fetch on mount)', async () => {
      const mockFn = vi.fn().mockResolvedValue({ ok: true });

      // immediate=true + refreshDeps → only 1 call (mount only, not mount+dep-change)
      const { result } = renderHook(() =>
        useRequest(mockFn, { refreshDeps: [42] })
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // Only called once — the immediate run on mount, not a second refreshDeps run
      expect(mockFn).toHaveBeenCalledTimes(1);
    });

    it('re-fetches on each of two dep changes', async () => {
      const mockFn = vi
        .fn()
        .mockResolvedValueOnce({ p: 1 })
        .mockResolvedValueOnce({ p: 2 })
        .mockResolvedValueOnce({ p: 3 });

      const { result, rerender } = renderHook(
        ({ page }) => useRequest(mockFn, { refreshDeps: [page] }),
        { initialProps: { page: 1 } }
      );

      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(mockFn).toHaveBeenCalledTimes(1);

      // page: 1→2
      rerender({ page: 2 });
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(mockFn).toHaveBeenCalledTimes(2);

      // page: 2→3
      rerender({ page: 3 });
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(mockFn).toHaveBeenCalledTimes(3);
    });

    it('re-fetches when pageSize changes alongside page', async () => {
      const mockFn = vi
        .fn()
        .mockResolvedValueOnce({ count: 10 })
        .mockResolvedValueOnce({ count: 20 });

      const { result, rerender } = renderHook(
        ({ page, pageSize }) =>
          useRequest(mockFn, { refreshDeps: [page, pageSize] }),
        { initialProps: { page: 1, pageSize: 10 } }
      );

      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(mockFn).toHaveBeenCalledTimes(1);

      // Only pageSize changes
      rerender({ page: 1, pageSize: 20 });
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(mockFn).toHaveBeenCalledTimes(2);
    });

    it('does NOT re-fetch when a non-dep value changes', async () => {
      // Simulating the fixed pagination: search text is NOT in refreshDeps
      const mockFn = vi.fn().mockResolvedValue({ items: [] });

      const { result, rerender } = renderHook(
        ({ page, searchText }) =>
          useRequest(mockFn, { refreshDeps: [page] }),
        { initialProps: { page: 1, searchText: '' } }
      );

      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(mockFn).toHaveBeenCalledTimes(1);

      // searchText changes → NOT in refreshDeps → no re-fetch
      rerender({ page: 1, searchText: 'query' });
      await flush();
      expect(mockFn).toHaveBeenCalledTimes(1);

      // page changes → IN refreshDeps → re-fetch
      rerender({ page: 2, searchText: 'query' });
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(mockFn).toHaveBeenCalledTimes(2);
    });

    it('handles no refreshDeps gracefully', async () => {
      const mockFn = vi.fn().mockResolvedValue({ ok: true });

      const { result, rerender } = renderHook(
        ({ page }) => useRequest(mockFn),
        { initialProps: { page: 1 } }
      );

      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(mockFn).toHaveBeenCalledTimes(1);

      // Without refreshDeps, page change does NOT trigger re-fetch (old behavior)
      rerender({ page: 2 });
      await flush();
      expect(mockFn).toHaveBeenCalledTimes(1);
    });

    it('discards stale responses on rapid dep changes', async () => {
      // Simulate rapid page changes; only the latest page data should land
      let resolvePage2: (value: { p: number }) => void;
      const page2Promise = new Promise<{ p: number }>((res) => {
        resolvePage2 = res;
      });

      const mockFn = vi
        .fn()
        .mockResolvedValueOnce({ p: 1 })
        .mockReturnValueOnce(page2Promise)     // page=2 → slow
        .mockResolvedValueOnce({ p: 3 });       // page=3 → fast

      const { result, rerender } = renderHook(
        ({ page }) => useRequest(mockFn, { refreshDeps: [page] }),
        { initialProps: { page: 1 } }
      );

      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(mockFn).toHaveBeenCalledTimes(1);

      // Trigger page=2 (slow)
      rerender({ page: 2 });
      // Immediately trigger page=3 (fast)
      rerender({ page: 3 });

      await waitFor(() => expect(result.current.loading).toBe(false));

      // Resolve the stale page=2 response
      resolvePage2!({ p: 2 });
      await flush();

      // Should still have page=3 data (stale page=2 was discarded)
      expect(result.current.data).toEqual({ p: 3 });
    });
  });

  // -------------------------------------------------------------------------
  // reset
  // -------------------------------------------------------------------------

  describe('reset', () => {
    it('clears data, loading, and error', async () => {
      const mockFn = vi.fn().mockResolvedValue({ items: [1] });

      const { result } = renderHook(() => useRequest(mockFn));

      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(result.current.data).toEqual({ items: [1] });

      act(() => {
        result.current.reset();
      });

      expect(result.current.data).toBeNull();
      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBeNull();
    });
  });
});
