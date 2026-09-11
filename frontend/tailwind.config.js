/**
 * Wreckognise design system -- terminal dark.
 *
 * One surface, not two. The previous palette ran light cards on a cream page
 * with dark cards for contrast; a terminal theme has a single near-black
 * ground and separates surfaces by a hairline and a few percent of lift.
 *
 * The token NAMES are unchanged on purpose. They are referenced ~300 times
 * across the components, and renaming them would mean touching every file to
 * achieve nothing the values cannot. What changed is what each one means:
 *
 *   cream  page ground      ->  near-black terminal ground
 *   sand   secondary ground ->  panel lift
 *   shell  hairline         ->  hairline, now light-on-dark
 *   navy   dark card / text ->  RAISED PANEL only (see note below)
 *   ink    (new)            ->  body text
 *
 * `navy` could not simply invert: it was both a card background and the body
 * text colour, which on a dark ground need to be opposite. Components using it
 * as text were repointed at `ink`; the ones using it as a surface kept it.
 *
 * Accent moves from azure/aqua to terminal green, with azure/aqua retained as
 * the cooler data tones so the sonar chart and meters keep their range.
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
        /*
         * Sampled from the reference template's own screenshot rather than
         * guessed from the phrase "neon green accents": #0A0A0A is 69% of
         * that image and the accent measures #00FF2D at full saturation,
         * hue 130deg. The ground is a NEUTRAL black -- no blue cast -- which
         * is most of why the reference reads as a terminal rather than as a
         * dark-mode dashboard.
         */

        // --- ground ---------------------------------------------------------
        cream: '#0A0A0A',        // page
        sand: '#0F0F0F',         // panel
        shell: '#1F1F1F',        // hairline

        // --- surfaces -------------------------------------------------------
        navy: {
          DEFAULT: '#0F0F0F',
          soft: '#141414',
          line: '#242424',
        },
        teal: {
          DEFAULT: '#0D0D0D',
          soft: '#131313',
        },

        // --- type -----------------------------------------------------------
        ink: {
          DEFAULT: '#FFFFFF',
          dim: '#A3A3A3',
          faint: '#6B6B6B',
        },

        // --- accent ---------------------------------------------------------
        // One accent, used sparingly. The reference spends it on the logo, the
        // active nav item, code-comment decorations and a single solid button.
        azure: '#00FF2D',
        aqua: '#15AA2C',         // the same green, muted, for rests and rules

        // --- alerts ---------------------------------------------------------
        coral: '#FF5C5C',
        sunset: '#FF9F45',
        amber: '#FFC533',
      },
      fontFamily: {
        // JetBrains Mono for anything that reads as machine output; Inter for
        // prose. `display` and `serif` are kept as aliases so the components
        // that reference them do not all have to change.
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        display: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        serif: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
      letterSpacing: {
        label: '0.14em',
      },
      borderRadius: {
        bento: '0.375rem',
      },
      boxShadow: {
        bento: 'none',
        'bento-lift': 'none',
        'inset-line': 'inset 0 1px 0 rgba(255,255,255,0.03)',
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
        caret: {
          '0%, 49%': { opacity: '1' },
          '50%, 100%': { opacity: '0' },
        },
        fadeUp: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
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
        caret: 'caret 1.05s step-end infinite',
        'fade-up': 'fadeUp 0.5s cubic-bezier(0.22, 1, 0.36, 1) both',
      },
    },
  },
  plugins: [],
}
