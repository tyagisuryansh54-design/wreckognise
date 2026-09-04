/**
 * Wreckognise design system.
 *
 * Colour distribution follows the 60-30-10 rule:
 *   60%  surface  -- cream / sand grounds
 *   30%  structure -- deep navy / teal cards and type
 *   10%  accent   -- azure / aqua interactive states and data marks
 * plus sparing pops (coral, sunset, amber) reserved for alerts and severity.
 */
/**
 * Tailwind's stock opacity scale is coarse (0, 5, 10, 20, 25, ...), but the
 * dark bento cards need finer steps -- the difference between `border-cream/8`
 * and `border-cream/10` is the difference between a hairline and a visible
 * rule. Opening the scale to every whole percent keeps those tokens legal in
 * both `@apply` and JSX class strings.
 */
const opacity = Object.fromEntries(
  Array.from({ length: 101 }, (_, i) => [i, String(i / 100)]),
)

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      opacity,
      colors: {
        // --- 60% : surface -------------------------------------------------
        cream: '#F9F6F0',
        sand: '#EFECE6',
        shell: '#E4E0D8',

        // --- 30% : structure -----------------------------------------------
        navy: {
          DEFAULT: '#0A192F',
          soft: '#122744',
          line: '#1D3557',
        },
        teal: {
          DEFAULT: '#1E3A3A',
          soft: '#2A5050',
        },

        // --- 10% : accent --------------------------------------------------
        azure: '#0077B6',
        aqua: '#00B4D8',

        // --- pops : alerts and severity flags -------------------------------
        coral: '#FF6B6B',
        sunset: '#FF7A00',
        amber: '#FFB703',
      },
      fontFamily: {
        display: ['"Playfair Display"', 'Georgia', 'serif'],
        mono: ['"Space Grotesk"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
        sans: ['"IBM Plex Sans"', 'system-ui', '-apple-system', 'sans-serif'],
        serif: ['"Crimson Pro"', 'Georgia', 'serif'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
      letterSpacing: {
        label: '0.14em',
      },
      borderRadius: {
        bento: '1.375rem',
      },
      boxShadow: {
        bento: '0 1px 2px rgba(10,25,47,0.04), 0 12px 32px -12px rgba(10,25,47,0.14)',
        'bento-lift': '0 2px 4px rgba(10,25,47,0.06), 0 24px 48px -16px rgba(10,25,47,0.24)',
        'inset-line': 'inset 0 1px 0 rgba(255,255,255,0.06)',
      },
      keyframes: {
        sweep: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(400%)' },
        },
        pulseRing: {
          '0%': { transform: 'scale(0.85)', opacity: '0.85' },
          '70%': { transform: 'scale(1.9)', opacity: '0' },
          '100%': { transform: 'scale(1.9)', opacity: '0' },
        },
        riseIn: {
          '0%': { opacity: '0', transform: 'translateY(14px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-600px 0' },
          '100%': { backgroundPosition: '600px 0' },
        },
      },
      animation: {
        sweep: 'sweep 3.4s linear infinite',
        'pulse-ring': 'pulseRing 2.2s cubic-bezier(0.24,0.6,0.36,1) infinite',
        'rise-in': 'riseIn 0.5s cubic-bezier(0.22,1,0.36,1) both',
        shimmer: 'shimmer 1.6s linear infinite',
      },
    },
  },
  plugins: [],
}
