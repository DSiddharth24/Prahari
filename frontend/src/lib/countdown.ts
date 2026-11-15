/**
 * Countdown utilities for case deadlines.
 * Implements state calculation, human‑readable formatting, and a React hook.
 */
import { useEffect, useState } from 'react';
import type { CaseStatus, CountdownState } from './types';

/** Determine the countdown state based on remaining seconds and case status. */
export function getCountdownState(
  secondsRemaining: number | null,
  caseStatus: CaseStatus | string,
): CountdownState {
  if (caseStatus === 'dismissed' || caseStatus === 'reported') return 'none';
  if (secondsRemaining === null) return 'none';
  if (secondsRemaining > 3 * 60 * 60) return 'green'; // >3h
  if (secondsRemaining >= 1 * 60 * 60) return 'amber'; // >=1h up to 3h (including exactly 3h & 1h)
  if (secondsRemaining > 0) return 'red'; // >0 and <1h
  // 0 or negative seconds are overdue
  return 'overdue';
}

/** Format helpers */
function fmtHM(seconds: number): string {
  const abs = Math.abs(seconds);
  const h = Math.floor(abs / 3600);
  const m = Math.floor((abs % 3600) / 60);
  const minutePad = m.toString().padStart(2, '0');
  if (h) return `${h}h ${minutePad}m`;
  return `${minutePad}m`;
}

function fmtMS(seconds: number): string {
  const abs = Math.abs(seconds);
  const m = Math.floor(abs / 60);
  const s = abs % 60;
  return `${m}m ${s}s`;
}

/** Human‑readable string for a countdown.
 *  - Normal states use hour/minute formatting.
 *  - Under one hour uses minute/second formatting.
 *  - Overdue uses "OVERDUE by …" with hour/minute.
 */
export function formatCountdown(secondsRemaining: number, state: CountdownState): string {
  if (state === 'overdue') {
    return `OVERDUE by ${fmtHM(secondsRemaining)}`;
  }
  if (state === 'red') {
    // Under one hour
    return fmtMS(secondsRemaining);
  }
  // green or amber
  return fmtHM(secondsRemaining);
}

/** React hook that tracks a live countdown.
 *  Returns the current remaining seconds, derived state, and formatted string.
 */
export function useCountdown(
  deadlineAt: string | null,
  caseStatus: CaseStatus,
): { remainingSeconds: number | null; state: CountdownState; formatted: string } {
  const [remaining, setRemaining] = useState<number | null>(null);
  const [state, setState] = useState<CountdownState>('none');
  const [formatted, setFormatted] = useState<string>('');

  useEffect(() => {
    if (!deadlineAt) {
      setRemaining(null);
      setState('none');
      setFormatted('');
      return;
    }
    const compute = () => {
      const now = Date.now();
      const deadline = new Date(deadlineAt).getTime();
      const secs = Math.floor((deadline - now) / 1000);
      const s = getCountdownState(secs, caseStatus);
      setRemaining(secs);
      setState(s);
      setFormatted(formatCountdown(secs, s));
    };
    compute();
    const iv = setInterval(compute, 1000);
    return () => clearInterval(iv);
  }, [deadlineAt, caseStatus]);

  return { remainingSeconds: remaining, state, formatted };
}


