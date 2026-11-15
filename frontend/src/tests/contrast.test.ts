import fs from 'fs';
import path from 'path';
import { expect, test } from 'vitest';

/**
 * Parse CSS custom properties from a file like src/styles/tokens.css.
 * Returns a map of name → hex string (e.g. '--color-text' → '#1A2030').
 */
function parseTokens(filePath: string): Record<string, string> {
  const raw = fs.readFileSync(filePath, 'utf8');
  const map: Record<string, string> = {};
  const varRegex = /--([a-zA-Z0-9-]+):\s*#([0-9A-Fa-f]{6})/g;
  let match: RegExpExecArray | null;
  while ((match = varRegex.exec(raw)) !== null) {
    const name = `--${match[1]}`;
    map[name] = `#${match[2]}`;
  }
  return map;
}

function luminance(hex: string): number {
  const rgb = hex
    .replace(/^#/, '')
    .match(/.{2}/g)!
    .map((c) => parseInt(c, 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)));
  return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
}

function contrast(a: string, b: string): number {
  const L1 = luminance(a);
  const L2 = luminance(b);
  return (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
}

const tokens = parseTokens(path.resolve(__dirname, '../styles/tokens.css'));

// helper to print ratio with two decimals
function logRatio(name: string, fg: string, bg: string) {
  const r = contrast(fg, bg);
  console.log(`${name}: ${r.toFixed(2)}:1`);
  return r;
}

test('WCAG contrast ratios (≥4.5:1 normal, ≥3:1 large)', () => {
  // text on paper, surface, sunken
  const pairs = [
    ['text-on-paper', tokens['--color-text'], tokens['--color-paper']],
    ['text-on-surface', tokens['--color-text'], tokens['--color-surface']],
    ['text-on-sunken', tokens['--color-text'], tokens['--color-sunken']],
    ['secondary-on-paper', tokens['--color-text-secondary'], tokens['--color-paper']],
    ['secondary-on-surface', tokens['--color-text-secondary'], tokens['--color-surface']],
    ['secondary-on-sunken', tokens['--color-text-secondary'], tokens['--color-sunken']],
    ['muted-on-paper', tokens['--color-text-muted'], tokens['--color-paper']],
    ['muted-on-surface', tokens['--color-text-muted'], tokens['--color-surface']],
    ['muted-on-sunken', tokens['--color-text-muted'], tokens['--color-sunken']],
    ['primary-text-on-primary', tokens['--color-primary-text'], tokens['--color-primary']],
    // chips
    ['chip-low', tokens['--color-chip-low-fg'], tokens['--color-chip-low-bg']],
    ['chip-medium', tokens['--color-chip-medium-fg'], tokens['--color-chip-medium-bg']],
    ['chip-high', tokens['--color-chip-high-fg'], tokens['--color-chip-high-bg']],
    ['chip-critical', tokens['--color-chip-critical-fg'], tokens['--color-chip-critical-bg']],
    // countdowns
    ['countdown-green', tokens['--color-countdown-green-fg'], tokens['--color-countdown-green-bg']],
    ['countdown-amber', tokens['--color-countdown-amber-fg'], tokens['--color-countdown-amber-bg']],
    ['countdown-red', tokens['--color-countdown-red-fg'], tokens['--color-countdown-red-bg']],
    ['countdown-overdue', tokens['--color-countdown-overdue-fg'], tokens['--color-countdown-overdue-bg']],
  ];

  for (const [name, fg, bg] of pairs) {
    const r = logRatio(name, fg, bg);
    const required = name === 'countdown-overdue' ? 3 : 4.5;
    expect(r).toBeGreaterThanOrEqual(required);
  }
});

