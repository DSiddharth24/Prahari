import { describe, it, expect } from 'vitest';
import { getCountdownState, formatCountdown } from '../lib/countdown';
import type { CaseStatus, CountdownState } from '../lib/types';

describe('getCountdownState', () => {
  const cases: Array<[number | null, CaseStatus, CountdownState]> = [
    // Just above 3h (3h + 1s) => green
    [3 * 3600 + 1, 'open', 'green'],
    // Exactly 3h => amber
    [3 * 3600, 'open', 'amber'],
    // Just below 3h (3h - 1s) => amber
    [3 * 3600 - 1, 'open', 'amber'],
    // Exactly 1h => amber
    [3600, 'open', 'amber'],
    // Just below 1h (1h - 1s) => red
    [3600 - 1, 'open', 'red'],
    // Exactly 0 seconds => overdue
    [0, 'open', 'overdue'],
    // Negative seconds => overdue
    [-5, 'open', 'overdue'],
    // Dismissed status => none
    [1000, 'dismissed', 'none'],
    // Reported status => none
    [1000, 'reported', 'none'],
    // Null seconds => none
    [null, 'open', 'none'],
  ];

  for (const [seconds, status, expected] of cases) {
    it(`returns ${expected} for ${seconds} seconds and status ${status}`, () => {
      expect(getCountdownState(seconds, status)).toBe(expected);
    });
  }
});

describe('formatCountdown', () => {
  it('formats green/amber hour-minute with zero-padded minutes', () => {
    expect(formatCountdown(3 * 3600, 'amber')).toBe('3h 00m');
    expect(formatCountdown(3 * 3600 + 61, 'green')).toBe('3h 01m');
  });

  it('formats red (under 1h) as minute/second', () => {
    expect(formatCountdown(42 * 60 + 10, 'red')).toBe('42m 10s');
  });

  it('formats overdue with zero-padded minutes', () => {
    expect(formatCountdown(-(1 * 3600 + 4 * 60), 'overdue')).toBe('OVERDUE by 1h 04m');
  });
});