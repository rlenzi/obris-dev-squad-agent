import { Activity } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useUptime } from '@/hooks/useUptime';

export function humanizeUptime(seconds: number): string {
  if (seconds >= 3600) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return `${h}h ${m}m`;
  }
  if (seconds >= 60) {
    const m = Math.floor(seconds / 60);
    return `${m}m`;
  }
  return `${seconds}s`;
}

export function UptimeBadge({ className }: { className?: string }) {
  const { uptimeSeconds, error } = useUptime();

  const label =
    error || uptimeSeconds === null
      ? 'Uptime: --'
      : `Uptime: ${humanizeUptime(uptimeSeconds)}`;

  return (
    <span
      role="status"
      aria-label={label}
      title={label}
      className={cn(
        'inline-flex items-center gap-1 rounded-full border border-border bg-muted/60 px-2.5 py-0.5 text-xs font-medium text-muted-foreground',
        className,
      )}
    >
      <Activity className="size-3" aria-hidden="true" />
      {label}
    </span>
  );
}
