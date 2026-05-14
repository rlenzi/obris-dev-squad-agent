import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useUptime } from './useUptime';

// Mock global fetch
const mockFetch = vi.fn();

beforeEach(() => {
  vi.stubGlobal('fetch', mockFetch);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.clearAllTimers();
});

describe('useUptime', () => {
  it('returns null and error=false before first fetch resolves', () => {
    // fetch never resolves during this test
    mockFetch.mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useUptime());

    expect(result.current.uptimeSeconds).toBeNull();
    expect(result.current.error).toBe(false);
  });

  it('returns uptime_seconds from endpoint after successful fetch', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ uptime_seconds: 8123 }),
    });

    const { result } = renderHook(() => useUptime());

    await waitFor(
      () => {
        expect(result.current.uptimeSeconds).toBe(8123);
      },
      { timeout: 10_000 },
    );
    expect(result.current.error).toBe(false);
  });

  it('sets error=true when fetch returns non-200', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 503 });

    const { result } = renderHook(() => useUptime());

    await waitFor(
      () => {
        expect(result.current.error).toBe(true);
      },
      { timeout: 10_000 },
    );
    expect(result.current.uptimeSeconds).toBeNull();
  });

  it('sets error=true when fetch throws (network error)', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network error'));

    const { result } = renderHook(() => useUptime());

    await waitFor(
      () => {
        expect(result.current.error).toBe(true);
      },
      { timeout: 10_000 },
    );
  });

  it('polls again after 30 seconds', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ uptime_seconds: 100 }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ uptime_seconds: 130 }),
      });

    const { result } = renderHook(() => useUptime());

    // Drain microtasks to let first fetch resolve
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    await waitFor(
      () => {
        expect(result.current.uptimeSeconds).toBe(100);
      },
      { timeout: 10_000 },
    );

    // Advance 30 seconds to trigger next poll, then drain microtasks
    await act(async () => {
      vi.advanceTimersByTime(30_000);
      await Promise.resolve();
      await Promise.resolve();
    });

    await waitFor(
      () => {
        expect(result.current.uptimeSeconds).toBe(130);
      },
      { timeout: 10_000 },
    );

    vi.useRealTimers();
  });

  it('cleans up interval on unmount', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ uptime_seconds: 50 }),
    });

    const { result, unmount } = renderHook(() => useUptime());

    await waitFor(
      () => {
        expect(result.current.uptimeSeconds).toBe(50);
      },
      { timeout: 10_000 },
    );

    const callCountBefore = mockFetch.mock.calls.length;
    unmount();

    // After unmount, no more calls should happen
    await new Promise((r) => setTimeout(r, 100));
    expect(mockFetch.mock.calls.length).toBe(callCountBefore);
  });
});
