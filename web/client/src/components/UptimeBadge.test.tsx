import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { UptimeBadge, humanizeUptime } from './UptimeBadge';
import type { UptimeState } from '@/hooks/useUptime';

// Mock useUptime hook
vi.mock('@/hooks/useUptime', () => ({
  useUptime: vi.fn<[], UptimeState>(),
}));

import { useUptime } from '@/hooks/useUptime';

const mockUseUptime = vi.mocked(useUptime);

describe('humanizeUptime', () => {
  it('formats seconds < 1 minute as "Xs"', () => {
    expect(humanizeUptime(30)).toBe('30s');
    expect(humanizeUptime(0)).toBe('0s');
    expect(humanizeUptime(59)).toBe('59s');
  });

  it('formats seconds >= 1 minute and < 1 hour as "Xm"', () => {
    expect(humanizeUptime(60)).toBe('1m');
    expect(humanizeUptime(2520)).toBe('42m');
    expect(humanizeUptime(3599)).toBe('59m');
  });

  it('formats seconds >= 1 hour as "Xh Ym"', () => {
    expect(humanizeUptime(3600)).toBe('1h 0m');
    expect(humanizeUptime(8100)).toBe('2h 15m');
    expect(humanizeUptime(8123)).toBe('2h 15m');
  });
});

describe('UptimeBadge', () => {
  it('renders "Uptime: --" when error is true', () => {
    mockUseUptime.mockReturnValue({ uptimeSeconds: null, error: true });
    render(<UptimeBadge />);
    expect(screen.getByText('Uptime: --')).toBeTruthy();
  });

  it('renders "Uptime: --" when uptimeSeconds is null and no error (loading)', () => {
    mockUseUptime.mockReturnValue({ uptimeSeconds: null, error: false });
    render(<UptimeBadge />);
    expect(screen.getByText('Uptime: --')).toBeTruthy();
  });

  it('renders "Uptime: 2h 15m" for 8100 seconds', () => {
    mockUseUptime.mockReturnValue({ uptimeSeconds: 8100, error: false });
    render(<UptimeBadge />);
    expect(screen.getByText('Uptime: 2h 15m')).toBeTruthy();
  });

  it('has accessible aria-label', () => {
    mockUseUptime.mockReturnValue({ uptimeSeconds: 8100, error: false });
    render(<UptimeBadge />);
    expect(screen.getByRole('status')).toBeTruthy();
  });
});
