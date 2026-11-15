/**
 * Utilities for formatting timestamps in Indian Standard Time (IST).
 * Uses Intl.DateTimeFormat to reliably format in the target timezone.
 */
import { parseISO } from 'date-fns';

export function formatIST(iso: string): string {
  const date = parseISO(iso);
  const fmt = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Kolkata',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
  const parts = fmt.formatToParts(date);
  const day = parts.find(p => p.type === 'day')?.value ?? '';
  const month = parts.find(p => p.type === 'month')?.value ?? '';
  const year = parts.find(p => p.type === 'year')?.value ?? '';
  const hour = parts.find(p => p.type === 'hour')?.value ?? '';
  const minute = parts.find(p => p.type === 'minute')?.value ?? '';
  return `${day} ${month} ${year}, ${hour}:${minute} IST`;
}
