const v = (name) => `var(--color-${name})`;

const colorNames = [
  'paper', 'surface', 'sunken', 'border', 'border-strong',
  'text', 'text-secondary', 'text-muted',
  'primary', 'primary-hover', 'primary-text',
  'link-focus', 'focus-ring', 'success', 'warning', 'error', 'info',
  'chip-low-bg', 'chip-low-fg', 'chip-medium-bg', 'chip-medium-fg',
  'chip-high-bg', 'chip-high-fg', 'chip-critical-bg', 'chip-critical-fg',
  'countdown-green-bg', 'countdown-green-fg',
  'countdown-amber-bg', 'countdown-amber-fg',
  'countdown-red-bg', 'countdown-red-fg',
  'countdown-overdue-bg', 'countdown-overdue-fg',
];

const fontSizes = [12, 13, 14, 16, 19, 23, 28];

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: Object.fromEntries(colorNames.map((n) => [n, v(n)])),
      borderRadius: {
        sm: 'var(--radius-sm)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
        full: 'var(--radius-full)',
      },
      boxShadow: {
        menu: 'var(--shadow-menu)',
        modal: 'var(--shadow-modal)',
      },
      fontFamily: {
        sans: ['var(--font-family-sans)'],
        mono: ['var(--font-family-mono)'],
      },
      fontSize: Object.fromEntries(
        fontSizes.map((s) => [
          String(s),
          [`var(--font-size-${s})`, { lineHeight: s >= 19 ? 'var(--line-height-heading)' : 'var(--line-height-base)' }],
        ]),
      ),
      letterSpacing: {
        label: 'var(--letter-spacing-label)',
        heading: 'var(--letter-spacing-heading)',
      },
      screens: { md: '768px', lg: '1024px', xl: '1280px' },
      transitionDuration: {
        micro: 'var(--duration-micro)',
        small: 'var(--duration-small)',
        large: 'var(--duration-large)',
      },
      transitionTimingFunction: {
        out: 'var(--ease-out)',
        in: 'var(--ease-in)',
        'in-out': 'var(--ease-in-out)',
      },
    },
  },
  plugins: [],
};