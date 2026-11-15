import { describe, it, expect } from 'vitest';
import { formatIST } from '../lib/time';

/**
 * Tests for the IST formatting utility.
 */
describe('formatIST', () => {
  it('formats a UTC ISO string to IST correctly', () => {
    // 2023-01-01T00:00:00Z -> 5:30 AM IST (same day)
    const iso = '2023-01-01T00:00:00Z';
    expect(formatIST(iso)).toBe("1 Jan 2023, 05:30 IST");
  });
});

