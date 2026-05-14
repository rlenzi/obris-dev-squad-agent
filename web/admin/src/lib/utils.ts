import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatBRL(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return '—';
  const n = typeof value === 'string' ? parseFloat(value) : value;
  if (Number.isNaN(n)) return '—';
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(n);
}

export function formatUSD(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return '—';
  const n = typeof value === 'string' ? parseFloat(value) : value;
  if (Number.isNaN(n)) return '—';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 6,
  }).format(n);
}

export function formatNumber(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return '—';
  const n = typeof value === 'string' ? parseFloat(value) : value;
  if (Number.isNaN(n)) return '—';
  return new Intl.NumberFormat('pt-BR').format(n);
}

interface PydanticValidationItem {
  type: string;
  loc: (string | number)[];
  msg: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
}

/**
 * Converte qualquer erro de axios numa string segura pra renderizar.
 *
 * Lida com:
 * - Erro 422 do FastAPI (detail é array de PydanticValidationItem)
 * - Erro 400/403/etc (detail é string)
 * - Erros de rede sem response
 * - Fallback genérico
 */
export function formatApiError(err: unknown, fallback = 'Erro inesperado'): string {
  const errObj = err as {
    response?: { data?: { detail?: string | PydanticValidationItem[] } };
    message?: string;
  };
  const detail = errObj?.response?.data?.detail;

  if (typeof detail === 'string') return detail;

  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const path = item.loc?.filter((x) => x !== 'body').join('.');
        return path ? `${path}: ${item.msg}` : item.msg;
      })
      .join(' • ');
  }

  if (errObj?.message) return errObj.message;
  return fallback;
}
