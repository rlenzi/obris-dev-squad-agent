import { useEffect, useState } from 'react';
import { API_BASE_URL } from '@/lib/api';

const UPTIME_ENDPOINT = `${API_BASE_URL}/api/v1/health/uptime`;
const POLL_INTERVAL_MS = 30_000;
const FETCH_TIMEOUT_MS = 5_000;

export interface UptimeState {
  uptimeSeconds: number | null;
  error: boolean;
}

async function fetchUptime(): Promise<number> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const response = await fetch(UPTIME_ENDPOINT, { signal: controller.signal });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = (await response.json()) as { uptime_seconds: number };
    return data.uptime_seconds;
  } finally {
    clearTimeout(timeoutId);
  }
}

export function useUptime(): UptimeState {
  const [state, setState] = useState<UptimeState>({
    uptimeSeconds: null,
    error: false,
  });

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const uptimeSeconds = await fetchUptime();
        if (!cancelled) {
          setState({ uptimeSeconds, error: false });
        }
      } catch {
        if (!cancelled) {
          setState((prev) => ({ ...prev, error: true }));
        }
      }
    }

    poll();
    const intervalId = setInterval(poll, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, []);

  return state;
}
